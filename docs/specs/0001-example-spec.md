---
status: draft
components: []
updated: 2026-08-21
summary: Worked example of the spec format; delete once real specs exist.
---

# Example spec

Exists so the format has a worked example, and so at least one spec exercises the docs-sync
lookup from a fresh clone. Delete once real specs exist.

## Problem

A template shows the shape of a spec but not the expected level of detail — the author of spec
0002 would have to guess.

## Approach

Keep one example in `status: draft` until real specs land. `components: []` keeps it invisible to
drift detection, so it never produces false positives.

## Rejected alternatives

A fabricated realistic feature spec — rejected because a plausible spec for a feature that does
not exist is exactly the stale-doc failure this repo avoids; a model reading it cannot tell it is
fiction.

## Acceptance

A reader can write spec 0002 from this plus `_TEMPLATE.md` without asking how much to write.
