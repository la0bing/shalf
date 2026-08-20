---
name: project-context
description: Use when you need to know what shalf is, who it is for, what it deliberately does not do, or what the current priorities are — before proposing product-level changes, judging whether something is in scope, or picking what to work on next.
---

# Project context

Product-level intent lives in `docs/product/`. Read the file you need; do not read both by reflex.

| Question | Read |
|---|---|
| What is shalf, who is it for, what problem does it solve? | `docs/product/vision.md` |
| Is this in scope? | `docs/product/vision.md` — the non-goals section |
| What should be worked on now? What was deferred, and what was declined? | `docs/product/roadmap.md` |

## Important: these are currently unfilled

Both files are stubs marked `status: draft`, with `TODO` placeholders instead of content. There is
no product definition yet.

**Do not infer the product from the repository.** If you need product context and it is still
unfilled, say so and ask — a guess written down becomes a fact nobody remembers guessing.

If the user supplies the answers, offer to fill in the stub properly and bump its `updated:` date.

## Related

- Concrete feature intent, as opposed to product direction, is in `docs/specs/` — see the
  `feature-specs` skill.
- Why technical choices were made: `docs/adr/` — see the `architecture` skill.
