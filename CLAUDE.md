# shalf

Monorepo: all code for the project plus its specs and docs.

> **Stack not chosen yet.** `apps/` and `packages/` are empty placeholders. Record the stack
> decision in `docs/architecture.md` before adding workspace tooling.

## Where to look

| You need | Read |
|---|---|
| What the project is for, priorities | `docs/product.md` |
| The spec for a feature | `docs/specs/` — filenames + `summary:` frontmatter say what each covers |
| How the system is built today, and why | `docs/architecture.md` |
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
