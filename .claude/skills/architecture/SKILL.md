---
name: architecture
description: Use when changing system structure, adding a workspace or service, choosing a dependency or technology, or when you need to know how the system works today or why an existing technical decision was made.
---

# Architecture and decisions

Two directories, two different jobs. Picking the wrong one wastes a read.

| You need | Read |
|---|---|
| How the system is built **today** | `docs/architecture/system-overview.md` |
| **Why** a choice was made, or what was rejected | `docs/adr/NNNN-*.md` |
| What was *intended* for a feature | `docs/specs/` — the `feature-specs` skill |

`docs/architecture/` is the only place claiming to describe reality. A `shipped` spec is history.

## Before proposing a technical change

**Check whether it was already decided.** `rg -l '<topic>' docs/adr/` and scan `docs/INDEX.md`.
Re-proposing a rejected option is the specific failure ADRs exist to prevent — the alternatives
section of an ADR usually contains the answer, including a reason that may still be valid.

If an ADR covers it and the reasoning still holds, follow it. If the reasoning no longer holds,
that is a new ADR superseding the old one — not an edit.

## Writing an ADR

`/adr-new <slug>`. Warranted when a decision is hard to reverse, affects more than one workspace,
constrains future choices, or would surprise someone six months from now. Not warranted for
choices that are obvious, local, and cheap to change.

**ADRs are append-only.** Never edit a decided ADR to change its decision. Write a new one, then
set the old to `status: superseded` with `related:` pointing forward. Record the bad consequences
too — an ADR listing only upsides is an advert, not a record.

## Keeping the overview honest

`docs/architecture/system-overview.md` must be updated whenever a change alters system structure,
a workspace boundary, or a data flow. `/docs-sync` prompts for this. If the file and the code
disagree, the file is a bug.

## Current state

Nothing is built yet — no application code, no dependencies, and **the technology stack has not
been chosen**. That decision is itself an ADR and should be written before any workspace tooling
is added. Do not assume a stack from file extensions or from what is conventional.
