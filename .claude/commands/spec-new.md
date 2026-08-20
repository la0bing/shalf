---
description: Create a new feature spec in docs/specs/ from the template
argument-hint: <slug>
---

Create a new feature spec for: **$ARGUMENTS**

1. Determine the next spec number: list `docs/specs/[0-9]*.md`, take the highest numeric prefix,
   add one, zero-pad to 4 digits. If none exist, start at `0001`.
2. Copy `docs/specs/_TEMPLATE.md` to `docs/specs/<NNNN>-<slug>.md`, where `<slug>` is the argument
   in kebab-case.
3. Fill the frontmatter: `id`, `title` (human-readable form of the slug), `status: draft`,
   `owner: la0bing`, `created` and `updated` set to today's date.
4. Interview the user for anything you cannot infer — problem, goals, non-goals, approach. Ask in
   one batch, not one question at a time. If they want to fill it in later, leave the template's
   section prompts in place rather than inventing content.
5. Set `components:` to the workspace paths under `apps/` or `packages/` this will touch. If none
   exist yet, leave it `[]` and note that it must be filled when the workspaces are created —
   without it the spec is invisible to `/docs-sync` drift detection.
6. Write `summary:` as one sentence aimed at a reader deciding whether to open the file. Not a
   restatement of the title.
7. Run `/docs-index` to add it to `docs/INDEX.md`.

Report the path created and anything left as a TODO.
