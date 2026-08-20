---
description: Whole-tree health check of docs, specs and skills
---

Audit the whole documentation tree. Run monthly, before a release, or when the docs stop feeling
trustworthy. Unlike `/docs-sync`, this is not diff-scoped.

Optional scope limit: $ARGUMENTS

Check each of the following and report findings grouped by severity. **Do not fix anything yet** —
present the list, then ask which to fix.

## Integrity

1. **Broken links** — every path referenced in `docs/**`, `.claude/skills/*/SKILL.md`,
   `.claude/commands/*.md`, and `CLAUDE.md` that does not exist on disk.
2. **Index drift** — compare `docs/INDEX.md` against `find docs -name '*.md'`: missing rows,
   phantom rows, summaries that no longer match the file's frontmatter.
3. **Frontmatter** — every `docs/**/*.md` except `README.md` and `INDEX.md` must open with `---`
   and carry `id`, `title`, `type`, `status`, `owner`, `created`, `updated`, `summary`. Flag
   invalid `type` or `status` values.
4. **Dead components** — `components:` entries naming paths that no longer exist under `apps/` or
   `packages/`.
5. **Invisible workspaces** — directories under `apps/` or `packages/` that no doc's `components:`
   mentions. These are drift-detection blind spots. Also flag any missing a `CLAUDE.md`.

## Accuracy

6. **Stale specs** — `status: active` whose `components:` code has changed substantially since the
   spec's `updated:` date; `status: shipped` whose content was never folded into
   `docs/architecture/`; `status: draft` untouched for a long time.
7. **Architecture drift** — does `docs/architecture/system-overview.md` list every workspace that
   exists, and only those?
8. **Unfilled stubs** — docs still carrying `TODO` placeholders. Note them; being unfilled is only
   a problem if the information now exists.
9. **Superseded chains** — every `status: superseded` doc has a `related:` pointing forward, and
   no `active` ADR contradicts another.

## Context budget

10. **Skill health** — any `SKILL.md` body over ~150 lines, or containing subject matter that
    duplicates a doc rather than linking to it. Any skill whose docs have all moved or been
    deleted.
11. **`CLAUDE.md`** — still under ~60 lines, and containing no `@` imports (which would be inlined
    into every session).
12. **Orphans** — docs that nothing links to and no skill routes to. They cannot be found, so they
    are not doing any work.

## Report

Group as **Broken** (integrity failures), **Stale** (accuracy risks), **Budget** (context cost),
**Fine**. Give the one-line fix for each. Then ask which to apply.
