---
name: new-block
description: Use when adding a new platform building block (a service under apps/ with an SDK extra), extending an existing block, or deciding which block owns a capability.
---

# New block

A block is a composable unit of the platform: FastAPI service in `apps/<block>/`, optional extra
in `packages/sdk`, depends on `packages/core` only. The blueprint — spine, block list,
composition rules, repo layout — is `docs/specs/0002-platform-foundation.md`. Read it first;
the composition rules there are load-bearing, not style.

## Procedure

1. **Ownership check**: find the capability in the block table of spec 0002. If it fits an
   existing block, extend that block instead. If it fits none, that's a blueprint change —
   raise it with the user before writing code.
2. **Spec first**: every block gets its own spec (`specs` skill). List `apps/<block>` and any
   touched packages in `components:`.
3. **Build inside the boundary**: imports from `packages/core` only; talk to sibling blocks via
   their REST APIs or spine events; own Postgres schema; `SHALF_<BLOCK>_*` env vars.
4. **Ship both deploy targets**: work through the checklist in `docs/deployment.md` — compose
   profile and Helm `<block>.enabled` flag are part of the block, not follow-up work.
5. **Docs**: `docs-sync` skill before committing — components row in `docs/architecture.md`,
   a `CLAUDE.md` inside the new workspace (see `docs/conventions.md`), spec status updated.
