# Architecture

## Principles

1. **Extensible by default.** Every backend-specific piece sits behind an
   abstract base class plus a `PluginRegistry` (`shalf.core.plugins`).
   Built-ins register themselves on import. Third-party packages register
   through entry points (`shalf.data.sources`, `shalf.data.online_stores`, ...),
   so a new backend is a `pip install`, not a fork.
2. **Platform and projects are separate.** This repository is the *platform*:
   libraries, services, base images and Kubernetes base manifests, with no
   business logic. Teams write *projects*: feature definitions, a dbt project
   and schedules. A project builds its images `FROM` the platform images, so
   pipelines, the feature server and training all run the same code and
   cannot disagree about what a feature means.
3. **One transformation, two runtimes.** Derived and on-demand features are
   computed by the same function offline (training) and online (serving),
   which removes training/serving skew by construction.
4. **Config via environment.** `shalf.yaml` supports `${VAR:-default}` and
   profiles. The platform's Kubernetes base sets the conventional paths and
   `SHALF_PROFILE` per workload, and Secrets provide credentials.

## Platform vs. project

| | Platform (this repo) | Project (its own repo) |
| --- | --- | --- |
| Contains | `packages/`, `services/`, `deploy/docker/Dockerfile`, `deploy/k8s/base` + `components/` | `shalf.yaml`, `features/`, `transform/` (dbt), `Dockerfile`, `deploy/<env>/` |
| Owned by | Platform/ML-infra team | Data scientists / analytics engineers |
| Released as | Versioned base images (`shalf-feature-server`, `shalf-platform-jobs`, `shalf-inference-api`) and the k8s base at a git tag | Project images (`<project>-serving`, `<project>-jobs`) + its overlays |
| Upgrades | New platform version | Bump `SHALF_VERSION` in the project's Dockerfile and `?ref=` in its kustomization |

`examples/quickstart/` is laid out exactly like a project repo. It lives here
so the platform's tests can run a real project end to end. To start a new
project, copy it. Its `deploy/` overlays reference the base by relative path
here; a separate repo would use
`github.com/la0bing/shalf//deploy/k8s/base?ref=<tag>`. Keeping several
projects in one repository is fine too (e.g. `projects/<name>/`), as long as
each keeps the same layout.

```
my-project/
  shalf.yaml            project, stores, transform (dbt), pipelines, profiles
  features/             entities.py, features.py ... (FeatureView, Aggregate, ...)
  transform/            dbt project: dbt_project.yml, profiles.yml, models/
  Dockerfile            FROM shalf-platform-jobs (+ dbt parse) / FROM shalf-feature-server
  deploy/dev|prod/      kustomization.yaml: platform base + images + secrets
```

## Data flow

```
app DB (SQLite / Postgres replica)
  │  ATTACH read-only
  ▼
dbt (dbt-duckdb, in-process) ──▶ Parquet models in /data/warehouse
  │  DbtModelSource(model=...)
  ▼
feature views (Aggregate / derived / on-demand) ──▶ offline cache /data/cache ──▶ training, EDA
  │  materialize                                 ──▶ Redis ──▶ feature-server ──▶ inference
```

A pipeline (`shalf-pipelines run hourly`) runs `dbt build` for its model
selection, including dbt tests. Only if that succeeds does it materialise the
feature views that read the rebuilt models, plus their dependents. dbt
model checksums are part of feature-view versions, so editing a dbt model
goes through the same `plan` / `backfill` / `promote` flow as editing feature
code.

**Why dbt-duckdb, and why in-process.** dbt-core runs as a library inside the
platform's batch image, so there's no dbt Cloud and no extra service. DuckDB
is already a platform dependency. Sources are attached read-only, and models
are written as Parquet on the shared volume, so the platform needs no
warehouse. Moving to a warehouse later is a change of dbt target in
`profiles.yml`.

**Scheduling.** Each pipeline is a Kubernetes CronJob on the project's jobs
image. Ordering *within* a run (dbt first, then features, stop on failed
tests) is handled by the pipeline itself, so no orchestrator service is
needed. What CronJobs still don't give you:
- dependencies *between* schedules (e.g. "hourly waits for daily")
- a UI
- partition-level backfill tracking

When those matter, run the same `shalf-pipelines run` command from Dagster,
Argo Workflows or Airflow.

## Packages

Libraries live in `packages/`. Each one is a separate distribution that
contributes to the `shalf.*` namespace package, so services install only what
they need. For example, the feature-server image contains `shalf-core` and
`shalf-data` but nothing from training.

```
shalf-core  <-  shalf-data  <-  shalf-training
                    ^      \
                    |       <-  shalf-serving  ->  shalf-models
shalf-pipelines  ->  shalf-data (+ dbt-core, dbt-duckdb in the jobs image only)
shalf-monitoring ->  shalf-core
```

The uv workspace (`pyproject.toml` at the root) installs every package
editable into one `.venv` for development. `uv.lock` pins the whole graph.

## Console

`services/console` is the platform's UI and control-plane API, deployed once
per cluster (`deploy/k8s/console`, namespace `shalf-system`). It reaches each
project through the project's feature-server admin API and its pipeline
CronJobs. Users sign in with OIDC SSO, and access is role-based: modules
declare permissions, admins compose custom roles and bind them to users or
SSO groups, globally or per project. See [console.md](console.md).

## Runtime topology (Kubernetes)

```
 clients ──▶ inference-api ──▶ feature-server ──────────▶ Redis primary ◀──┐
             [serving]         [serving, HPA, PDB]                          │ writes
                                                         Redis replica      │
 notebooks ─────────────────▶ feature-server-eda ──────▶ (read-only)        │
   │                          [eda, profile=eda]                            │
   └──▶ offline reads ──▶ /data (RWX): cache + warehouse ◀── pipeline-hourly/daily
                                                             [batch, CronJob: dbt → features]
                                                                       │
                                               source DB read replica ◀┘
[serving] / [batch] / [eda] = PriorityClass
```

| Workload             | Kind       | Image (placeholder)     | Command / profile                       |
| -------------------- | ---------- | ----------------------- | --------------------------------------- |
| `feature-server`     | Deployment | `shalf-project-serving` | `uvicorn feature_server.app:app`, `serving` |
| `feature-server-eda` | Deployment | `shalf-project-serving` | same, profile `eda`                     |
| `pipeline-hourly`    | CronJob    | `shalf-project-jobs`    | `shalf-pipelines run hourly`, `batch`   |
| `pipeline-daily`     | CronJob    | `shalf-project-jobs`    | `shalf-pipelines run daily`, `batch`    |
| `inference-api`      | Deployment | `shalf-inference-api`   | `uvicorn inference_api.app:app`, `serving` |

The project overlay maps the placeholders to its own images. How serving is
isolated from exploration and batch work is described in
[data-layer.md → Isolation](data-layer.md#isolation-serving-vs-exploration).
`deploy/k8s/components/dev-redis` adds an in-cluster Redis plus a read replica
for dev clusters. The quickstart's `deploy/jobs/backfill.yaml` is an on-demand
backfill Job.

## Language choices

Everything is Python today. That was a deliberate default, revisited per
component:

| Component | Language | Why |
| --- | --- | --- |
| Feature definitions, transformations | Python (+ SQL snippets in `where`/`query`) | The users are data scientists. Feature code must be the same code they prototype with in notebooks, and the same function must run offline and online. |
| Heavy computation (aggregations, Parquet I/O) | SQL executed by **DuckDB** (C++) | Python orchestrates and the engine does the work. This is where the 11x speed-up comes from, without asking users to leave Python. |
| Source queries | SQL pushed down to the database | Filtering and projection belong in the database. |
| Data modelling (cleaning, business rules) | SQL in **dbt**, run by DuckDB | Analytics engineers already know dbt; tests, lineage and docs come with it. |
| Feature server / inference API | Python (FastAPI) | Shares the definitions and on-demand transformations with training. Request time is dominated by the Redis round trip, not Python. |
| Infra | YAML (Kustomize), Dockerfile, Make | Standard tools, no custom DSL. |

**When to move part of serving off Python.** Only if a measured p99 budget
(e.g. < 5 ms at high QPS) cannot be met by scaling replicas. The candidate
is a small Go or Rust "online read" service that does key lookups only: it
reads the same Redis layout (`shalf:{project}:{view}@{version}:{key}`, JSON
values, `active:` pointers) and calls back to Python only for on-demand
features. The storage format is language-neutral by design, so that split
needs no data migration. Training code and feature definitions would stay in
Python.

## Adding a new service

1. `services/<name>/` with a `pyproject.toml` depending on the workspace
   packages it needs and a `src/<module>/app.py`.
2. Build with `make docker-build SERVICE=<name>`.
3. Add a Deployment to `deploy/k8s/base` with an image placeholder that
   project overlays map to an image.
