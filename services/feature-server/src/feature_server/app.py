"""Online feature server.

Environment:
    SHALF_REPO_PATH  feature repository directory (baked into the image)
    SHALF_CONFIG     optional shalf.yaml override (mounted from a ConfigMap)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from shalf.core import ShalfError, configure_logging, get_logger
from shalf.data import FeatureStore

log = get_logger(__name__)


class OnlineFeaturesRequest(BaseModel):
    entities: dict[str, list[Any]] = Field(examples=[{"customer_id": [1, 2]}])
    features: list[str] | None = Field(default=None, examples=[["customer_txn_stats:txn_count_7d"]])
    feature_service: str | None = Field(default=None, examples=["fraud_model_v1"])
    request_data: dict[str, list[Any]] | None = None
    full_feature_names: bool = False

    @model_validator(mode="after")
    def _one_selector(self) -> OnlineFeaturesRequest:
        if (self.features is None) == (self.feature_service is None):
            raise ValueError("Provide exactly one of `features` or `feature_service`")
        return self


class OnlineFeaturesResponse(BaseModel):
    feature_names: list[str]
    results: dict[str, list[Any]]


def create_app(store: FeatureStore | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        app.state.store = store or FeatureStore.from_repo(os.environ.get("SHALF_REPO_PATH", "."))
        log.info("Loaded feature repo for project %r", app.state.store.config.project)
        yield

    app = FastAPI(title="shalf feature server", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        try:
            app.state.store.online_store.ping()
        except Exception as exc:
            log.warning("Online store unreachable: %s", exc)
            raise HTTPException(503, "online store unreachable") from exc
        return {"status": "ready", "feature_views": len(app.state.store.list_feature_views())}

    @app.get("/v1/registry")
    def registry() -> dict[str, Any]:
        return app.state.store.registry.to_dict()

    @app.get("/v1/feature-views/{name}")
    def feature_view(name: str) -> dict[str, Any]:
        try:
            return app.state.store.registry.get_view(name).describe()
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    # Sync handler: FastAPI runs it in a thread pool, so blocking store I/O is fine.
    @app.post("/v1/features/online", response_model=OnlineFeaturesResponse)
    def online_features(request: OnlineFeaturesRequest) -> OnlineFeaturesResponse:
        try:
            response = app.state.store.get_online_features(
                request.entities,
                request.features,
                feature_service=request.feature_service,
                request_data=request.request_data,
                full_feature_names=request.full_feature_names,
            )
        except (KeyError, ValueError, ShalfError) as exc:
            raise HTTPException(400, str(exc)) from exc
        return OnlineFeaturesResponse(
            feature_names=response.feature_names, results=response.to_dict()
        )

    return app


app = create_app()
