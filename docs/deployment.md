# Deployment

> **Nothing is deployable yet.** `deploy/` does not exist until the foundation
> (`docs/specs/0002-platform-foundation.md`) lands. This doc records the *conventions* every
> block must ship with, so the first and the tenth block compose the same way. When reality and
> this doc diverge, fix this doc (see the `docs-sync` skill).

Two targets, one composition model: users pick blocks; the spine is always on.

## Local — Docker Compose

- One file: `deploy/compose/docker-compose.yml`. Spine services (PostgreSQL, object store) carry
  no profile and always start. Each block's service carries `profiles: [<block>]`.
- Run the spine alone: `docker compose up`. Add blocks:
  `docker compose --profile experiments --profile registry up`.
- Block images build from their own `apps/<block>/Dockerfile`; compose builds locally, no
  registry needed.
- Configuration via environment variables only: `SHALF_CORE_*` for spine, `SHALF_<BLOCK>_*` per
  block, with working defaults for local so `up` needs no env file.

## Production — Kubernetes (Helm)

- One umbrella chart: `deploy/k8s/shalf/`, with a subchart (or template group) per block and a
  single switchboard in `values.yaml`:

  ```yaml
  experiments:
    enabled: true
  serving:
    enabled: false
  ```

- Spine defaults to in-cluster PostgreSQL + object store for evaluation; production values point
  at managed equivalents (any S3-compatible store, managed Postgres). Blocks never know which —
  they see `SHALF_CORE_*` env vars.
- One container image per block, tagged with the repo release; no shared "platform" mega-image.

## Adding a block — checklist

A block is not done until every box ticks (the `new-block` skill walks this):

1. `apps/<block>/Dockerfile` builds the service image.
2. Compose: service entry with `profiles: [<block>]`, env defaults, healthcheck.
3. Helm: `<block>.enabled` flag wired, off by default; env from spine values.
4. Config only via `SHALF_<BLOCK>_*` env vars — no config files baked into images.
5. Runs on spine + itself alone (composition rule 4 in spec 0002).
