"""Read dbt models as feature sources.

A project's dbt models (built by ``shalf-pipelines`` with dbt-duckdb) are
written as Parquet files under the *warehouse path*, one file per model.
:class:`DbtModelSource` reads them by model name::

    transactions = FeatureView(
        name="transactions",
        source=DbtModelSource(model="fct_transactions", timestamp_field="created_at"),
        ...
    )

Two things tie the feature layer to dbt:

* **Lineage.** The source knows its model name, so a pipeline run that
  rebuilt ``fct_transactions`` re-materialises exactly the feature views that
  read it.
* **Versions.** The view version includes the checksum of the model's SQL and
  of everything upstream of it in the dbt DAG (from ``manifest.json``), so
  changing a dbt model triggers the same plan/backfill/promote flow as
  changing feature code.

The warehouse and manifest locations come from the project's ``shalf.yaml``
(``transform:`` section, set by ``FeatureStore.from_repo``) or from
``$SHALF_WAREHOUSE_PATH`` / ``$SHALF_DBT_MANIFEST``.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, ClassVar

from shalf.core import ShalfError, get_logger
from shalf.data.sources.base import source_registry
from shalf.data.sources.duckdb import DuckDBSource

log = get_logger(__name__)

_context: dict[str, str] = {}
_manifest_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def configure_dbt(*, warehouse_path: str | Path | None, manifest_path: str | Path | None) -> None:
    """Point dbt-backed sources at a project's warehouse and manifest."""
    _context.clear()
    if warehouse_path:
        _context["warehouse_path"] = str(warehouse_path)
    if manifest_path:
        _context["manifest_path"] = str(manifest_path)


def _setting(key: str, env: str) -> str | None:
    return _context.get(key) or os.environ.get(env)


def load_manifest() -> dict[str, Any] | None:
    path = _setting("manifest_path", "SHALF_DBT_MANIFEST")
    if not path or not Path(path).is_file():
        return None
    mtime = Path(path).stat().st_mtime
    cached = _manifest_cache.get(path)
    if cached is None or cached[0] != mtime:
        cached = (mtime, json.loads(Path(path).read_text()))
        _manifest_cache[path] = cached
    return cached[1]


def model_checksum(manifest: dict[str, Any], model: str) -> str:
    """Checksum of a model's SQL, its macros and everything upstream of it."""
    nodes = manifest.get("nodes", {})
    by_name = {n["name"]: uid for uid, n in nodes.items() if n.get("resource_type") == "model"}
    if model not in by_name:
        raise ShalfError(f"dbt model {model!r} not found in the manifest")

    memo: dict[str, str] = {}

    def node_hash(uid: str) -> str:
        if uid in memo:
            return memo[uid]
        node = nodes.get(uid)
        if node is None:  # a source or an external node: its identity is what matters
            memo[uid] = uid
            return uid
        depends = node.get("depends_on", {})
        macros = manifest.get("macros", {})
        parts = [
            node.get("checksum", {}).get("checksum", ""),
            json.dumps(node.get("config", {}).get("materialized")),
            *(
                hashlib.sha256(macros.get(m, {}).get("macro_sql", "").encode()).hexdigest()
                for m in sorted(depends.get("macros", []))
            ),
            *(node_hash(d) for d in sorted(depends.get("nodes", []))),
        ]
        memo[uid] = hashlib.sha256("|".join(parts).encode()).hexdigest()
        return memo[uid]

    return node_hash(by_name[model])[:16]


@source_registry.register("dbt")
class DbtModelSource(DuckDBSource):
    """The Parquet output of a dbt model (``<warehouse>/<model>.parquet``)."""

    type_name: ClassVar[str] = "dbt"
    _warned: ClassVar[set[str]] = set()

    def __init__(self, *, model: str, name: str | None = None, **kwargs: Any) -> None:
        self.model = model
        super().__init__(path=f"{model}.parquet", name=name or model, **kwargs)

    def model_file(self) -> Path:
        warehouse = _setting("warehouse_path", "SHALF_WAREHOUSE_PATH")
        if not warehouse:
            raise ShalfError(
                "No warehouse path for dbt models: set `transform.warehouse_path` in "
                "shalf.yaml or $SHALF_WAREHOUSE_PATH"
            )
        return Path(warehouse) / f"{self.model}.parquet"

    def is_built(self) -> bool:
        return self.model_file().exists()

    def file_reader(self) -> str:
        file = self.model_file()
        if not file.exists():
            raise ShalfError(f"dbt model {self.model!r} has not been built yet ({file} missing)")
        return f"read_parquet('{str(file).replace(chr(39), chr(39) * 2)}')"

    def fingerprint(self) -> dict[str, Any]:
        base = {**super().fingerprint(), "model": self.model, "query": None}
        manifest = load_manifest()
        if manifest is None:
            if self.model not in self._warned:
                self._warned.add(self.model)
                log.warning(
                    "No dbt manifest found: the version of views reading %r ignores its SQL. "
                    "Run `dbt parse` (pipelines do) or set $SHALF_DBT_MANIFEST.",
                    self.model,
                )
            base["model_checksum"] = None
        else:
            base["model_checksum"] = model_checksum(manifest, self.model)
        return base

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "model": self.model}
