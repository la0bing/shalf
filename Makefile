SERVICE ?= feature-server
PIPELINE ?= hourly
PROJECT ?= examples/quickstart
APP_MODULE ?= $(subst -,_,$(SERVICE)).app:app
IMAGE_REGISTRY ?= ghcr.io/la0bing
TAG ?= dev
OVERLAY ?= dev

.PHONY: install lint fmt typecheck test quickstart pipeline serve-features docker-build project-images k8s-render

install:            ## Install every workspace package (editable) + dev tools
	uv sync --all-packages

lint:               ## Static checks
	uv run ruff check .
	uv run ruff format --check .

fmt:                ## Auto-format
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy packages/*/src services/*/src

test:               ## Run all tests in the monorepo
	uv run pytest

quickstart:         ## Seed SQLite, run dbt + feature pipelines, build a training set, read online
	uv run python examples/quickstart/run.py

pipeline:           ## Run one project pipeline: make pipeline PIPELINE=daily
	uv run shalf-pipelines --repo $(PROJECT) run $(PIPELINE)

serve-features:     ## Run the online feature server against the quickstart repo
	SHALF_REPO_PATH=$(PROJECT) uv run uvicorn feature_server.app:app --reload --port 8080

docker-build:       ## Build one platform image: make docker-build SERVICE=platform-jobs
	docker build -f deploy/docker/Dockerfile \
		--build-arg SERVICE=$(SERVICE) --build-arg APP_MODULE=$(APP_MODULE) \
		--build-arg DUCKDB_EXTENSIONS="$(if $(filter platform-jobs,$(SERVICE)),sqlite postgres,)" \
		-t $(IMAGE_REGISTRY)/shalf-$(SERVICE):$(TAG) .

project-images:     ## Build a project's serving + jobs images on top of the platform images
	docker build --target jobs --build-arg SHALF_VERSION=$(TAG) -t $(IMAGE_REGISTRY)/$(notdir $(PROJECT))-jobs:$(TAG) $(PROJECT)
	docker build --target serving --build-arg SHALF_VERSION=$(TAG) -t $(IMAGE_REGISTRY)/$(notdir $(PROJECT))-serving:$(TAG) $(PROJECT)

k8s-render:         ## Render a project's manifests: make k8s-render OVERLAY=prod
	kubectl kustomize $(PROJECT)/deploy/$(OVERLAY)
