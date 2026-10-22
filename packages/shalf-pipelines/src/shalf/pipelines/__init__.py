"""Orchestrator-agnostic pipelines. Skeleton: steps + a local runner; adapters for
Argo Workflows / Airflow / Kubeflow are meant to compile the same Pipeline."""

from shalf.pipelines.pipeline import LocalRunner, Pipeline, Step

__all__ = ["LocalRunner", "Pipeline", "Step"]
