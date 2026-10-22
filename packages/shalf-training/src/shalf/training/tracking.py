from __future__ import annotations

from typing import Any

from shalf.core import PluginRegistry


class ExperimentTracker:
    """Experiment tracking interface (MLflow, W&B, ... as plugins). Defaults are no-ops."""

    def start_run(self, name: str, tags: dict[str, str] | None = None) -> None: ...

    def log_params(self, params: dict[str, Any]) -> None: ...

    def log_metrics(self, metrics: dict[str, float], step: int | None = None) -> None: ...

    def end_run(self) -> None: ...


tracker_registry: PluginRegistry[ExperimentTracker] = PluginRegistry(
    "experiment tracker", ExperimentTracker, entry_point_group="shalf.training.trackers"
)


@tracker_registry.register("noop")
class NoopTracker(ExperimentTracker):
    pass
