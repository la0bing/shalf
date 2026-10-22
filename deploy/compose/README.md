# Docker Compose proof of concept

The whole platform on one machine with Docker: the same topology as the
Kubernetes deployment, scaled down.

```bash
docker compose -f deploy/compose/docker-compose.yml up -d --build   # or: make poc-up
python deploy/compose/smoke_test.py                                  # or: make poc-smoke
```

| URL | What |
| --- | --- |
| http://localhost:8090 | Console. Local login `admin@example.com` / `change-me`, or **Dev SSO** (type any email and groups) |
| http://localhost:8080/docs | Online feature server (Redis primary) |
| http://localhost:8081/docs | EDA feature server (Redis replica, offline cache only, read-only) |

## What runs

```
postgres ───── app database (seeded) ──ATTACH read-only──▶ pipelines ──▶ /data volume
   │                                                       (dbt + features,   warehouse + cache
   └── console database                                     every: 24h / 1h)       │
                                                              │                     │
redis ◀──────────────────── latest feature values ────────────┘                     │
  └─▶ redis-replica ──▶ feature-server-eda ◀────────────────── cache (ro) ──────────┘
redis ──▶ feature-server :8080
console :8090 (+ dev-idp :9555, sharing its network)
```

| Service | Role |
| --- | --- |
| `postgres` | The application's database (dbt reads it) and the console's database |
| `redis`, `redis-replica` | Online store, plus a read replica for exploration traffic |
| `seed` | One-off: synthetic customers, merchants and transactions (skipped once seeded) |
| `pipelines` | `shalf-pipelines schedule`: runs each pipeline every `every:` from `shalf.yaml` (daily, hourly), one at a time |
| `feature-server` | Online serving (`SHALF_PROFILE=serving`) |
| `feature-server-eda` | Exploration (`SHALF_PROFILE=eda`): replica, cache only, refuses writes |
| `console` | UI + control plane. The quickstart project is loaded in-process; runs started from the UI wait for the scheduler through the pipeline lock |
| `dev-idp` | A fake OIDC provider for trying SSO. It shares the console's network namespace, so `http://localhost:9555` is the same issuer for your browser and for the console |

Everything is built into one image (`deploy/compose/Dockerfile`, about
1.5 GB): every platform service, the console UI and the quickstart project.
Production instead uses one image per service plus project images.

## Make it yours

- **Your project:** build with `--build-arg PROJECT=path/to/your/project`
  (the `PROJECT` arg of `deploy/compose/Dockerfile`), or point the build at
  your own copy of this directory.
- **Your database:** set `SHALF_PG_DSN` (ideally a read replica) and remove
  the `seed` service.
- **Real SSO:** replace the `dev` provider in `console.yaml` with your IdP
  (issuer, client ID, secret), register
  `http://<host>:8090/auth/oidc/<id>/callback` as the redirect URI, and remove
  the `dev-idp` service.
- **Faster schedules for demos:** `command: ["shalf-pipelines", "schedule", "--every", "hourly=5m"]`.
- **Passwords:** set `SHALF_CONSOLE_ADMIN_PASSWORD` and `SHALF_ADMIN_TOKEN`
  in a `.env` file next to the compose file. The defaults are for localhost
  only.

## Not for production

Single host and no TLS. Postgres and Redis use default passwords. Local
login is on, and the dev IdP signs whatever identity you type. For
production, use the Kubernetes manifests (`deploy/k8s`, `docs/console.md`).

```bash
make poc-down        # stop; add -v to the compose command to also delete the data volumes
```
