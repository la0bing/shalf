# shalf

An extensible, end-to-end machine learning framework, organised as a Python
monorepo and deployed to Kubernetes.

| Stage            | Package / service                                   | Status        |
| ---------------- | --------------------------------------------------- | ------------- |
| Console (UI, SSO, RBAC) | [`services/console`](services/console) · [docs](docs/console.md) | **Implemented** |
| Data & features  | [`shalf-data`](packages/shalf-data)                 | **Implemented** |
| Online features  | [`services/feature-server`](services/feature-server) | **Implemented** |
| Training         | [`shalf-training`](packages/shalf-training)         | Skeleton      |
| Model registry   | [`shalf-models`](packages/shalf-models)             | Skeleton      |
| Serving runtime  | [`shalf-serving`](packages/shalf-serving)           | Skeleton      |
| Inference API    | [`services/inference-api`](services/inference-api)  | Skeleton      |
| Monitoring       | [`shalf-monitoring`](packages/shalf-monitoring)     | Skeleton      |
| Pipelines (dbt → features) | [`shalf-pipelines`](packages/shalf-pipelines) | **Implemented** |

Every extension point (data sources, online/offline stores, transformations,
model registries, predictors, drift detectors, experiment trackers) is a
plugin registry. You add a backend by subclassing and registering it, in code
or through a Python entry point, without forking the framework.

Data-layer highlights: features declared as `Aggregate("amount", "sum", "7d")`
and run by DuckDB (11x faster than hand-written pandas in the included
benchmark); a Parquet offline cache so training and EDA don't touch source
databases; a separate, low-priority EDA serving path; versioned feature
logic with `plan` / `backfill` / `promote`.

This repository is the **platform**. Teams build **projects** (feature
definitions, a dbt project and schedules) on top of it, in their own repos.
[`examples/quickstart`](examples/quickstart) is a complete project in exactly
that layout. See [Platform vs. project](docs/architecture.md#platform-vs-project).

## Quickstart

```bash
make install       # uv sync --all-packages
make quickstart    # SQLite -> dbt -> features -> training set -> online read
make test
make serve-features  # http://localhost:8080/docs
make console-web && make console   # UI on http://localhost:8090
uv run python examples/benchmarks/aggregations.py   # DuckDB vs pandas
```

## Deploy

| Option | Use it for | How |
| --- | --- | --- |
| Local processes | Development, demos | `make quickstart && make console-web && make console` |
| Docker Compose | A proof of concept on one machine | `make poc-up`, see [deploy/compose](deploy/compose/README.md) |
| Kubernetes | Production | Platform base `deploy/k8s` + project overlays, console in `deploy/k8s/console` ([architecture](docs/architecture.md)) |

## Layout

```
packages/                 platform libraries (namespace package `shalf.*`, one dist each)
  shalf-core/             plugin registry, config (env interpolation, profiles), logging
  shalf-data/             sources (incl. dbt models), feature views, offline/online stores, CLI
  shalf-pipelines/        dbt build -> feature materialisation; scheduled runs and backfills
  shalf-training/         datasets from feature services, trainer/tracker interfaces
  shalf-models/           model artifacts + model registry interface
  shalf-serving/          predictor contract + feature-store glue
  shalf-monitoring/       drift detection
services/                 platform services, one base image each
  feature-server/         FastAPI online feature serving
  inference-api/          FastAPI model serving (skeleton)
  platform-jobs/          batch image: dbt-core + dbt-duckdb + pipelines
  console/                web UI (React, web/) + control-plane API: OIDC SSO, RBAC, audit
deploy/
  docker/Dockerfile       builds the platform base images
  compose/                docker compose proof of concept (one machine)
  k8s/base/               generic workloads for one project (image placeholders)
  k8s/components/         optional add-ons (dev Redis)
examples/quickstart/      an example *project*: shalf.yaml, features/, transform/ (dbt),
                          Dockerfile (FROM platform images), deploy/ overlays
docs/                     architecture and design docs
```

## Docs

- [Architecture](docs/architecture.md): components, how they deploy, how they talk
- [Data layer](docs/data-layer.md): feature definitions, offline/online semantics, extending it
- [Console](docs/console.md): modules, SSO, RBAC model, deployment
