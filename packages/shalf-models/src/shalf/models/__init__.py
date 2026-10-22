"""Model artifacts and registry. Skeleton: interfaces + a local filesystem registry."""

from shalf.models.artifact import ModelArtifact
from shalf.models.registry import LocalModelRegistry, ModelRegistry, model_registry_registry

__all__ = ["LocalModelRegistry", "ModelArtifact", "ModelRegistry", "model_registry_registry"]
