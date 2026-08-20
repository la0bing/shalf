---
id: 0001
title: Record architecture decisions as ADRs
type: adr
status: active
owner: la0bing
created: 2026-08-20
updated: 2026-08-20
components: []
related: [docs/README.md]
summary: Significant technical decisions are recorded as append-only ADRs in docs/adr/.
tags: [meta, process]
---

# Record architecture decisions as ADRs

## Status

`active`.

## Context

This project is built largely through Claude Code. A model reading the repo can see *what* the
code does but not *why* it is that way. Without a written record it re-derives reasoning from
scratch each session, and will cheerfully propose an option that was already considered and
rejected — sometimes the one rejected for a reason that is still valid.

Commit messages and PR descriptions are the usual fallback and are a poor one: they are scattered,
tied to one diff, and effectively unsearchable by the time they matter.

## Decision

Significant technical decisions are recorded as numbered ADRs in `docs/adr/`, one file per
decision, using `docs/adr/_TEMPLATE.md`. "Significant" means: hard to reverse, affects more than
one workspace, constrains future choices, or would otherwise surprise someone six months from now.

ADRs are append-only. A decided ADR is never edited to change the decision — a new ADR supersedes
it, and the old one is marked `status: superseded` with `related:` pointing forward.

## Consequences

- The reasoning behind the system is retrievable, by a person or a model, without archaeology.
- Rejected options stay visible, so settled debates stay settled.
- Small cost per decision: one file, written while the reasoning is fresh.
- Append-only means the directory only grows, and some entries will be historical rather than
  current. `status` and `related:` are what distinguish the two — they have to be kept accurate,
  which `/docs-audit` checks.

## Alternatives considered

**Nothing — rely on code, commits and PRs.** Rejected: this is the status quo that produces the
re-derivation problem above.

**A single running decisions log.** Rejected: it grows unboundedly and must be read in full to
find one decision, which is the token cost this repo's whole docs design exists to avoid. One file
per decision means one file gets read.
