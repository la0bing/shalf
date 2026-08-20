# shalf

Monorepo holding all code for the project plus all of its specs and design docs.

> **Stack is not chosen yet.** `apps/` and `packages/` are placeholders. When the stack is
> decided, record it as an ADR (`/adr-new`) before adding workspace tooling.

## Repo map

| Path | What |
|---|---|
| `apps/` | Deployable applications. One directory per app. |
| `packages/` | Shared libraries consumed by `apps/`. |
| `docs/` | All specs, decisions, architecture and reference material. |
| `docs/INDEX.md` | One-line summary of every doc — **start here when looking for a doc.** |
| `.claude/` | Skills and slash commands that load docs on demand. |

## Where to look

| You need | Read |
|---|---|
| Any doc, unsure which | `docs/INDEX.md` |
| What this project is for | `docs/product/` |
| The spec for a feature | `docs/specs/` |
| How the system is built *today* | `docs/architecture/` |
| Why a technical choice was made | `docs/adr/` |
| Naming, file placement, commits | `docs/reference/conventions.md` |
| Domain vocabulary | `docs/reference/glossary.md` |
| How docs are organised and kept current | `docs/README.md` |

Skills load these automatically when relevant. Read `docs/INDEX.md` first if none fired.

## Working agreement

- Non-trivial work starts with a spec: `/spec-new <slug>`.
- **Before committing code, run `/docs-sync`.** It reconciles the diff against the docs that
  claim to describe it. This is not optional — stale docs actively mislead.
- Non-obvious technical decisions get an ADR: `/adr-new <slug>`.
- `docs/architecture/` describes reality. `docs/specs/` describes intent at a point in time.
  When a spec ships, `/spec-ship <id>` moves what is still true into architecture.

Commands: `/spec-new` `/adr-new` `/spec-ship` `/docs-sync` `/docs-audit` `/docs-index` `/skill-new`

## Context discipline — do not break these

This file and the skill descriptions are the only things loaded into *every* session. Everything
else must stay pay-per-use.

- **Never use `@path` imports here.** `@` inlines the file into every session at startup. Write
  paths as plain backticked text so they are read on demand.
- **Never paste doc content here.** This file is a router. Cap: ~60 lines.
- **One topic per doc, ~400 lines max.** Reading a doc is all-or-nothing.
- **Single source of truth.** Link between docs; never duplicate. Two copies means one is stale
  and nothing can tell you which.
- **Skills route, docs hold content.** A `SKILL.md` points at docs and describes procedure; it
  never explains subject matter. See `.claude/skills/docs-maintenance/SKILL.md`.
