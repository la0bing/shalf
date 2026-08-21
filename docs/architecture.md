# Architecture

**This file describes the system as it actually exists.** Specs record intent; this records
reality. If this file and the code disagree, the code is right and this file is a bug — fix it as
part of the change that broke it (see the `docs-sync` skill).

## Current state

No application code yet. The repo contains docs, the platform blueprint
(`docs/specs/0002-platform-foundation.md`), deployment conventions (`docs/deployment.md`), and
Claude Code wiring. The stack is chosen (see Key decisions); the foundation described in spec
0002 is the next thing to build.

## Components

None yet. Each workspace added under `apps/` or `packages/` gets a row here.

| Workspace | Responsibility | Depends on |
|---|---|---|
| — | — | — |

## Key decisions

One short entry per decision worth remembering: what was decided, why, and what was rejected.
Edit an entry in place when the decision changes — git history is the archive. Check here before
proposing a technical choice; re-litigating a settled decision wastes a session.

### Docs live in the monorepo, loaded on demand

Specs and docs live beside the code, structured so nothing loads into LLM context until needed
(`CLAUDE.md` routes, skills point, docs hold content). Rejected: wikis/Notion (invisible to the
model and to git), and inlining docs into `CLAUDE.md` (every session pays for every doc).

### Stack: Python everywhere

Python 3.12+ for all platform services and the SDK: FastAPI + Pydantic for services and
contracts, uv workspaces for monorepo packaging, pytest for tests. One language keeps the
codebase in the ecosystem its users live in, and lets service code and SDK share the contract
models in `packages/core`. Rejected: Go control-plane + Python SDK (smaller images, but two
toolchains and duplicated contracts); TypeScript services (splits the repo away from ML).

### Build the platform, don't wrap open source

Platform capabilities (tracking, registry, serving, drift detection…) are implemented in this
repo — no wrapping, forking, or hard dependency on MLflow, Kubeflow, Airflow, Seldon, and kin.
Infrastructure *primitives* are fair game: PostgreSQL, S3-compatible object storage, Kubernetes.
Backends sit behind interfaces owned by `packages/core`, so any single primitive is swappable.
Rejected: assembling an OSS stack (permanent integration tax, upstream churn dictates our
roadmap, nothing differentiated to own).

### Building blocks: spine + independent blocks

The platform is a small **spine** every deployment runs — metadata store (PostgreSQL, one schema
per block), artifact store (object-storage interface; filesystem or any S3-compatible backend),
event bus (Postgres-backed initially, behind an interface) — plus independent **blocks**
(experiments, registry, serving, pipelines, monitoring, workbench, gateway). A block is a FastAPI
service under `apps/<block>/` plus an optional extra in the single `packages/sdk` client. Blocks
depend only on `packages/core`, never on each other's code; cross-block integration goes through
published REST APIs and spine events. Any subset of blocks is a valid deployment. Full blueprint:
`docs/specs/0002-platform-foundation.md`. Rejected: a monolith with feature flags (can't ship
blocks independently), one microservice per entity with its own database (operational overhead
without composability gain), a mandatory framework-style SDK (locks user code in).

### Two deployment targets, every block ships both

Local development runs on Docker Compose (one file, one profile per block; the spine is always
on). Production runs on Kubernetes via a single umbrella Helm chart with a `<block>.enabled`
flag per block. A block is not done until it works in both. Conventions and the
block-onboarding checklist: `docs/deployment.md`. Rejected: compose-only (no prod story),
raw K8s manifests per block (drifts from compose, no single composition switchboard).

### Delivery order: experiments first

Blocks land one at a time: foundation → **experiments** (run tracking) → registry → serving →
pipelines → monitoring → workbench/gateway. Tracking comes first because registry, serving, and
drift all hang off tracked runs and models, and it proves the block model end to end. Priorities
live in `docs/product.md`; revisit there, not here.
