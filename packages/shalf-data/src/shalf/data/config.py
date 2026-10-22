from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from shalf.core import load_yaml


class FeatureStoreConfig(BaseModel):
    """Contents of a feature repository's ``shalf.yaml``.

    Store sections are ``{"type": <registered plugin name>, **plugin params}``;
    values may reference environment variables as ``${VAR}`` /
    ``${VAR:-default}``.
    """

    model_config = ConfigDict(extra="forbid")

    project: str = "default"
    definitions: list[str] = ["features.py"]
    offline_store: dict[str, Any] = {"type": "pandas"}
    online_store: dict[str, Any] = {"type": "memory"}

    @field_validator("definitions", mode="before")
    @classmethod
    def _one_or_many(cls, value: Any) -> Any:
        return [value] if isinstance(value, str) else value

    @classmethod
    def load(cls, path: str | Path) -> FeatureStoreConfig:
        return cls.model_validate(load_yaml(path))

    def resolve_paths(self, base: Path) -> FeatureStoreConfig:
        """Make relative ``path`` entries of store configs relative to ``base``."""

        def fix(section: dict[str, Any]) -> dict[str, Any]:
            path = section.get("path")
            if isinstance(path, str) and path != ":memory:" and not Path(path).is_absolute():
                return {**section, "path": str(base / path)}
            return section

        return self.model_copy(
            update={
                "offline_store": fix(self.offline_store),
                "online_store": fix(self.online_store),
            }
        )
