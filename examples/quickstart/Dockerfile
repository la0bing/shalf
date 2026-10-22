# syntax=docker/dockerfile:1.7
# This project's images, built on the platform's base images:
#   docker build --target jobs    -t ghcr.io/la0bing/quickstart-jobs:TAG .
#   docker build --target serving -t ghcr.io/la0bing/quickstart-serving:TAG .
# Bump SHALF_VERSION to upgrade the platform; the project code stays put.
ARG SHALF_REGISTRY=ghcr.io/la0bing
ARG SHALF_VERSION=0.1.0

# Batch image: dbt + pipelines + this project (CronJobs, backfill Jobs).
FROM ${SHALF_REGISTRY}/shalf-platform-jobs:${SHALF_VERSION} AS jobs
COPY --chown=10001:10001 . /app/project
# Bake the dbt manifest: feature view versions include dbt model checksums, and
# serving pods (which have no dbt) must compute the same versions.
RUN SHALF_DBT_TARGET_PATH=/app/project/transform/target \
    shalf-pipelines --repo /app/project dbt parse

# Serving image: feature server + this project's definitions and manifest.
FROM ${SHALF_REGISTRY}/shalf-feature-server:${SHALF_VERSION} AS serving
COPY --from=jobs /app/project /app/project
