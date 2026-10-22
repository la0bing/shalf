# syntax=docker/dockerfile:1.7
# The console image: SPA (built with Node) + console API (Python).
#   docker build -f deploy/docker/console.Dockerfile -t ghcr.io/la0bing/shalf-console:TAG .
ARG PYTHON_VERSION=3.12

FROM node:22-slim AS web
WORKDIR /web
COPY services/console/web/package.json services/console/web/package-lock.json ./
RUN npm ci
COPY services/console/web ./
RUN npm run build -- --outDir /web/dist --emptyOutDir

FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

FROM python:${PYTHON_VERSION}-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package shalf-console --extra postgres

FROM python:${PYTHON_VERSION}-slim AS runtime
RUN useradd --uid 10001 --create-home --home-dir /home/shalf --shell /usr/sbin/nologin shalf
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=web /web/dist /app/static
ENV PATH=/app/.venv/bin:$PATH \
    HOME=/home/shalf \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHALF_CONSOLE_STATIC=/app/static \
    SHALF_CONSOLE_CONFIG=/etc/shalf-console/console.yaml
USER 10001
EXPOSE 8090
CMD ["shalf-console", "--port", "8090"]
