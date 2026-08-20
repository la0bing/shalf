---
description: Regenerate docs/INDEX.md from every doc's frontmatter
---

Regenerate `docs/INDEX.md` from the frontmatter of every document under `docs/`.

1. Find all `docs/**/*.md`, excluding `README.md`, `INDEX.md`, and any `_TEMPLATE.md`.
2. Read the frontmatter of each: `title`, `type`, `status`, `summary`, `updated`, `components`.
3. Write `docs/INDEX.md` with a short generated-file header, then one section per `type` value in
   this order — `product`, `spec`, `architecture`, `adr`, `guide`, `reference` — each a table.
   These are the singular `type` values from the frontmatter, not the plural directory names; a
   `type` outside this list gets its own section at the end. Section headings are:
   Product, Specs, Architecture, Decisions (ADR), Guides, Reference.

   | Doc | Status | Summary |
   |---|---|---|
   | [`title`](<relative-path>.md) | `status` | summary |

   Within a section, sort by path. Copy `summary` **verbatim** from the frontmatter — do not
   paraphrase, shorten, or improve it. Divergence between this file and the source frontmatter is
   what makes the index untrustworthy.
4. If a doc is missing `summary` or `title`, list it under a **Needs frontmatter** section at the
   bottom rather than skipping it silently.

This file is generated. Never hand-edit it — edit the source doc's frontmatter and re-run this.

Report how many docs were indexed and any that need frontmatter.
