---
name: deploy
description: Use when running the platform locally, deploying to Kubernetes, wiring a service into docker compose or the Helm chart, or changing platform configuration/env vars.
---

# Deploy

All deployment conventions live in `docs/deployment.md` — read it before touching anything under
`deploy/` or adding a service. The short version: Docker Compose locally (spine always on, one
profile per block), one umbrella Helm chart in production (one `<block>.enabled` flag per
block), configuration via `SHALF_*` env vars only.

Adding or changing a block's deployment? Use the checklist at the bottom of `docs/deployment.md`.
If `deploy/` and that doc disagree, the code is right and the doc is a bug — fix it in the same
change (`docs-sync` skill).
