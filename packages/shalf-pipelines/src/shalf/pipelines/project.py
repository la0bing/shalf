"""The project pipeline: ``dbt build`` -> feature materialisation.

Configured in the project's ``shalf.yaml``::

    transform:                        # the dbt project of this feature project
      project_dir: transform
      profiles_dir: transform
      target: ${SHALF_DBT_TARGET:-dev}
      target_path: ${SHALF_DBT_TARGET_PATH:-transform/target}
      manifest_path: ${SHALF_DBT_MANIFEST:-transform/target/manifest.json}
      warehouse_path: ${SHALF_WAREHOUSE_PATH:-data/warehouse}

    pipelines:
      hourly:
        dbt_select: "tag:hourly+"     # dbt selection; omit to skip dbt
        views: affected               # affected | all | [view, ...]
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from shalf.core import ShalfError, get_logger
from shalf.data import FeatureStore
from shalf.data.feature_view import BaseFeatureView, FeatureView, OnDemandFeatureView
from shalf.data.sources.dbt import DbtModelSource
from shalf.pipelines.dbt import DbtProject, DbtResult
from shalf.pipelines.pipeline import LocalRunner, Pipeline

log = get_logger(__name__)


class PipelineError(ShalfError):
    """A pipeline step failed; later steps did not run."""


class TransformConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["dbt"] = "dbt"
    project_dir: str
    profiles_dir: str | None = None
    target: str | None = None
    target_path: str | None = None
    manifest_path: str | None = None
    warehouse_path: str

    def dbt(self, repo_path: str) -> DbtProject:
        target_path = self.target_path or os.path.join(self.project_dir, "target")
        return DbtProject(
            project_dir=self.project_dir,
            profiles_dir=self.profiles_dir or self.project_dir,
            target=self.target,
            target_path=target_path,
            env={"SHALF_WAREHOUSE_PATH": self.warehouse_path, "SHALF_PROJECT_DIR": repo_path},
        )


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dbt_select: str | None = None
    views: Literal["affected", "all"] | list[str] = "affected"


def _dbt_sources(view: BaseFeatureView) -> list[DbtModelSource]:
    if isinstance(view, FeatureView):
        return [view.source] if isinstance(view.source, DbtModelSource) else []
    sources: list[DbtModelSource] = []
    for upstream in view.upstream:
        if isinstance(upstream, BaseFeatureView):
            sources += _dbt_sources(upstream)
    return sources


def _models_read_by(view: BaseFeatureView) -> set[str]:
    return {s.model for s in _dbt_sources(view)}


def affected_views(store: FeatureStore, models: Sequence[str]) -> list[str]:
    """Batch views that read any of ``models`` (directly or through upstream views)."""
    built = set(models)
    return [
        view.name
        for view in store.list_feature_views()
        if not isinstance(view, OnDemandFeatureView) and _models_read_by(view) & built
    ]


def _with_dependents(store: FeatureStore, names: Sequence[str]) -> list[str]:
    wanted = set(names)
    for name in names:
        wanted |= {v.name for v in store.registry.dependents(name)}
    return [
        v.name
        for v in store.list_feature_views()
        if v.name in wanted and not isinstance(v, OnDemandFeatureView)
    ]


def build_pipeline(
    store: FeatureStore,
    repo_path: str,
    name: str,
    *,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    promote: bool = False,
) -> Pipeline:
    """Steps: ``transform`` (dbt build) -> ``features`` (materialise or backfill).

    With ``start``/``end`` the run is a backfill: dbt receives them as
    ``--vars '{start: ..., end: ...}'`` (for incremental models) and the
    feature views are recomputed over that range.
    """
    pipelines = store.config.pipelines
    if name not in pipelines:
        raise PipelineError(f"Unknown pipeline {name!r}; defined: {sorted(pipelines)}")
    config = PipelineConfig.model_validate(pipelines[name] or {})
    backfill = start is not None or end is not None
    pipeline = Pipeline(name)

    @pipeline.step()
    def transform() -> DbtResult | None:
        if config.dbt_select is None:
            return None
        if not store.config.transform:
            raise PipelineError(f"Pipeline {name!r} selects dbt models but `transform` is not set")
        dbt = TransformConfig.model_validate(store.config.transform).dbt(repo_path)
        variables = {k: str(v) for k, v in (("start", start), ("end", end)) if v is not None}
        result = dbt.build(config.dbt_select, variables or None)
        if not result.success:
            raise PipelineError(f"dbt build failed: {result.failures}; features not updated")
        log.info("dbt built models: %s", result.models)
        return result

    @pipeline.step(depends_on=["transform"])
    def features(transform: DbtResult | None) -> dict[str, int]:
        if config.views == "all":
            views = [v.name for v in store.list_feature_views()]
        elif config.views == "affected":
            views = affected_views(store, transform.models if transform else [])
        else:
            views = list(config.views)
        views = _with_dependents(store, views)
        waiting = {
            name: sorted(
                {s.model for s in _dbt_sources(store.registry.get_view(name)) if not s.is_built()}
            )
            for name in views
        }
        waiting = {name: models for name, models in waiting.items() if models}
        if waiting:
            # e.g. the first daily run before any hourly run built the facts.
            log.warning("skipping views whose dbt models are not built yet: %s", waiting)
            views = [v for v in views if v not in waiting]
        if not views:
            log.info("no feature views affected")
            return {}
        if backfill:
            # `views` already includes dependents and excludes unbuilt inputs,
            # so materialise the range directly (store.backfill would re-add them).
            return store.materialize(start, end, views, promote=promote)
        return store.materialize_incremental(views=views)

    return pipeline


def run_pipeline(store: FeatureStore, repo_path: str, name: str, **kwargs: Any) -> dict[str, Any]:
    return LocalRunner().run(build_pipeline(store, repo_path, name, **kwargs))
