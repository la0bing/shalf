"""Console modules: one per platform capability.

A module contributes permissions (to the RBAC catalog), API routes and a
status. The UI renders navigation and module cards from ``/api/modules``,
so a capability that becomes available - or a third-party module installed
through the ``shalf.console.modules`` entry point - appears without UI
changes to the shell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Literal

from fastapi import APIRouter

from shalf_console.rbac import Permission

Status = Literal["ready", "preview", "planned"]


@dataclass
class ConsoleModule:
    key: str
    title: str
    description: str
    status: Status
    permissions: list[Permission]
    read_permission: str
    project_scoped: bool = True
    router: APIRouter | None = None
    order: int = 100
    links: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "read_permission": self.read_permission,
            "project_scoped": self.project_scoped,
            "order": self.order,
        }


def default_modules() -> list[ConsoleModule]:
    from shalf_console.modules import (
        admin,
        features,
        models,
        monitoring,
        pipelines,
        serving,
        training,
    )

    modules = [
        features.module(),
        pipelines.module(),
        serving.module(),
        models.module(),
        training.module(),
        monitoring.module(),
        admin.module(),
    ]
    for ep in entry_points(group="shalf.console.modules"):
        modules.append(ep.load()())
    return sorted(modules, key=lambda m: m.order)
