"""Online feature server.

Environment:
    SHALF_REPO_PATH  project directory (/app/project in project images)
    SHALF_PROFILE    shalf.yaml profile: `serving`, or `eda` for the EDA server
    SHALF_CONFIG     optional path to a different shalf.yaml
    SHALF_ADMIN_TOKEN  enables the /v1/admin API (plan, promote, preview) for
                       the console; requests must send `Authorization: Bearer <token>`
"""

from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from shalf.core import ShalfError, configure_logging, get_logger
from shalf.data import FeatureStore
from shalf.data.types import to_python

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


class PromoteRequest(BaseModel):
    views: list[str] | None = None


def create_app(store: FeatureStore | None = None, admin_token: str | None = None) -> FastAPI:
    admin_token = (
        admin_token if admin_token is not None else os.environ.get("SHALF_ADMIN_TOKEN", "")
    )

    def require_admin(authorization: str | None = Header(None)) -> None:
        if not admin_token:
            raise HTTPException(404, "Admin API disabled (set SHALF_ADMIN_TOKEN)")
        if not authorization or not hmac.compare_digest(authorization, f"Bearer {admin_token}"):
            raise HTTPException(401, "Invalid admin token")

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

    # -- admin API used by the console (token-protected, disabled by default) -------
    @app.get("/v1/admin/plan", dependencies=[Depends(require_admin)])
    def plan() -> list[dict[str, Any]]:
        return app.state.store.plan()

    @app.get("/v1/admin/pipelines", dependencies=[Depends(require_admin)])
    def pipelines() -> dict[str, Any]:
        return dict(app.state.store.config.pipelines)

    @app.post("/v1/admin/promote", dependencies=[Depends(require_admin)])
    def promote(body: PromoteRequest) -> dict[str, str]:
        try:
            return app.state.store.promote(body.views)
        except (ShalfError, PermissionError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/v1/admin/preview/{view}", dependencies=[Depends(require_admin)])
    def preview(view: str, limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        try:
            df = app.state.store.preview(view, limit=limit)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ShalfError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "columns": list(df.columns),
            "rows": [[to_python(v) for v in row] for row in df.itertuples(index=False)],
        }

    return app


app = create_app()
