# Conventions

## Where things go

| It is… | It goes in |
|---|---|
| A deployable application | `apps/<name>/` |
| Code shared by two or more workspaces | `packages/<name>/` |
| Used by exactly one app | inside that app — don't create a package speculatively |
| Intent for a feature | `docs/specs/NNNN-slug.md` |
| How the system works now, and key decisions | `docs/architecture.md` |

A package exists when a *second* workspace needs the code. Moving it out later is mechanical;
unwinding a premature abstraction is not.

## Naming

`kebab-case` files and directories. Specs carry a zero-padded number: `0007-deck-sharing.md`.
One concept, one name — a thing with three names reads as three things.

## Adding a workspace

1. Create the directory, plus a short `CLAUDE.md` inside it (loads automatically when working
   there): what it is, boundaries, gotchas, governing specs. ~40 lines max.
2. Add its path to the `components:` of every spec that covers it — this is how doc updates get
   found when its code changes.
3. Add a row to the components table in `docs/architecture.md`.

## Commits

Conventional Commits, workspace as scope: `feat(web): add share-link expiry`. Imperative subject,
no trailing period. If the *why* needs more than a sentence, it belongs in `docs/architecture.md`
Key decisions, not a commit body.

Before committing code: update the docs (see the `docs-sync` skill).
