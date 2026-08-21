# Product

## What shalf is

shalf is a self-built, modular, end-to-end machine-learning platform. It covers the full model
lifecycle — development (EDA, training, validation), delivery (batch pipelines, REST model
hosting), and operation (experiment tracking, model registry, drift detection and monitoring) —
as independent **building blocks** a team composes: run only the blocks you need, locally with
Docker Compose or in production on Kubernetes. Capabilities are implemented in this repo, not
assembled from open-source ML platforms; interfaces stay agnostic so infrastructure backends
(databases, object stores, queues) remain swappable.

The scope is large by design; blocks are delivered one at a time in the priority order below.

## Non-goals

- **Not a distribution of open-source ML tools.** No wrapping or forking of MLflow, Kubeflow,
  Airflow, Seldon, Evidently, etc. Infrastructure primitives (PostgreSQL, object storage,
  Kubernetes) are fair game; ML-platform *solutions* are not.
- **Not a data platform.** No warehouse, feature-store-as-database, labeling, or annotation
  tooling. shalf consumes data where it lives.
- **Not a general-purpose workflow engine.** Pipelines exist to run ML batch work, not arbitrary
  business processes.
- **Not AutoML.** shalf runs and tracks the user's training code; it does not write it.
- **No lock-in of user code.** Models and training scripts stay plain Python; the SDK is a thin
  client, not a framework users must inherit from.

## Priorities

**Now**
- Platform foundation: `packages/core` contracts, the platform spine (metadata store, artifact
  store, event bus interfaces), and the two deployment skeletons — see
  `docs/specs/0002-platform-foundation.md`.
- First block: **experiments** (experiment & run tracking) — proves the block model end to end.

**Next**
- **registry** — model versioning, lineage, stage promotion.
- **serving** — hosting registered models as REST APIs.

**Later**
- **pipelines** — batch pipeline definition, scheduling, execution.
- **monitoring** — drift detection, data quality, model performance.
- **workbench** — development experience: EDA project scaffolding, notebook integration.
- **gateway** — single entry point: auth, routing, eventually a UI.
