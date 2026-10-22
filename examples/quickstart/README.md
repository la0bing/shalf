# quickstart: an example shalf project

This directory is laid out exactly like a team's own project repository.
Copy it to start a new one.

```
shalf.yaml       project config: stores, dbt project, pipelines, profiles
features/        feature definitions (entities, views, aggregations, services)
transform/       dbt project: staging + marts over the application database
Dockerfile       project images, built FROM the platform base images
deploy/          Kustomize overlays (platform base + this project's images), backfill Job
seed.py          creates a synthetic "application database" (SQLite)
run.py           end-to-end walk-through
```

## Run it locally

```bash
uv run python examples/quickstart/run.py              # seed -> dbt -> features -> train/online
uv run shalf-pipelines --repo examples/quickstart run hourly    # what the CronJob runs
uv run shalf-pipelines --repo examples/quickstart dbt docs generate
uv run shalf-data --repo examples/quickstart plan     # after editing a model or feature
```

## How the pieces fit

1. **dbt** (`transform/`) cleans the source tables and applies business rules.
   It runs in-process via dbt-duckdb: sources are attached read-only (SQLite
   locally, a Postgres read replica in prod) and marts are written as Parquet
   to the warehouse path. Tests in `_schema.yml` gate the pipeline.
2. **Features** (`features/`) read marts with `DbtModelSource(model=...)` and
   add feature semantics: windowed `Aggregate`s, point-in-time joins, custom
   derived logic, on-demand features and the model's `FeatureService`.
3. **Pipelines** (`shalf.yaml` → `pipelines:`) pair a dbt selection with the
   feature views reading the rebuilt models. In Kubernetes each is a CronJob
   (`pipeline-hourly`, `pipeline-daily`) on this project's jobs image.

## Deploy

```bash
docker build --target jobs    -t ghcr.io/la0bing/quickstart-jobs:1.0.0 .
docker build --target serving -t ghcr.io/la0bing/quickstart-serving:1.0.0 .
kubectl apply -k deploy/prod      # needs the shalf-secrets Secret, see the overlay
```

In a standalone repo, change the overlay's base to
`github.com/la0bing/shalf//deploy/k8s/base?ref=<platform tag>`.
