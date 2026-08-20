---
id: 0001
title: Local development
type: guide
status: draft
owner: la0bing
created: 2026-08-20
updated: 2026-08-20
components: []
related: [docs/reference/conventions.md]
summary: How to get the repo running locally — no setup needed yet, there is no code.
tags: [workflow, setup]
---

# Local development

## Right now

There is nothing to run. The repo contains documentation and Claude Code configuration only — no
application code, no dependencies, no build step. Clone it and read.

```sh
git clone git@github.com:la0bing/shalf.git
cd shalf
```

## Once a stack is chosen

This guide gets filled in with prerequisites, install, run, and test commands at the same time the
stack ADR lands. Fill in this section then — a setup guide written before the setup exists is
fiction, and a model reading it cannot tell.

## Claude Code in this repo

Nothing to install. Opening the repo picks up `CLAUDE.md`, the skills in `.claude/skills/`, and
the commands in `.claude/commands/`.

The one habit that matters: **run `/docs-sync` before committing code.** See `docs/README.md`.
