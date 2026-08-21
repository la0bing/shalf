# shalf

Monorepo: a self-built, modular, end-to-end ML platform — independent building blocks
(experiments, registry, serving, pipelines, monitoring…) on a shared spine.

> Stack: Python 3.12+/FastAPI/uv — decision records in `docs/architecture.md`. `apps/` and
> `packages/` are still empty; the foundation lands per `docs/specs/0002-platform-foundation.md`.

## Where to look

| You need | Read |
|---|---|
| What the project is for, priorities | `docs/product.md` |
| The spec for a feature | `docs/specs/` — filenames + `summary:` frontmatter say what each covers |
| Block boundaries, spine, composition rules | `docs/specs/0002-platform-foundation.md` |
| How the system is built today, and why | `docs/architecture.md` |
| Running locally, K8s, compose/Helm conventions | `docs/deployment.md` |
| Naming, file placement, commits | `docs/conventions.md` |

## Working rules

- Non-trivial work starts with a spec in `docs/specs/` (copy `_TEMPLATE.md`, next number).
- **Every code change ends by updating the docs that describe it** — the `docs-sync` skill has
  the procedure. Stale docs actively mislead; git history is the archive, docs describe *now*.
- Decisions worth remembering go in the "Key decisions" section of `docs/architecture.md`.
  Edit in place when they change — git keeps the history.

## Context discipline

Only this file and skill descriptions load into every session; docs load on demand.

- Never use `@path` imports here — `@` inlines the file into every session. Plain backticked
  paths only.
- Never paste doc content here. This file is a router, ~40 lines max.
- One topic per doc. Skills point at docs; they never explain subject matter themselves.
