---
id: 0001
title: Glossary
type: reference
status: draft
owner: la0bing
created: 2026-08-20
updated: 2026-08-20
components: []
related: []
summary: Canonical names for domain concepts, so code and docs use one word per thing.
tags: [reference, vocabulary]
---

# Glossary

Canonical vocabulary. Use these exact words in code, docs and commits — one word per concept. The
point is to stop the same thing acquiring three names across the codebase, which is expensive for
people and worse for a model, which will treat the synonyms as different things.

Add a term the moment a concept gets a second name.

## Repo terms

| Term | Means |
|---|---|
| **workspace** | One directory under `apps/` or `packages/` — the unit a spec's `components:` refers to. |
| **app** | A deployable workspace under `apps/`. |
| **package** | A shared library under `packages/`, consumed by apps or other packages. |
| **spec** | A document in `docs/specs/` capturing intent for one feature at a point in time. |
| **ADR** | Architecture decision record in `docs/adr/`; append-only, never edited once active. |
| **the loop** | spec → implement → `/docs-sync` → commit, with periodic `/docs-audit`. |
| **drift** | Code and the docs describing it having diverged. What `/docs-sync` prevents. |

## Domain terms

TODO — the words specific to what shalf does. Populate as the product takes shape; this is the
half of the glossary that earns its keep.

| Term | Means |
|---|---|
| — | — |
