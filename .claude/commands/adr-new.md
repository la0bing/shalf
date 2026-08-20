---
description: Record an architecture decision in docs/adr/
argument-hint: <slug>
---

Create a new ADR for: **$ARGUMENTS**

First, check whether this ground is already covered: `rg -li '<topic>' docs/adr/`. If an existing
ADR decides it, do not write a new one unless this genuinely supersedes it — say which ADR already
applies and stop.

1. Next number: highest numeric prefix in `docs/adr/[0-9]*.md` plus one, zero-padded to 4 digits.
2. Copy `docs/adr/_TEMPLATE.md` to `docs/adr/<NNNN>-<slug>.md`.
3. Title it as a **statement of the decision**, not a question: "Use Postgres for primary storage",
   not "Which database?".
4. Fill in Context (the forces that made a decision necessary, written for someone who was not
   there), Decision, Consequences, and Alternatives considered.
5. **Consequences must include the downsides** — what gets harder, what is now locked in, what
   reversing it would cost. An ADR listing only upsides is an advert, not a record.
6. Interview the user for reasoning you do not have. Do not invent rationale; a fabricated reason
   in an ADR outlives everyone's memory of it being fabricated.
7. If this supersedes an existing ADR: set the old one's `status: superseded` and point its
   `related:` at the new file. **Do not edit the old ADR's decision or reasoning** — the record is
   append-only.
8. Set `status: active` if the decision is made, `draft` if still under discussion.
9. Run `/docs-index`.
