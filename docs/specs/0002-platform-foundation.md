---
status: active
components: [packages/core, packages/sdk, deploy]
updated: 2026-08-21
summary: Blueprint for the modular ML platform — the spine, the building blocks and their boundaries, the repo layout, and the foundation to build first.
---

# Platform foundation & module blueprint

## Problem

shalf aims to cover the whole ML lifecycle — development (EDA, training, validation), delivery
(batch pipelines, REST hosting), operation (experiment tracking, registry, drift detection). One
team cannot build that at once, and different users need different subsets. Without an agreed
decomposition, the first blocks built will entangle (tracking reaching into serving's tables,
serving importing training code) and the "pick the blocks you need" promise dies early. There is
also nothing to run: no shared contracts, no storage, no deployment skeleton for a first block to
land on.

## Approach

### The spine

Three capabilities every deployment runs, owned by `packages/core` as interfaces with pluggable
backends:

| Capability | Interface owner | Local backend | Production backend |
|---|---|---|---|
| Metadata store | `packages/core` | PostgreSQL (compose) | PostgreSQL (managed or in-cluster) |
| Artifact store | `packages/core` | Filesystem volume or any S3-compatible store | Any S3-compatible object store |
| Event bus | `packages/core` | Postgres-backed queue | Postgres-backed queue (interface allows swapping later) |

One PostgreSQL instance, one schema per block — blocks never read another block's schema.
The event bus starts as a Postgres outbox/queue; the interface is the contract, so a
Redis/NATS/Kafka backend can be added later without touching block code.

### The blocks

| Block | Responsibility |
|---|---|
| `experiments` | Experiment & run tracking: params, metrics, artifacts, comparisons |
| `registry` | Model versioning, lineage back to runs, stage promotion |
| `serving` | Hosting registered model versions as REST endpoints |
| `pipelines` | Batch pipeline definition, scheduling, execution |
| `monitoring` | Drift detection, data quality, model performance over time |
| `workbench` | Development experience: EDA project scaffolding, notebook integration |
| `gateway` | Optional single entry point: auth, routing, eventually a UI |

### Composition rules

These are the load-bearing constraints; a change that violates one is an architecture change,
not a shortcut.

1. A block is a FastAPI service in `apps/<block>/` with its own Dockerfile, plus an optional
   extra in `packages/sdk` (`pip install shalf[experiments]`).
2. A block imports `packages/core` and nothing from any other block.
3. Cross-block integration uses the other block's published REST API or spine events — e.g.
   `registry` links a model version to a run by run ID via the experiments API, never via its
   tables.
4. Every block runs standalone on spine + itself. If it degrades without a sibling block, it
   degrades gracefully (a registry without experiments still registers models — lineage fields
   stay empty).
5. Configuration is environment variables prefixed `SHALF_<BLOCK>_`; spine config is `SHALF_CORE_`.

### Repo layout (target)

```
apps/<block>/          one FastAPI service + Dockerfile per block
packages/core/         contracts (Pydantic models), spine interfaces, backend adapters
packages/sdk/          `shalf` client library; one optional extra per block
deploy/compose/        docker-compose.yml — spine always on, one profile per block
deploy/k8s/shalf/      umbrella Helm chart — one <block>.enabled flag per block
```

uv workspaces tie `apps/*` and `packages/*` together. Deployment conventions and the
block-onboarding checklist live in `docs/deployment.md`.

### What "foundation" means concretely

The work this spec governs, in order:

1. `packages/core`: uv workspace setup; spine interfaces (metadata session, artifact store,
   event bus) with the Postgres/filesystem/S3-compatible backends; shared Pydantic contract
   models; pytest wiring.
2. `deploy/compose`: spine services (PostgreSQL, object store) running via `docker compose up`;
   profile mechanism proven with a placeholder healthcheck.
3. `deploy/k8s/shalf`: umbrella chart with spine + the `<block>.enabled` switchboard.
4. `packages/sdk`: the `shalf` client package skeleton (auth/transport plumbing, no block extras
   yet).

The first block, `experiments`, gets its own spec (0003) and is not part of this one.

## Rejected alternatives

- **Assemble open-source tools** (MLflow + Airflow + Seldon + Evidently): permanent integration
  tax, upstream churn sets the roadmap, and the result is a distribution, not a product. Decision
  recorded in `docs/architecture.md`.
- **Monolith with feature flags**: simplest to start, but blocks can't be deployed, scaled, or
  versioned independently — the composability promise becomes marketing.
- **Microservice per entity, database per service**: maximal isolation shalf doesn't need at this
  scale; one Postgres with schema-per-block gives the same boundary at a fraction of the
  operational cost.
- **One SDK package per block**: users juggle version matrices across N packages; a single
  `shalf` package with extras keeps installs composable and releases atomic.
- **Kafka/NATS event bus from day one**: heavy spine dependency before any block emits events;
  the interface keeps the door open.

## Acceptance

- `packages/core` exists with the three spine interfaces, at least one working backend each, and
  passing tests.
- `docker compose up` in `deploy/compose` brings up the spine locally with no block enabled.
- The Helm umbrella chart installs the spine on a cluster with every `<block>.enabled=false`.
- The `experiments` block (spec 0003) can be built against this foundation without modifying
  `packages/core` beyond adding its contract models.
