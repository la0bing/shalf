# syntax=docker/dockerfile:1.7
# Platform base images. They contain the shalf libraries and services but no
# project code; a project builds FROM them and adds itself at /app/project
# (see examples/quickstart/Dockerfile).
#
#   SERVICE=feature-server  APP_MODULE=feature_server.app:app  -> shalf-feature-server
#   SERVICE=inference-api   APP_MODULE=inference_api.app:app   -> shalf-inference-api
#   SERVICE=platform-jobs   DUCKDB_EXTENSIONS="sqlite postgres" -> shalf-platform-jobs
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

# ---- runtime: the virtualenv only ----
FROM python:${PYTHON_VERSION}-slim AS runtime
ARG APP_MODULE=""
ARG DUCKDB_EXTENSIONS=""
RUN useradd --uid 10001 --create-home --home-dir /home/shalf --shell /usr/sbin/nologin shalf \
    && mkdir -p /app/project && chown 10001:10001 /app/project
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    HOME=/home/shalf \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHALF_REPO_PATH=/app/project \
    APP_MODULE=${APP_MODULE}
USER 10001
# DuckDB downloads extensions on first use; bake them into the image so pods
# (read-only root filesystem, often no internet) never need to.
RUN if [ -n "$DUCKDB_EXTENSIONS" ]; then \
      python -c "import duckdb, sys; con = duckdb.connect(); [con.install_extension(e, repository_url='https://extensions.duckdb.org') for e in sys.argv[1:]]" $DUCKDB_EXTENSIONS; \
    fi
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn \"$APP_MODULE\" --host 0.0.0.0 --port 8080"]
