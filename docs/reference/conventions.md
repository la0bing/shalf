---
id: 0002
title: Repository conventions
type: reference
status: active
owner: la0bing
created: 2026-08-20
updated: 2026-08-20
components: []
related: [docs/README.md, docs/reference/glossary.md]
summary: Where files go, how things are named, and how commits and PRs are written.
tags: [reference, conventions]
---

# Repository conventions

## Where does this go?

| It is… | It goes in |
|---|---|
| A deployable application | `apps/<name>/` |
| Code shared by two or more workspaces | `packages/<name>/` |
| Used by exactly one app, and always will be | inside that app, not `packages/` |
| Intent for a feature not yet built | `docs/specs/` |
| A technical decision worth remembering | `docs/adr/` |
| A description of how the system works now | `docs/architecture/` |
| A how-to procedure | `docs/guides/` |
| A lookup table, glossary, or convention | `docs/reference/` |

**Do not create a package speculatively.** A package exists when a second workspace needs the
code. Until then it lives with its single consumer — moving it later is a small, mechanical
change; unwinding a premature abstraction is not.

## Naming

- Directories and files: `kebab-case`. Specs and ADRs are prefixed with a zero-padded number:
  `0007-deck-sharing-links.md`.
- Workspace names match their directory name exactly.
- Use the words in `glossary.md`. One concept, one name.

## Adding a workspace

1. Create `apps/<name>/` or `packages/<name>/`.
2. Add a `CLAUDE.md` inside it — Claude Code loads it automatically when working in that
   directory, so it is the cheapest place to put local rules. Keep it under ~40 lines: what the
   workspace is, its boundaries, gotchas, and the specs that govern it.
3. Add the workspace path to the `components:` of every spec that covers it. This is what makes
   `/docs-sync` able to see the workspace at all.
4. Add a row to the components table in `docs/architecture/system-overview.md`.
5. Wire it into the workspace tooling — once that exists.

## Commits

Conventional Commits, with the workspace as scope:

```
feat(web): add share-link expiry
fix(db): correct migration ordering
docs(specs): ship 0007-deck-sharing-links
chore(repo): add editorconfig
```

Types: `feat` `fix` `docs` `refactor` `test` `chore` `perf` `build` `ci`.

Subject in the imperative, no trailing period. Body explains *why* when it is not obvious from the
diff — and if the why is substantial, it belongs in an ADR, not a commit body.

## Pull requests

- Link the spec or ADR the work implements, or state why there is none.
- Confirm `/docs-sync` was run — the PR template asks.
- Keep PRs to one spec's worth of change where possible.

## Before you commit

Run `/docs-sync`. It maps the diff onto the docs that claim to describe the changed code and walks
you through reconciling them. Details in `docs/README.md`.
