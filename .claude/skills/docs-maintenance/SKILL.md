---
name: docs-maintenance
description: Use after changing code or before committing, when asked to update or check the docs, when docs may be stale or contradict the code, or when creating, editing, or deleting a skill or slash command in .claude/.
---

# Keeping docs, specs and skills in step with code

Stale docs are worse than no docs here: a model cannot tell that a file is out of date and will
follow it confidently into the wrong design. So reconciliation is a step in the workflow, not a
matter of remembering.

```
  /spec-new  ──▶  implement  ──▶  /docs-sync  ──▶  commit / PR
      ▲                                │
      └────────  /docs-audit  ◀────────┘   (periodic, whole-tree)
```

## Before committing code: `/docs-sync`

Run it whenever a change touches `apps/` or `packages/`. It is diff-driven rather than a memory
exercise: it reads the changed paths, matches them against `components:` frontmatter across
`docs/**` to get the concrete list of docs claiming to describe that code, then walks each one.

Do not skip it because the change "was small". Small changes are exactly the ones that silently
invalidate a sentence in a spec.

## Periodically: `/docs-audit`

Monthly, before a release, or whenever the docs stop feeling trustworthy. Whole-tree health check:
broken links, `INDEX.md` drift, frontmatter violations, `components:` paths that no longer exist,
specs stuck in the wrong status, orphaned docs, oversized skills.

## Which doc changes when

| The change… | Update |
|---|---|
| alters behaviour a spec describes | that spec — and if the feature is now built, `/spec-ship <id>` |
| alters system structure, a boundary, or a data flow | `docs/architecture/system-overview.md` |
| makes a non-obvious technical choice, or reverses one | `/adr-new` (never edit a decided ADR) |
| adds a workspace | `components:` of relevant specs, the architecture components table, and a `CLAUDE.md` inside the workspace |
| introduces a new domain term | `docs/reference/glossary.md` |
| changes how contributors work | `docs/reference/conventions.md` or `docs/guides/` |
| adds, renames, or removes a doc | `docs/INDEX.md` via `/docs-index`, plus any skill that linked to it |

Always bump `updated:` on a doc you edit. Never hand-edit `docs/INDEX.md` — it is generated.

## Authoring and maintaining skills

### The rule that keeps this cheap: skills route, docs hold content

A `SKILL.md` body contains **pointers and procedures, never subject matter**. A skill that
explains *what* the auth flow does has duplicated a fact that now lives in two places, and one of
them will rot. Instead: "auth is specified in `docs/specs/NNNN-auth.md`; read it before touching
the auth package" — true regardless of how auth changes.

The payoff: **a code change never requires editing a skill.** Skills change only when the docs
*structure* changes. That is a handful of edits a year, not one per PR.

### Anatomy

- The frontmatter `description` is the **only** thing loaded into every session (~50 tokens) and
  the only thing deciding whether the skill fires. Write it as an explicit trigger condition —
  "Use when…", naming the situations and the words someone would actually use. A vague description
  means the skill silently never fires, which is the dominant failure mode.
- Body ≤ ~150 lines. Over budget means subject matter leaked in; push it down into `docs/`.
- The body links to docs; it does not summarise them.

### When to create, change, or delete one

**Create** when a docs domain passes ~5 docs, or when a recurring question keeps missing every
existing skill. Use `/skill-new <domain>`, which delegates to the `skill-creator` skill. Currently
pending: `guides/` is routed through `repo-conventions` and splits into its own `dev-workflows`
skill once local-dev, testing and release guides are real.

**Change** when a doc it links to was renamed or deleted (`/docs-audit` catches these), when its
body drifts over budget, or when it demonstrably fails to fire — that last one is a `description`
problem, so rewrite the trigger phrasing, not the body.

**Delete** when its domain has folded into another, or its docs are reachable through a sibling
skill. Dead skills are not free: they cost standing tokens and dilute the trigger space, making
*other* skills fire less reliably.

## The context budget these rules protect

Only three things load unconditionally: root `CLAUDE.md`, every skill's `name` + `description`,
and the slash-command names — about 1k tokens total, and flat as the repo grows. Skill bodies load
on match; docs load only when a body points at them.

That budget breaks if anyone: adds `@path` imports to `CLAUDE.md` (eagerly inlined into every
session), pastes doc content into `CLAUDE.md`, lets a skill body sprawl, or keeps skills whose
domains are dead. Guard it.

## Backstops

Advisory, never blocking: a `Stop` hook in `.claude/settings.json` warns when a turn ends with
code changed and docs untouched; the PR template asks for the spec/ADR link; `docs-drift.yml`
comments on PRs from outside Claude Code. They catch forgetting — they do not replace the loop.
