---
id: 0001
title: Example spec
type: spec
status: draft
owner: la0bing
created: 2026-08-20
updated: 2026-08-20
components: []
related: [docs/adr/0001-record-architecture-decisions.md]
summary: Worked example showing the spec format and lifecycle; delete once real specs exist.
tags: [meta, example]
---

# Example spec

This file exists so the format has a worked example rather than only a blank template. Delete it
once there are real specs.

## Problem

A template shows the shape of a document but not the level of detail expected in it. Someone
writing spec `0002` has to guess how much to write, and guesses vary.

## Goals

- Show what a filled-in section actually looks like.
- Exercise `/docs-index` and `/docs-sync` with at least one real entry, so both are testable from
  a fresh clone.

## Non-goals

- Describing anything about the real product. There is no product code yet.
- Serving as a style guide for prose. Only the structure is prescriptive.

## Proposed approach

Keep one example spec in `status: draft` until real specs land. Because `components: []`, it is
invisible to drift detection and never produces false positives in `/docs-sync`.

## Alternatives considered

**Template only, no example.** Rejected: leaves `INDEX.md` empty, so nothing exercises the index
generation or the sync loop until the first real feature — which is exactly when a broken loop is
most expensive to discover.

**A fabricated realistic feature.** Rejected: a plausible-looking spec for a feature that does not
exist is precisely the stale-doc failure this repo is built to avoid. A model reading it would
have no way to tell it was fiction.

## Risks and open questions

- [ ] Delete this file once the first real spec is written — tracked by `/docs-audit`, which flags
      `status: draft` specs that have gone stale.

## Acceptance

- `/docs-index` lists this file with its summary.
- A reader can write a new spec from this plus `_TEMPLATE.md` without asking how much to write.
