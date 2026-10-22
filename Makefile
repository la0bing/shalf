SERVICE ?= feature-server
PIPELINE ?= hourly
PROJECT ?= examples/quickstart
APP_MODULE ?= $(subst -,_,$(SERVICE)).app:app
IMAGE_REGISTRY ?= ghcr.io/la0bing
TAG ?= dev
OVERLAY ?= dev

.PHONY: install lint fmt typecheck test quickstart pipeline serve-features docker-build project-images k8s-render console-web console console-idp console-e2e poc-up poc-smoke poc-down

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

console-web:        ## Build the console UI into the console package
	cd services/console/web && npm ci && npm run build

console:            ## Run the console locally (http://localhost:8090, admin@example.com / change-me-locally)
	SHALF_CONSOLE_CONFIG=services/console/dev/console.dev.yaml uv run shalf-console

console-idp:        ## Run the dev OIDC provider for trying SSO locally (port 9555)
	uv run python services/console/dev/dev_idp.py

console-e2e:        ## Browser end-to-end test of the console (needs console-web first)
	uv run --with playwright python services/console/e2e/run_e2e.py

POC := docker compose -f deploy/compose/docker-compose.yml

poc-up:             ## Docker Compose proof of concept: whole platform on one machine
	$(POC) up -d --build

poc-smoke:          ## Check the running PoC from the outside (incl. SSO and a pipeline run)
	python3 deploy/compose/smoke_test.py

poc-down:           ## Stop the PoC (data volumes are kept)
	$(POC) down
