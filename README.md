# shalf

Monorepo containing all code for the project, together with its specs and docs.

```
apps/       deployable applications        (empty — stack not chosen yet)
packages/   shared libraries               (empty)
docs/       product, architecture, conventions, and per-feature specs
.claude/    skills that load docs on demand and keep them in sync with code
```

Docs describe *now*; git history is the archive. The one working habit: every code change ends by
updating the docs that describe it — the `docs-sync` skill in `.claude/skills/` holds the
procedure, and a Stop hook reminds you if code changed and docs didn't.

License: Apache-2.0 — see [LICENSE](LICENSE).
