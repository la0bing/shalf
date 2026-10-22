from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelArtifact:
    """Metadata that travels with a trained model.

    ``feature_service`` ties the model to the exact features it was trained
    on, so the serving side fetches the same features online.
    """

    name: str
    version: str
    uri: str
    feature_service: str
    framework: str = "sklearn"
    stage: str = "staging"  # staging | production | archived
    metrics: dict[str, float] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
