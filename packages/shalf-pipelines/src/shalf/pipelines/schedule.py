"""A minimal in-process scheduler for installs without Kubernetes CronJobs
(docker compose, a single VM).

Runs pipelines one after another - never concurrently - each every
``interval``. All pipelines run once at start-up, in the given order.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Any

from shalf.core import get_logger
from shalf.data import FeatureStore
from shalf.pipelines.project import run_pipeline

log = get_logger(__name__)


def run_schedule(
    store: FeatureStore,
    repo_path: str,
    intervals: Sequence[tuple[str, timedelta]],
    *,
    max_runs: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    runner: Callable[..., dict[str, Any]] = run_pipeline,
) -> list[tuple[str, str]]:
    """Returns ``[(pipeline, "succeeded" | "failed"), ...]`` once ``max_runs`` is reached."""
    if not intervals:
        raise ValueError("Nothing to schedule: give pipelines an `every:` or use --every")
    start = clock()
    next_run = {name: start for name, _ in intervals}
    history: list[tuple[str, str]] = []
    while max_runs is None or len(history) < max_runs:
        for name, interval in intervals:
            if next_run[name] > clock():
                continue
            try:
                outputs = runner(store, repo_path, name)
                features = outputs.get("features", {})
                log.info("scheduled run of %s succeeded: %s", name, features)
                history.append((name, "succeeded"))
            except Exception:
                log.exception("scheduled run of %s failed", name)
                history.append((name, "failed"))
            next_run[name] = clock() + interval.total_seconds()
            if max_runs is not None and len(history) >= max_runs:
                return history
        sleep(max(0.0, min(next_run.values()) - clock()))
    return history
