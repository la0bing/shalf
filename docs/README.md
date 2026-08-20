# How documentation works in this repo

Docs live beside the code they describe, in one tree, under two rules:

1. **A doc costs nothing until it is relevant.** Nothing here is loaded into an LLM's context by
   default — retrieval is explicit, via skills and `INDEX.md`.
2. **A doc is never allowed to go stale.** Stale docs are worse than no docs: a model cannot tell
   that a file is out of date and will follow it confidently into the wrong design.

Rule 2 is the hard one, so it is enforced by a loop rather than by discipline. See
[The loop](#the-loop) below.

## The tree

| Directory | Holds | Lifetime |
|---|---|---|
| `product/` | Vision, roadmap — the *why* | Living |
| `specs/` | One file per feature — *intent at a point in time* | Frozen once shipped |
| `adr/` | Architecture decision records — *why a choice was made* | Append-only |
| `architecture/` | How the system is built **today** — the *what* | Living |
| `guides/` | How-to: local dev, testing, release | Living |
| `reference/` | Conventions, glossary | Living |

`INDEX.md` is generated. Do not hand-edit it; run `/docs-index`.

### specs vs. architecture — the distinction that keeps docs honest

A **spec** captures what you intended to build, at the moment you decided it. Once the feature
ships the spec stops being true about the world — it stays as a record of intent and of the
reasoning at that time.

**`architecture/` is the only place that claims to describe reality.** When a spec ships,
`/spec-ship <id>` marks it `shipped` and moves whatever is still true into `architecture/`.

**ADRs are append-only.** Never edit a decided ADR. Write a new one, and mark the old one
`status: superseded` with `related:` pointing forward. The wrong turns are part of the value —
they are what stop the same debate being reopened in six months.

## Adding a doc

Use `/spec-new <slug>` or `/adr-new <slug>`; both allocate the next number and fill the
frontmatter. For other types, copy an existing file's frontmatter block. Every doc under `docs/`
except `README.md` and `INDEX.md` **must** carry it:

```yaml
---
id: 0007                    # zero-padded; specs and ADRs number independently
title: Deck sharing links
type: spec                  # spec | adr | architecture | guide | reference | product
status: draft               # draft | active | shipped | superseded
owner: la0bing
created: 2026-08-20
updated: 2026-08-20
components: [apps/web, packages/db]      # workspace paths this doc describes; [] if none yet
related: [docs/adr/0003-storage-choice.md]
summary: One sentence, copied verbatim into INDEX.md.
tags: [sharing, auth]
---
```

Three fields carry weight:

- **`summary`** is what makes `INDEX.md` useful — a reader (human or model) scans one-liners and
  opens exactly one file instead of searching blind. Write it for someone deciding whether to open
  the doc, not as a title restatement.
- **`status`** stops a shipped spec from reading like a plan.
- **`components`** is the join key between code and docs. `/docs-sync` uses it to map a changed
  file back to the docs claiming to describe it. A doc with an empty or wrong `components` is
  invisible to drift detection.

### Why specs are central, not per-package

A feature routinely spans several workspaces, so a spec cannot live inside "its" package. Specs
stay flat in `specs/` and reach outward through `components:`. The link runs back the other way
through each package's own `CLAUDE.md`, which names the specs that govern it.

## The loop

```
  /spec-new  ──▶  implement  ──▶  /docs-sync  ──▶  commit / PR
      ▲                                │
      └────────  /docs-audit  ◀────────┘   (periodic, whole-tree)
```

**1. Spec first.** Anything non-trivial starts with `/spec-new`. `draft` while shaping, `active`
when work starts. Trivial fixes skip this — the spec exists to capture intent worth remembering,
not to add ceremony.

**2. Implement.**

**3. `/docs-sync` before committing.** The heart of the loop, and diff-driven so it is mechanical
rather than a memory exercise: it reads the changed paths, matches them against `components:`
across the tree, and walks each affected doc, plus architecture impact, ADR-worthy decisions,
shipped specs, and the index.

**4. `/docs-audit` periodically.** Monthly, before a release, or whenever the docs stop feeling
trustworthy. Whole-tree health check: broken links, index drift, schema violations, dead
`components:` entries, orphans, oversized skills.

Three advisory backstops keep step 3 from being skipped: a `Stop` hook that notices code changed
without docs changing, a PR-template checkbox, and a warn-only CI check for changes made outside
Claude Code. None of them block.

## How docs reach the model

`.claude/skills/*/SKILL.md` — only each skill's `name` and `description` sit in context
(~50 tokens each); the body loads when the description matches what is being worked on, and the
docs it links to load only if that body points at them. Total standing cost for the whole system
is around 1k tokens regardless of how large this tree grows.

**Growth rule:** add a skill when a docs domain passes ~5 docs, or when a recurring question keeps
missing every existing skill. Until then `guides/` is routed through `repo-conventions`; it splits
into its own `dev-workflows` skill once the local-dev / testing / release guides are real.

Authoring and maintaining skills is covered in `.claude/skills/docs-maintenance/SKILL.md`.
