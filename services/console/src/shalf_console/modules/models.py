from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from shalf_console.context import Console
from shalf_console.deps import get_console, get_db, require
from shalf_console.modules.base import ConsoleModule
from shalf_console.rbac import Permission, Principal

M = "models"
PERMISSIONS = [
    Permission("models.read", "See registered models, versions and metrics", M),
    Permission("models.promote", "Move model versions between stages", M),
]


class PromoteRequest(BaseModel):
    stage: Literal["staging", "production", "archived"]


def router() -> APIRouter:
    api = APIRouter(prefix="/models", tags=["models"])

    @api.get("")
    def list_models(
        console: Console = Depends(get_console),
        _: Principal = require("models.read", project_scoped=False),
    ) -> list[dict[str, Any]]:
        return [asdict(m) for m in console.model_registry.list()]

    @api.post("/{name}/versions/{version}/promote")
    def promote(
        name: str,
        version: str,
        body: PromoteRequest,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        principal: Principal = require("models.promote", project_scoped=False),
    ) -> dict[str, Any]:
        try:
            artifact = console.model_registry.promote(name, version, body.stage)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        console.audit(db, principal.email, "models.promote", f"{name}@{version}", stage=body.stage)
        return asdict(artifact)

    return api


def module() -> ConsoleModule:
    return ConsoleModule(
        key=M,
        title="Models",
        description="Model registry: versions, metrics, stages, linked feature services",
        status="preview",
        permissions=PERMISSIONS,
        read_permission="models.read",
        project_scoped=False,
        router=router(),
        order=40,
    )
