# syntax=docker/dockerfile:1.7
# One Dockerfile for every service in services/:
#   docker build -f deploy/docker/Dockerfile \
#     --build-arg SERVICE=feature-server --build-arg APP_MODULE=feature_server.app:app .
ARG PYTHON_VERSION=3.12

FROM ghcr.io/astral-sh/uv:0.11.32 AS uv

# ---- build: resolve only the workspace packages this service depends on ----
FROM python:${PYTHON_VERSION}-slim AS builder
ARG SERVICE
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package "${SERVICE}"

# ---- runtime: just the virtualenv + the feature repository ----
FROM python:${PYTHON_VERSION}-slim AS runtime
ARG APP_MODULE
ARG FEATURE_REPO=examples/quickstart/feature_repo
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin shalf
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY ${FEATURE_REPO} /app/feature_repo
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHALF_REPO_PATH=/app/feature_repo \
    APP_MODULE=${APP_MODULE}
USER 10001
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn \"$APP_MODULE\" --host 0.0.0.0 --port 8080"]
