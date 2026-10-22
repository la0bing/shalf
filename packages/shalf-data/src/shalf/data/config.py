from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from shalf.core import ConfigError, interpolate_env, load_yaml


class FeatureStoreConfig(BaseModel):
    """Contents of a feature repository's ``shalf.yaml``.

    Store sections are ``{"type": <registered plugin name>, **plugin params}``;
    values may reference environment variables as ``${VAR}`` /
    ``${VAR:-default}``.

    ``profiles`` lets one file describe several deployments of the same
    features. A profile (selected with ``$SHALF_PROFILE``) replaces whole
    top-level sections, e.g. an ``eda`` profile that reads a Redis replica
    read-only and never touches source databases::

        profiles:
          eda:
            online_store: {type: redis, url: "${SHALF_REDIS_REPLICA_URL}", read_only: true}
            offline_store: {type: pandas, cache_path: /cache, cache_only: true}

    ``auto_promote``: when a view's logic changes, the materialiser builds the
    new version beside the old one and switches readers over once the first
    full run finishes. Set it to ``false`` to switch manually after checking
    the new values (``shalf-data promote``).
    """

    model_config = ConfigDict(extra="forbid")

    project: str = "default"
    definitions: list[str] = ["features.py"]
    offline_store: dict[str, Any] = {"type": "pandas"}
    online_store: dict[str, Any] = {"type": "memory"}
    auto_promote: bool = True
    version_cache_seconds: float = 10.0
    # Consumed by shalf-pipelines (dbt project location, schedules); the data
    # layer only reads `transform.warehouse_path` / `transform.manifest_path`.
    transform: dict[str, Any] = {}
    pipelines: dict[str, Any] = {}

    @field_validator("definitions", mode="before")
    @classmethod
    def _one_or_many(cls, value: Any) -> Any:
        return [value] if isinstance(value, str) else value

    @classmethod
    def load(cls, path: str | Path, profile: str | None = None) -> FeatureStoreConfig:
        """Load, apply ``profile`` if given, then interpolate env vars (only the
        sections actually used must have their variables set)."""
        raw = load_yaml(path, interpolate=False)
        profiles = raw.pop("profiles", {}) or {}
        if profile:
            if profile not in profiles:
                raise ConfigError(f"Profile {profile!r} not in {path}; known: {sorted(profiles)}")
            raw.update(profiles[profile])
        return cls.model_validate(interpolate_env(raw))

    def resolve_paths(self, base: Path) -> FeatureStoreConfig:
        """Make relative ``path`` / ``*_path`` / ``*_dir`` entries relative to ``base``."""

        def fix(section: dict[str, Any]) -> dict[str, Any]:
            fixed = dict(section)
            for key, value in section.items():
                is_path = key == "path" or key.endswith(("_path", "_dir"))
                if (
                    is_path
                    and isinstance(value, str)
                    and value != ":memory:"
                    and "://" not in value
                    and not Path(value).is_absolute()
                ):
                    fixed[key] = str(base / value)
            return fixed

        return self.model_copy(
            update={
                "offline_store": fix(self.offline_store),
                "online_store": fix(self.online_store),
                "transform": fix(self.transform),
            }
        )
