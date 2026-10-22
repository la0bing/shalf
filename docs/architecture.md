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
               ┌──────────────── namespace: shalf ───────────────────┐
 clients ──▶ inference-api (Deployment) ──▶ feature-server (Deployment, HPA, PDB)
               │                                  │
               │                                  ▼
               │                           online store (Redis)
               │                                  ▲
               │      feature-materializer (CronJob, every 15 min)
               │                                  │
               └───────────────────── offline sources (Postgres, ...)
```

| Workload               | Kind       | Image                  | Command                             |
| ---------------------- | ---------- | ---------------------- | ----------------------------------- |
| `feature-server`       | Deployment | `shalf-feature-server` | `uvicorn feature_server.app:app`    |
| `feature-materializer` | CronJob    | `shalf-feature-server` | `shalf-data materialize-incremental` |
| `inference-api`        | Deployment | `shalf-inference-api`  | `uvicorn inference_api.app:app`     |

The long-running APIs are Deployments. Materialisation is a CronJob because it
is batch work: it runs, finishes and exits. If you prefer a single long-running
Deployment, run `materialize-incremental` in a loop instead; the watermark kept
in the online store makes repeated runs cheap and idempotent.

`deploy/k8s/overlays/dev` adds an in-cluster Redis and runs one replica of
everything. `overlays/prod` expects a `shalf-secrets` Secret with
`SHALF_REDIS_URL` (and e.g. `SHALF_PG_DSN`) and scales the feature server.

## Adding a new service

1. `services/<name>/` with a `pyproject.toml` depending on the workspace
   packages it needs and a `src/<module>/app.py`.
2. Build with `make docker-build SERVICE=<name>`.
3. Add a Deployment to `deploy/k8s/base` and an `images:` entry to each overlay.
