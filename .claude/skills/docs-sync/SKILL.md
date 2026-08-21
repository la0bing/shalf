---
name: docs-sync
description: Use after changing code and before committing, or whenever docs may be stale or contradict the code — reconciles the docs that describe the changed code.
---

# Docs sync — run before every commit that touches code

Stale docs are worse than none: a model can't tell a doc is out of date and will follow it into
the wrong design. This is the loop that keeps `docs/` describing *now* (git history keeps the
past — never preserve outdated prose for the record).

## Procedure

1. **Collect the diff**: `git status --porcelain` + `git diff --name-only origin/main...HEAD`.
   Ignore changes confined to `docs/`.
2. **Find affected specs**: for each changed workspace path,
   `rg -l 'components:.*<workspace>' docs/specs/`. A workspace no spec mentions is a finding too —
   add it to the right spec's `components:`.
3. **Reconcile each affected spec**: does the code still do what it says? Update what's wrong,
   bump `updated:`. Feature now fully built → ship it (see the `specs` skill).
4. **`docs/architecture.md`**: structure, a boundary, or a data flow changed → update it. A
   technical decision worth remembering was made or reversed → edit Key decisions in place.
5. **New workspace added** → `components:` on relevant specs, a row in architecture.md, and a
   short `CLAUDE.md` inside the workspace (see `docs/conventions.md`).

## Report

Say what you updated and what you checked and found already accurate. Nothing affected is a valid
outcome — say so plainly; don't manufacture an edit.
