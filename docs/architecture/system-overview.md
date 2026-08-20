---
id: 0001
title: System overview
type: architecture
status: draft
owner: la0bing
created: 2026-08-20
updated: 2026-08-20
components: []
related: [docs/adr/0001-record-architecture-decisions.md]
summary: How the system is built today — currently nothing but the repo skeleton exists.
tags: [architecture]
---

# System overview

**This file describes the system as it actually exists.** It is the only doc that claims to
describe reality: `docs/specs/` records intent at a point in time, and `docs/adr/` records why
choices were made. When a spec ships, whatever is still true about the built system moves here.

## Current state

Nothing is built. The repository contains documentation structure and Claude Code wiring only:

```
apps/       empty placeholder
packages/   empty placeholder
docs/       this tree
.claude/    skills + commands
```

No application code, no build tooling, no runtime dependencies, no deployment. The technology
stack has not been chosen — that decision will arrive as an ADR.

## Components

None yet. As workspaces are added, each gets an entry here: what it is, what it depends on, and
what depends on it.

| Workspace | Kind | Responsibility | Depends on |
|---|---|---|---|
| — | — | — | — |

## Data flow

None yet.

## External dependencies

None yet — no third-party services, datastores, or APIs.

## Keeping this accurate

`/docs-sync` prompts for an update here whenever a change alters system structure, a boundary, or
a data flow. If this file and the code disagree, the code is right and this file is a bug.
