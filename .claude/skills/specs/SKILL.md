---
name: specs
description: Use when starting non-trivial work, writing a new feature spec, finding the spec that governs a feature or file, or marking a feature shipped.
---

# Specs

One file per feature in `docs/specs/NNNN-slug.md` — intent at a point in time. `_TEMPLATE.md` is
the structure; `0001-example-spec.md` shows the expected depth.

## Finding one

`ls docs/specs/` — filenames say what each covers; the `summary:` frontmatter line says more.
Looking for the spec covering a file? `rg -l 'components:.*<workspace>' docs/specs/`.

Read the whole spec before implementing — the rejected alternatives are where the traps are.

## Writing one

1. Next number: highest prefix in `docs/specs/` + 1, zero-padded to 4 digits.
2. Copy `_TEMPLATE.md`, fill it in. Ask the user for what you can't infer; leave honest TODOs
   rather than inventing content.
3. `components:` lists the workspace paths this touches — it is how the docs-sync loop finds this
   spec when that code changes. Empty means invisible to drift detection.
4. `summary:` is one sentence for a reader deciding whether to open the file.

## Lifecycle

`draft` (being shaped) → `active` (being built) → `shipped` (done — historical record).

**On shipping:** move what is now true about the built system into `docs/architecture.md`
(components table, key decisions), then set `status: shipped`. Don't rewrite the spec body to
match what was built — it records what was intended; git and architecture.md record the rest.
A shipped spec no longer describes reality; `docs/architecture.md` does.
