# shalf

An extensible, end-to-end machine learning framework, organised as a Python
monorepo and deployed to Kubernetes.

| Stage            | Package / service                                   | Status        |
| ---------------- | --------------------------------------------------- | ------------- |
| Data & features  | [`shalf-data`](packages/shalf-data)                 | **Implemented** |
| Online features  | [`services/feature-server`](services/feature-server) | **Implemented** |
| Training         | [`shalf-training`](packages/shalf-training)         | Skeleton      |
| Model registry   | [`shalf-models`](packages/shalf-models)             | Skeleton      |
| Serving runtime  | [`shalf-serving`](packages/shalf-serving)           | Skeleton      |
| Inference API    | [`services/inference-api`](services/inference-api)  | Skeleton      |
| Monitoring       | [`shalf-monitoring`](packages/shalf-monitoring)     | Skeleton      |
| Pipelines        | [`shalf-pipelines`](packages/shalf-pipelines)       | Skeleton      |

Every extension point (data sources, online/offline stores, transformations,
model registries, predictors, drift detectors, experiment trackers) is a
plugin registry. You add a backend by subclassing and registering it, in code
or through a Python entry point, without forking the framework.

Data-layer highlights: features declared as `Aggregate("amount", "sum", "7d")`
and run by DuckDB (11x faster than hand-written pandas in the included
benchmark); a Parquet offline cache so training and EDA don't touch source
databases; a separate, low-priority EDA serving path; versioned feature
logic with `plan` / `backfill` / `promote`.

## Quickstart

```bash
make install       # uv sync --all-packages
make quickstart    # seed SQLite, build a training set, materialise, read online
make test
make serve-features  # http://localhost:8080/docs
uv run python examples/benchmarks/aggregations.py   # DuckDB vs pandas
```

## Layout

```
packages/                 libraries (namespace package `shalf.*`, one dist each)
  shalf-core/             plugin registry, config (env interpolation), logging
  shalf-data/             sources, feature views, offline/online stores, CLI
  shalf-training/         datasets from feature services, trainer/tracker interfaces
  shalf-models/           model artifacts + model registry interface
  shalf-serving/          predictor contract + feature-store glue
  shalf-monitoring/       drift detection
  shalf-pipelines/        orchestrator-agnostic step DAGs
services/                 deployables, one container image each
  feature-server/         FastAPI online feature serving
  inference-api/          FastAPI model serving
examples/quickstart/      a complete feature repository on SQLite
deploy/
  docker/Dockerfile       one multi-stage Dockerfile, parameterised by SERVICE
  k8s/                    Kustomize base + dev/prod overlays
docs/                     architecture and design docs
```

## Docs

- [Architecture](docs/architecture.md): components, how they deploy, how they talk
- [Data layer](docs/data-layer.md): feature definitions, offline/online semantics, extending it
