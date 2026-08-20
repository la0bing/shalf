---
name: repo-conventions
description: Use when creating or naming files, deciding where something belongs in the monorepo, adding a workspace under apps/ or packages/, writing commit messages or PRs, or setting up local development.
---

# Repository conventions

Full detail: `docs/reference/conventions.md`. Vocabulary: `docs/reference/glossary.md`. Local
setup: `docs/guides/local-development.md` (nothing to run yet — there is no code).

The essentials, so you rarely need to open them:

## Where things go

| It is… | It goes in |
|---|---|
| A deployable application | `apps/<name>/` |
| Code shared by two or more workspaces | `packages/<name>/` |
| Used by exactly one app, and always will be | inside that app |
| Documentation | `docs/` — see `docs/README.md` for which subdirectory |

**Never create a package speculatively.** A package exists once a second workspace needs the code.
Moving it out later is mechanical; unwinding a premature abstraction is not.

## Naming

`kebab-case` for files and directories. Specs and ADRs carry a zero-padded numeric prefix:
`0007-deck-sharing-links.md`. Use the exact words from `glossary.md` — one concept, one name. A
concept with three names reads as three things.

## Adding a workspace

Beyond creating the directory, four steps are easy to miss and all matter:

1. Add a `CLAUDE.md` inside it (≤ ~40 lines). Claude Code loads it automatically when working in
   that directory — the cheapest possible place for local rules. State what the workspace is, its
   boundaries, its gotchas, and the specs governing it.
2. Add the workspace path to `components:` in every spec covering it. Without this the workspace
   is invisible to `/docs-sync` drift detection.
3. Add a row to the components table in `docs/architecture/system-overview.md`.
4. Wire it into workspace tooling — once a stack exists.

## Commits and PRs

Conventional Commits, scoped by workspace: `feat(web): add share-link expiry`. Types: `feat` `fix`
`docs` `refactor` `test` `chore` `perf` `build` `ci`. Imperative subject, no trailing period.

If the *why* needs more than a sentence, it belongs in an ADR, not a commit body.

PRs link the spec or ADR they implement, or state why there is none.

## Before committing

Run `/docs-sync`. See the `docs-maintenance` skill.
