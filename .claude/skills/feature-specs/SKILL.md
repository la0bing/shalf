---
name: feature-specs
description: Use when implementing, reviewing, or writing a feature spec — finding the spec that governs a feature or file, creating a new one, or handling the spec lifecycle (draft, active, shipped, superseded).
---

# Feature specs

Specs live flat in `docs/specs/NNNN-slug.md`. Each one captures **intent at a point in time** for
one feature, and declares which workspaces it touches via `components:` frontmatter.

## Finding the spec for something

1. `docs/INDEX.md` — one line per doc with a summary. Scan it first; it is far cheaper than
   grepping the tree.
2. Looking for the spec covering a *file*? Grep `components:` for its workspace path:
   `rg -l 'components:.*packages/db' docs/`
3. Only then search spec bodies by keyword.

Read the whole spec before implementing from it — the non-goals and alternatives sections are
where the traps are, and they are the parts most often skipped.

## Writing one

Run `/spec-new <slug>`. It allocates the next number, fills the frontmatter, and updates the
index. `docs/specs/_TEMPLATE.md` is the structure; `docs/specs/0001-example-spec.md` shows the
expected level of detail.

Two fields do real work and are worth getting right rather than filling in:

- **`summary`** is copied verbatim into `INDEX.md`. Write it for someone deciding whether to open
  the file — not as a restatement of the title.
- **`components`** lists the workspace paths this spec describes. It is the join key `/docs-sync`
  uses to detect drift. An empty or wrong `components` makes the spec invisible to drift detection.

## Lifecycle

| Status | Meaning |
|---|---|
| `draft` | Being shaped. Not agreed. |
| `active` | Agreed; being implemented. |
| `shipped` | Built. **Historical record — no longer describes the system.** |
| `superseded` | Replaced. `related:` points at the replacement. |

**A shipped spec does not describe reality.** `docs/architecture/` does. When a feature ships, run
`/spec-ship <id>`: it flips the status and prompts for what should be folded into
`docs/architecture/system-overview.md`.

So: if you are asked how the system currently behaves, read `docs/architecture/`, not a spec. If
you are asked what was intended or why, read the spec.

## Related

- `/docs-sync` before committing — reconciles your diff against affected specs.
- Technical decisions belong in `docs/adr/`, not in spec bodies — see the `architecture` skill.
