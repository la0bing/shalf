"""Pipelines: ordered steps run as one unit by a scheduler (a Kubernetes CronJob
or Job, or an orchestrator such as Dagster/Argo/Airflow calling the same CLI).

The built-in *project pipeline* runs ``dbt build`` for a selection of models,
then materialises (or backfills) the feature views that read the rebuilt
models, so features never run ahead of the data they depend on.
"""

from shalf.pipelines.pipeline import LocalRunner, Pipeline, Step
from shalf.pipelines.project import (
    PipelineConfig,
    PipelineError,
    TransformConfig,
    affected_views,
    build_pipeline,
    run_pipeline,
)

__all__ = [
    "LocalRunner",
    "Pipeline",
    "PipelineConfig",
    "PipelineError",
    "Step",
    "TransformConfig",
    "affected_views",
    "build_pipeline",
    "run_pipeline",
]
