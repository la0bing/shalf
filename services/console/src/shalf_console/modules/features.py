from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from shalf_console.context import Console
from shalf_console.deps import get_console, get_db, require
from shalf_console.modules.base import ConsoleModule
from shalf_console.rbac import Permission, Principal

M = "features"
PERMISSIONS = [
    Permission("features.read", "List feature views, services, versions and lineage", M),
    Permission("features.preview", "Look at computed feature rows", M),
    Permission("features.backfill", "Backfill feature views over a time range", M),
    Permission("features.promote", "Switch readers to new feature versions", M),
]


class PromoteRequest(BaseModel):
    views: list[str] | None = None


def _views_with_status(console: Console, project: str) -> list[dict[str, Any]]:
    backend = console.projects[project]
    registry, plan = backend.registry(), {r["view"]: r for r in backend.plan()}
    views = registry["feature_views"]
    downstream: dict[str, list[str]] = {v["name"]: [] for v in views}
    for view in views:
        for upstream in view.get("upstream", []):
            downstream.setdefault(upstream, []).append(view["name"])
    for view in views:
        view["downstream"] = downstream.get(view["name"], [])
        view["rollout"] = plan.get(view["name"])
    return views


def router() -> APIRouter:
    api = APIRouter(prefix="/projects/{project}/features", tags=["features"])

    @api.get("/views")
    def list_views(
        project: str,
        console: Console = Depends(get_console),
        _: Principal = require("features.read"),
    ) -> list[dict[str, Any]]:
        return _views_with_status(console, project)

    @api.get("/views/{view}")
    def get_view(
        project: str,
        view: str,
        console: Console = Depends(get_console),
        _: Principal = require("features.read"),
    ) -> dict[str, Any]:
        for item in _views_with_status(console, project):
            if item["name"] == view:
                return item
        raise HTTPException(404, f"Unknown feature view {view!r}")

    @api.get("/views/{view}/preview")
    def preview(
        project: str,
        view: str,
        limit: int = Query(50, ge=1, le=500),
        console: Console = Depends(get_console),
        _: Principal = require("features.preview"),
    ) -> dict[str, Any]:
        return console.projects[project].preview(view, limit)

    @api.get("/services")
    def services(
        project: str,
        console: Console = Depends(get_console),
        _: Principal = require("features.read"),
    ) -> list[dict[str, Any]]:
        return console.projects[project].registry()["feature_services"]

    @api.get("/entities")
    def entities(
        project: str,
        console: Console = Depends(get_console),
        _: Principal = require("features.read"),
    ) -> list[dict[str, Any]]:
        return console.projects[project].registry()["entities"]

    @api.post("/promote")
    def promote(
        project: str,
        body: PromoteRequest,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        principal: Principal = require("features.promote"),
    ) -> dict[str, str]:
        promoted = console.projects[project].promote(body.views)
        console.audit(
            db,
            principal.email,
            "features.promote",
            ",".join(promoted) or "-",
            project=project,
            versions=promoted,
        )
        return promoted

    return api


def module() -> ConsoleModule:
    return ConsoleModule(
        key=M,
        title="Features",
        description="Feature views, lineage, versions and rollouts",
        status="ready",
        permissions=PERMISSIONS,
        read_permission="features.read",
        router=router(),
        order=10,
    )
