# Architecture

**This file describes the system as it actually exists.** Specs record intent; this records
reality. If this file and the code disagree, the code is right and this file is a bug — fix it as
part of the change that broke it (see the `docs-sync` skill).

## Current state

Nothing is built. The repo contains docs structure and Claude Code wiring only — no application
code, no build tooling, no dependencies. The stack has not been chosen.

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

### Stack

TODO — not chosen. Record the choice and the runners-up here before adding workspace tooling.
