from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path

from shalf.core import PluginRegistry
from shalf.models.artifact import ModelArtifact


class ModelRegistry(ABC):
    """Stores model versions and their lifecycle stage. Plug in MLflow, SageMaker, W&B, ..."""

    @abstractmethod
    def register(self, artifact: ModelArtifact) -> ModelArtifact: ...

    @abstractmethod
    def get(
        self, name: str, version: str | None = None, stage: str | None = None
    ) -> ModelArtifact: ...

    @abstractmethod
    def promote(self, name: str, version: str, stage: str) -> ModelArtifact: ...

    @abstractmethod
    def list(self) -> list[ModelArtifact]: ...


model_registry_registry: PluginRegistry[ModelRegistry] = PluginRegistry(
    "model registry", ModelRegistry, entry_point_group="shalf.models.registries"
)


@model_registry_registry.register("local")
class LocalModelRegistry(ModelRegistry):
    """JSON index on local disk / a mounted volume. For development."""

    def __init__(self, root: str | Path = "model_registry") -> None:
        self.root = Path(root)

    def _index(self) -> Path:
        return self.root / "index.json"

    def _load(self) -> list[dict]:
        return json.loads(self._index().read_text()) if self._index().exists() else []

    def _save(self, items: list[dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._index().write_text(json.dumps(items, indent=2))

    def register(self, artifact: ModelArtifact) -> ModelArtifact:
        items = [
            i
            for i in self._load()
            if (i["name"], i["version"]) != (artifact.name, artifact.version)
        ]
        self._save([*items, asdict(artifact)])
        return artifact

    def get(self, name: str, version: str | None = None, stage: str | None = None) -> ModelArtifact:
        matches = [
            ModelArtifact(**i)
            for i in self._load()
            if i["name"] == name and version in (None, i["version"]) and stage in (None, i["stage"])
        ]
        if not matches:
            raise KeyError(f"No model {name!r} (version={version}, stage={stage})")
        return matches[-1]

    def promote(self, name: str, version: str, stage: str) -> ModelArtifact:
        artifact = self.get(name, version)
        artifact.stage = stage
        return self.register(artifact)

    def list(self) -> list[ModelArtifact]:
        return [ModelArtifact(**i) for i in self._load()]
