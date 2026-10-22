# Architecture

## Principles

1. **Extensible by default.** Every backend-specific piece sits behind an
   abstract base class plus a `PluginRegistry` (`shalf.core.plugins`).
   Built-ins register themselves on import. Third-party packages register
   through entry points (`shalf.data.sources`, `shalf.data.online_stores`, ...),
   so a new backend is a `pip install`, not a fork.
2. **Definitions are code.** Feature definitions live in a *feature repository*
   (Python modules + `shalf.yaml`) that is baked into images. Training jobs,
   the materialiser and the online server load the same code, so they cannot
   disagree about what a feature means.
3. **One transformation, two runtimes.** Derived and on-demand features are
   computed by the same function offline (training) and online (serving),
   which removes training/serving skew by construction.
4. **Config via environment.** `shalf.yaml` supports `${VAR:-default}`. In
   Kubernetes a ConfigMap overrides the file (`$SHALF_CONFIG`) and Secrets
   provide credentials.

## Packages

Libraries live in `packages/`. Each one is a separate distribution that
contributes to the `shalf.*` namespace package, so services install only what
they need. For example, the feature-server image contains `shalf-core` and
`shalf-data` but nothing from training.

```
shalf-core  <-  shalf-data  <-  shalf-training
                    ^      \
                    |       <-  shalf-serving  ->  shalf-models
shalf-monitoring, shalf-pipelines  ->  shalf-core
```

The uv workspace (`pyproject.toml` at the root) installs every package
editable into one `.venv` for development. `uv.lock` pins the whole graph.

## Runtime topology (Kubernetes)

```
 clients ──▶ inference-api ──▶ feature-server ──────────▶ Redis primary ◀──┐
             [serving]         [serving, HPA, PDB]                          │ writes
                                                         Redis replica      │
 notebooks ─────────────────▶ feature-server-eda ──────▶ (read-only)        │
   │                          [eda, profile=eda]                            │
   └──▶ offline reads ──▶ Parquet offline cache (RWX volume) ◀── feature-materializer
                                                                 [batch, CronJob]
                                                                       │
                                               source DB read replica ◀┘
[serving] / [batch] / [eda] = PriorityClass
```

| Workload               | Kind       | Image                  | Command                             |
| ---------------------- | ---------- | ---------------------- | ----------------------------------- |
| `feature-server`       | Deployment | `shalf-feature-server` | `uvicorn feature_server.app:app`    |
| `feature-materializer` | CronJob    | `shalf-feature-server` | `shalf-data materialize-incremental` |
| `feature-server-eda`   | Deployment | `shalf-feature-server` | same, with `SHALF_PROFILE=eda`      |
| `inference-api`        | Deployment | `shalf-inference-api`  | `uvicorn inference_api.app:app`     |

The long-running APIs are Deployments. Materialisation is a CronJob because it
is batch work: it runs, finishes and exits. If you prefer a single long-running
Deployment, run `materialize-incremental` in a loop instead; the watermark kept
in the online store makes repeated runs cheap and idempotent.

How serving is isolated from exploration and batch work is described in
[data-layer.md → Isolation](data-layer.md#isolation-serving-vs-exploration).
`deploy/k8s/jobs/backfill.yaml` is an on-demand Job for backfills after a
feature-logic change.

`deploy/k8s/overlays/dev` adds an in-cluster Redis plus a read replica and
runs one replica of everything. `overlays/prod` expects a `shalf-secrets`
Secret with `SHALF_REDIS_URL`, `SHALF_REDIS_REPLICA_URL` (and e.g.
`SHALF_PG_DSN`) and scales the feature server.

## Language choices

Everything is Python today. That was a deliberate default, revisited per
component:

| Component | Language | Why |
| --- | --- | --- |
| Feature definitions, transformations | Python (+ SQL snippets in `where`/`query`) | The users are data scientists. Feature code must be the same code they prototype with in notebooks, and the same function must run offline and online. |
| Heavy computation (aggregations, Parquet I/O) | SQL executed by **DuckDB** (C++) | Python orchestrates and the engine does the work. This is where the 11x speed-up comes from, without asking users to leave Python. |
| Source queries | SQL pushed down to the database | Filtering and projection belong in the database. |
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
3. Add a Deployment to `deploy/k8s/base` and an `images:` entry to each overlay.
