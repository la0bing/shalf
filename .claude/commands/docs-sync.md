---
description: Reconcile the current diff against the docs that describe the changed code
---

Reconcile documentation with the code changes in this branch. Run this **before committing**.

Extra focus, if given: $ARGUMENTS

## 1. Collect the diff

```sh
git diff --name-only origin/main...HEAD
git status --porcelain
```

Include uncommitted work. Ignore changes confined to `docs/` — they are the output of this
process, not its input.

## 2. Map changed paths to the docs claiming to describe them

For each changed path, take its workspace prefix (`apps/<name>` or `packages/<name>`) and find
docs listing it:

```sh
rg -l 'components:.*<workspace>' docs/
```

Also read `docs/INDEX.md` and pick up anything topically related that `components:` missed — a
missing `components:` entry is itself a finding, so note it.

## 3. Walk each affected doc

For every doc found, read it and ask: **does the code still do what this says?** Update the
content where it does not, and bump `updated:`. Do not tidy prose that is still accurate — this
step is about truth, not polish.

## 4. Then check each of these, and say explicitly which apply and which do not

- **Architecture** — did this alter system structure, a workspace boundary, or a data flow? Update
  `docs/architecture/system-overview.md`.
- **Decisions** — did this make a non-obvious technical choice, or reverse an earlier one? Propose
  `/adr-new`. Do not edit an existing decided ADR.
- **Shipped specs** — is a spec now fully implemented? Propose `/spec-ship <id>`.
- **New workspaces** — added under `apps/` or `packages/`? Add the path to the `components:` of
  relevant specs, add a row to the architecture components table, and create the workspace's own
  `CLAUDE.md` (see `docs/reference/conventions.md`).
- **Vocabulary** — new domain term introduced in the code? Add it to
  `docs/reference/glossary.md`, or rename the code to use the existing term.
- **Contributor workflow** — changed? Update `docs/reference/conventions.md` or `docs/guides/`.
- **Skills** — were docs added, renamed, or removed? Fix any `.claude/skills/*/SKILL.md` that
  linked to them, and apply the growth rule: a docs domain past ~5 docs warrants its own skill.

## 5. Regenerate the index

Run `/docs-index`.

## 6. Report

List what you changed, and — just as important — what you checked and found already accurate. If
you found nothing to update, say so plainly rather than manufacturing an edit.
