---
description: Mark a spec shipped and fold its durable content into docs/architecture/
argument-hint: <spec id or slug>
---

Ship the spec identified by: **$ARGUMENTS**

A shipped spec stops describing reality and becomes a historical record of intent.
`docs/architecture/` takes over. This command performs that handover — the status flip alone is
not the point.

1. Locate the spec in `docs/specs/`.
2. Read it and identify what is **still true about the system as built**. Note where the
   implementation diverged from the spec — that divergence is the most valuable thing here and the
   easiest to lose.
3. Fold that content into `docs/architecture/system-overview.md`: update the components table,
   data flow, and external dependencies. Describe what exists, in the present tense. Do not copy
   the spec's aspirational phrasing across.
4. If the implementation diverged from the spec in a way that involved a real decision, propose an
   ADR via `/adr-new` and say why.
5. Set the spec's `status: shipped` and bump `updated:`. **Do not rewrite the spec body to match
   what was built** — it is a record of what was intended.
6. Bump `updated:` on `docs/architecture/system-overview.md`.
7. Run `/docs-index`.

Report what moved into architecture and any divergence worth an ADR.
