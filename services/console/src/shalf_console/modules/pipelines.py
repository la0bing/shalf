from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from shalf_console.context import Console
from shalf_console.deps import get_console, get_db, get_permissions, require
from shalf_console.modules.base import ConsoleModule
from shalf_console.rbac import Permission, Principal

M = "pipelines"
PERMISSIONS = [
    Permission("pipelines.read", "See pipelines, schedules, runs and logs", M),
    Permission("pipelines.run", "Start pipeline runs (backfills also need features.backfill)", M),
]


class RunRequest(BaseModel):
    start: str | None = None
    end: str | None = None
    promote: bool = False


def router() -> APIRouter:
    api = APIRouter(prefix="/projects/{project}/pipelines", tags=["pipelines"])

    @api.get("")
    def list_pipelines(
        project: str,
        console: Console = Depends(get_console),
        _: Principal = require("pipelines.read"),
    ) -> list[dict[str, Any]]:
        config = console.projects[project].pipelines()
        runner = console.runners.get(project)
        try:
            schedules = runner.schedules() if runner else {}
        except Exception:  # schedules are informative only
            schedules = {}
        return [
            {"name": name, "schedule": schedules.get(name), **(spec or {})}
            for name, spec in config.items()
        ]

    @api.get("/runs")
    def runs(
        project: str,
        limit: int = Query(50, ge=1, le=500),
        console: Console = Depends(get_console),
        _: Principal = require("pipelines.read"),
    ) -> list[dict[str, Any]]:
        runner = console.runners.get(project)
        return runner.runs(limit) if runner else []

    @api.get("/runs/{run_id}")
    def get_run(
        project: str,
        run_id: str,
        console: Console = Depends(get_console),
        _: Principal = require("pipelines.read"),
    ) -> dict[str, Any]:
        runner = console.runners.get(project)
        if runner is None:
            raise HTTPException(404, "No pipeline runner for this project")
        return runner.get(run_id)

    @api.post("/{pipeline}/runs", status_code=202)
    def start_run(
        project: str,
        pipeline: str,
        body: RunRequest,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        granted: dict[str, set[str]] = Depends(get_permissions),
        principal: Principal = require("pipelines.run"),
    ) -> dict[str, Any]:
        # A backfill rewrites history and a promotion changes what models see:
        # both need their own permission on top of pipelines.run.
        extra = (["features.backfill"] if body.start or body.end else []) + (
            ["features.promote"] if body.promote else []
        )
        missing = [p for p in extra if p not in granted.get(project, set())]
        if missing:
            raise HTTPException(403, f"Requires {', '.join(missing)}")
        runner = console.runners.get(project)
        if runner is None:
            raise HTTPException(404, "No pipeline runner for this project")
        run = runner.start(
            pipeline, start=body.start, end=body.end, promote=body.promote, actor=principal.email
        )
        console.audit(
            db,
            principal.email,
            "pipelines.run",
            pipeline,
            project=project,
            run=run["id"],
            **body.model_dump(),
        )
        return run

    return api


def module() -> ConsoleModule:
    return ConsoleModule(
        key=M,
        title="Pipelines",
        description="dbt transforms and feature materialisation: schedules, runs, backfills",
        status="ready",
        permissions=PERMISSIONS,
        read_permission="pipelines.read",
        router=router(),
        order=20,
    )
