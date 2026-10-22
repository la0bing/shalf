from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator

from shalf_console.context import Console
from shalf_console.deps import get_console, require
from shalf_console.modules.base import ConsoleModule
from shalf_console.rbac import Permission, Principal

M = "serving"
PERMISSIONS = [
    Permission("serving.read", "See online serving health and served versions", M),
    Permission("serving.query", "Look up online feature values", M),
]


class OnlineRequest(BaseModel):
    entities: dict[str, list[Any]]
    features: list[str] | None = None
    feature_service: str | None = None
    request_data: dict[str, list[Any]] | None = None

    @model_validator(mode="after")
    def _one(self) -> OnlineRequest:
        if (self.features is None) == (self.feature_service is None):
            raise ValueError("Provide exactly one of `features` or `feature_service`")
        return self


def router() -> APIRouter:
    api = APIRouter(prefix="/projects/{project}/serving", tags=["serving"])

    @api.get("/status")
    def status(
        project: str,
        console: Console = Depends(get_console),
        _: Principal = require("serving.read"),
    ) -> dict[str, Any]:
        backend = console.projects[project]
        health = backend.health()
        try:
            plan = backend.plan()
        except Exception as exc:
            plan, health = [], {**health, "plan_error": str(exc)}
        return {
            "health": health,
            "backend": backend.kind,
            "views": [
                {"view": r["view"], "active_version": r["active_version"], "status": r["status"]}
                for r in plan
            ],
        }

    @api.post("/online")
    def online(
        project: str,
        body: OnlineRequest,
        console: Console = Depends(get_console),
        _: Principal = require("serving.query"),
    ) -> dict[str, Any]:
        try:
            return console.projects[project].online(
                body.entities, body.features, body.feature_service, body.request_data
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return api


def module() -> ConsoleModule:
    return ConsoleModule(
        key=M,
        title="Serving",
        description="Online feature serving: health, served versions, live lookups",
        status="ready",
        permissions=PERMISSIONS,
        read_permission="serving.read",
        router=router(),
        order=30,
    )
