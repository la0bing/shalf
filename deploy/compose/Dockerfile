# syntax=docker/dockerfile:1.7
# All-in-one image for the docker compose proof of concept: every platform
# service, the console UI and one project, so one build serves every container.
# Production uses one image per service (deploy/docker/) plus project images.
ARG PYTHON_VERSION=3.12

# ---- console UI ----
FROM node:22-slim AS web
WORKDIR /web
COPY services/console/web/package.json services/console/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY services/console/web ./
RUN npm run build -- --outDir /web/dist --emptyOutDir

# ---- every workspace package ----
FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:${PYTHON_VERSION}-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --all-packages --all-extras

# ---- runtime ----
FROM python:${PYTHON_VERSION}-slim
ARG PROJECT=examples/quickstart
RUN useradd --uid 10001 --create-home --home-dir /home/shalf --shell /usr/sbin/nologin shalf \
    && mkdir -p /data && chown 10001:10001 /data
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=web /web/dist /app/static
COPY --chown=10001:10001 ${PROJECT} /app/project
COPY services/console/dev/dev_idp.py /app/dev/dev_idp.py
ENV PATH=/app/.venv/bin:$PATH \
    HOME=/home/shalf \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHALF_REPO_PATH=/app/project \
    SHALF_CONSOLE_STATIC=/app/static \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false
USER 10001
# DuckDB extensions for dbt's ATTACH, baked in so containers need no internet.
RUN python -c "import duckdb; con = duckdb.connect(); \
    [con.install_extension(e, repository_url='https://extensions.duckdb.org') for e in ('postgres', 'sqlite')]"
# Bake the dbt manifest (feature versions include dbt model checksums).
RUN SHALF_DBT_TARGET_PATH=/app/project/transform/target shalf-pipelines --repo /app/project dbt parse
