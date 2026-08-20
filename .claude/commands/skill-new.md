---
description: Create a new skill in .claude/skills/ for a docs domain
argument-hint: <domain>
---

Create a new skill for the domain: **$ARGUMENTS**

## First, check it is warranted

A skill costs standing tokens in every session, and every extra skill dilutes the trigger space,
making the others fire less reliably. Justified when a docs domain has passed ~5 documents, or
when a recurring question keeps missing every existing skill.

Read `.claude/skills/docs-maintenance/SKILL.md` for the authoring rules, then check whether an
existing skill already covers this — extending one is usually better than adding another. If it is
not warranted, say so and stop.

## Then create it

Use the **`skill-creator`** skill to scaffold and author it, subject to these constraints:

- **Route, do not explain.** The body contains pointers to `docs/` and procedures — never subject
  matter. A skill that explains what something *does* has duplicated a fact that will rot. This is
  what keeps code changes from requiring skill edits.
- **The `description` is the whole trigger.** It is the only part loaded into every session and the
  only thing deciding whether the skill fires. Write it as "Use when…", naming concrete situations
  and the words someone would actually use. Vague descriptions mean the skill silently never fires.
- **Body ≤ ~150 lines.** Over budget means content leaked in; push it into `docs/`.
- Match the tone and shape of the existing skills in `.claude/skills/`.

## Finally

- Note in `docs/README.md` if the growth rule's pending splits changed.
- Verify the routing: every path the new skill references exists.
