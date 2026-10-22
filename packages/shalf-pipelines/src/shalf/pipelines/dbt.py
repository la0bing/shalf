"""Thin wrapper around dbt's programmatic API (dbt-core >= 1.5).

dbt runs in-process: no dbt Cloud, no extra service. With the dbt-duckdb
adapter the computation runs in DuckDB, reading the source databases through
DuckDB's ``ATTACH`` (read-only) and writing models as Parquet files to the
project's warehouse path.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from shalf.core import ShalfError, get_logger

log = get_logger(__name__)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


@dataclass
class DbtResult:
    success: bool
    models: list[str]  # models built successfully
    failures: list[str]  # nodes (models or tests) that failed or errored


class DbtProject:
    def __init__(
        self,
        *,
        project_dir: str,
        profiles_dir: str,
        target: str | None,
        target_path: str,
        env: Mapping[str, str],
    ) -> None:
        self.project_dir = project_dir
        self.profiles_dir = profiles_dir
        self.target = target
        self.target_path = target_path
        self.env = dict(env)

    def invoke(self, args: Sequence[str], on_log: Callable[[str], None] | None = None) -> Any:
        try:
            from dbt.cli.main import dbtRunner
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ShalfError("dbt is not installed: `pip install shalf-pipelines[dbt]`") from exc

        os.environ.update(self.env)  # profiles.yml reads these through env_var()
        # No telemetry, and no ~/.dbt or .user.yml writes (read-only filesystems).
        os.environ.setdefault("DBT_SEND_ANONYMOUS_USAGE_STATS", "false")
        common = [
            "--project-dir", self.project_dir,
            "--profiles-dir", self.profiles_dir,
            "--target-path", self.target_path,
            "--log-path", os.path.join(self.target_path, "logs"),
        ]  # fmt: skip
        if self.target:
            common += ["--target", self.target]
        log.info("dbt %s", " ".join(args))
        # Options after the (possibly multi-word, e.g. `docs generate`) command.
        callbacks: list[Any] = []
        if on_log is not None:

            def forward(event: Any) -> None:
                info = getattr(event, "info", None)
                if info is not None and info.msg and info.level in ("info", "warn", "error"):
                    on_log(f"dbt {info.level.upper()} {_ANSI.sub('', info.msg)}")

            callbacks.append(forward)
        return dbtRunner(callbacks=callbacks).invoke([*args, *common])

    def build(
        self,
        select: str | None,
        variables: Mapping[str, Any] | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> DbtResult:
        if "SHALF_WAREHOUSE_PATH" in self.env:  # dbt-duckdb creates files, not directories
            os.makedirs(self.env["SHALF_WAREHOUSE_PATH"], exist_ok=True)
        args = ["build"]
        if select:
            args += ["--select", select]
        if variables:
            import json

            args += ["--vars", json.dumps(dict(variables))]
        result = self.invoke(args, on_log)
        models, failures = [], []
        for node_result in getattr(result.result, "results", None) or []:
            node, status = node_result.node, str(node_result.status)
            if status in ("error", "fail"):
                failures.append(node.unique_id)
            elif node.resource_type == "model" and status == "success":
                models.append(node.name)
        if result.exception is not None:
            failures.append(f"dbt: {result.exception}")
        return DbtResult(result.success and not failures, models, failures)

    def parse(self) -> None:
        result = self.invoke(["parse"])
        if not result.success:
            raise ShalfError(f"dbt parse failed: {result.exception}")
