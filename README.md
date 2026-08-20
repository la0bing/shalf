# shalf

Monorepo containing all code for the project, together with its specs and design docs.

## Layout

```
apps/       deployable applications
packages/   shared libraries
docs/       specs, decisions, architecture, reference  ->  see docs/README.md
.claude/    skills + slash commands that load docs on demand
```

Start at [`docs/INDEX.md`](docs/INDEX.md) for a one-line summary of every document.

## Status

Early. The technology stack has not been chosen yet — `apps/` and `packages/` are placeholders
and there is no build tooling. The stack decision will be recorded as an ADR in `docs/adr/`.

## Working with Claude Code

This repo is set up so documentation loads into the model's context only when relevant, and so
docs stay in step with code. Both mechanisms are described in [`docs/README.md`](docs/README.md);
the short version is: write a spec before non-trivial work, and run `/docs-sync` before you commit.

## License

Apache-2.0. See [LICENSE](LICENSE).
