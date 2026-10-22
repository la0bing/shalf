SERVICE ?= feature-server
APP_MODULE ?= $(subst -,_,$(SERVICE)).app:app
IMAGE_REGISTRY ?= ghcr.io/la0bing
TAG ?= dev
OVERLAY ?= dev

.PHONY: install lint fmt typecheck test quickstart serve-features docker-build k8s-render

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

quickstart:         ## Seed the example SQLite db, materialize and read features
	uv run python examples/quickstart/run.py

serve-features:     ## Run the online feature server against the quickstart repo
	SHALF_REPO_PATH=examples/quickstart/feature_repo uv run uvicorn feature_server.app:app --reload --port 8080

docker-build:       ## Build one service image: make docker-build SERVICE=inference-api
	docker build -f deploy/docker/Dockerfile \
		--build-arg SERVICE=$(SERVICE) --build-arg APP_MODULE=$(APP_MODULE) \
		-t $(IMAGE_REGISTRY)/shalf-$(SERVICE):$(TAG) .

k8s-render:         ## Render manifests for an overlay: make k8s-render OVERLAY=prod
	kubectl kustomize deploy/k8s/overlays/$(OVERLAY)
