# shalf

A self-built, modular, end-to-end ML platform: development (EDA, training, validation), delivery
(batch pipelines, REST model hosting), and operation (experiment tracking, model registry, drift
detection) as independent building blocks on a shared spine. Run only the blocks you need —
locally with Docker Compose, or in production on Kubernetes. Blueprint:
`docs/specs/0002-platform-foundation.md`.

```
apps/       one service per building block  (empty — foundation lands first)
packages/   core contracts + the `shalf` SDK (empty)
docs/       product, architecture, deployment, conventions, per-feature specs
.claude/    skills that load docs on demand and keep them in sync with code
```

Docs describe *now*; git history is the archive. The one working habit: every code change ends by
updating the docs that describe it — the `docs-sync` skill in `.claude/skills/` holds the
procedure, and a Stop hook reminds you if code changed and docs didn't.

License: Apache-2.0 — see [LICENSE](LICENSE).
