"""How the console reaches a project.

Everything the UI shows goes through these two interfaces, so a new way of
running projects (another orchestrator, a different cluster API) is one new
class rather than changes across the console.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from shalf.core import ShalfError


class BackendError(ShalfError):
    """The project could not be reached or rejected the request."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


class ProjectBackend(ABC):
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description

    kind: str = "abstract"

    @abstractmethod
    def registry(self) -> dict[str, Any]:
        """``FeatureRegistry.to_dict()``: entities, feature views, services."""

    @abstractmethod
    def plan(self) -> list[dict[str, Any]]:
        """``FeatureStore.plan()``: code vs. active version per view."""

    @abstractmethod
    def preview(self, view: str, limit: int) -> dict[str, Any]:
        """``{"columns": [...], "rows": [[...]]}`` of computed rows."""

    @abstractmethod
    def promote(self, views: list[str] | None) -> dict[str, str]: ...

    @abstractmethod
    def online(
        self,
        entities: dict[str, list[Any]],
        features: list[str] | None,
        feature_service: str | None,
        request_data: dict[str, list[Any]] | None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def pipelines(self) -> dict[str, Any]:
        """The project's ``pipelines:`` configuration."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """``{"status": "ok" | "error", ...}``."""


class PipelineRunner(ABC):
    kind: str = "abstract"

    @abstractmethod
    def start(
        self,
        pipeline: str,
        *,
        start: str | None,
        end: str | None,
        promote: bool,
        actor: str,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def runs(self, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get(self, run_id: str) -> dict[str, Any]:
        """A run including its ``log``."""

    def schedules(self) -> dict[str, str]:
        """Pipeline name -> cron schedule, where the runner knows it."""
        return {}
