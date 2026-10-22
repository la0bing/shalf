from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from shalf.core import get_logger
from shalf.models import ModelRegistry, model_registry_registry
from shalf_console.db import AuditEvent, Role, RoleBinding, User, make_engine, make_sessionmaker
from shalf_console.modules.base import ConsoleModule
from shalf_console.projects import (
    KubernetesPipelineRunner,
    LocalProject,
    PipelineRunner,
    ProjectBackend,
    RemoteProject,
    ThreadPipelineRunner,
)
from shalf_console.rbac import BUILTIN_ROLES, GLOBAL_SCOPE, PermissionCatalog, Principal
from shalf_console.rbac.evaluator import Grant, effective_permissions
from shalf_console.security.oidc import OIDCClient
from shalf_console.security.passwords import hash_password
from shalf_console.settings import ConsoleSettings

log = get_logger(__name__)


class Console:
    """Everything a request handler needs, built once at start-up."""

    def __init__(
        self,
        settings: ConsoleSettings,
        modules: list[ConsoleModule],
        *,
        http: httpx.Client | None = None,
        projects: dict[str, ProjectBackend] | None = None,
        runners: dict[str, PipelineRunner] | None = None,
    ) -> None:
        self.settings = settings
        self.modules = modules
        self.http = http or httpx.Client(timeout=15)
        self.catalog = PermissionCatalog()
        for module in modules:
            self.catalog.add(*module.permissions)

        self.sessions: sessionmaker = make_sessionmaker(make_engine(settings.database_url))
        self.session_ttl = timedelta(hours=settings.session_ttl_hours)
        self.oidc = {p.id: OIDCClient(p, self.http) for p in settings.oidc}
        self.projects: dict[str, ProjectBackend] = projects or {}
        self.runners: dict[str, PipelineRunner] = runners or {}
        self._build_projects()
        self.model_registry: ModelRegistry = model_registry_registry.create(settings.model_registry)
        self._seed()

    # -- start-up ----------------------------------------------------------------
    def _build_projects(self) -> None:
        for config in self.settings.projects:
            if config.name in self.projects:
                continue
            if config.type == "local":
                if not config.path:
                    raise ValueError(f"Local project {config.name!r} needs a path")
                backend: ProjectBackend = LocalProject(
                    config.name, config.path, profile=config.profile, description=config.description
                )
            else:
                if not config.serving_url:
                    raise ValueError(f"Remote project {config.name!r} needs serving_url")
                backend = RemoteProject(
                    config.name,
                    serving_url=config.serving_url,
                    eda_url=config.eda_url,
                    admin_token=config.admin_token,
                    http=self.http,
                    description=config.description,
                )
            self.projects[config.name] = backend
            runner = dict(config.pipeline_runner)
            kind = runner.pop("type", "thread")
            if kind == "thread":
                if not isinstance(backend, LocalProject):
                    raise ValueError(
                        f"Project {config.name!r}: the thread runner needs a local project"
                    )
                self.runners[config.name] = ThreadPipelineRunner(backend, self.sessions)
            elif kind == "kubernetes":
                self.runners[config.name] = KubernetesPipelineRunner(**runner)
            else:
                raise ValueError(f"Unknown pipeline runner {kind!r}")

    def _seed(self) -> None:
        with self.sessions() as db:
            existing = {r.name: r for r in db.scalars(select(Role)).all()}
            for name, (description, permissions) in BUILTIN_ROLES.items():
                role = existing.get(name)
                if role is None:
                    db.add(
                        Role(
                            name=name,
                            description=description,
                            builtin=True,
                            permissions=permissions,
                        )
                    )
                else:  # keep built-ins in sync with the code
                    role.description, role.permissions, role.builtin = (
                        description,
                        permissions,
                        True,
                    )
            db.flush()
            admin = db.scalars(select(Role).where(Role.name == "admin")).one()
            for email in self.settings.bootstrap_admins:
                email = email.lower()
                # Break-glass: configured admins always have a global admin binding.
                exists = db.scalars(
                    select(RoleBinding).where(
                        RoleBinding.subject_type == "user",
                        RoleBinding.subject == email,
                        RoleBinding.role_id == admin.id,
                        RoleBinding.scope == GLOBAL_SCOPE,
                    )
                ).first()
                if exists is None:
                    db.add(
                        RoleBinding(
                            subject_type="user",
                            subject=email,
                            role_id=admin.id,
                            scope=GLOBAL_SCOPE,
                            created_by="bootstrap",
                        )
                    )
                user = db.scalars(select(User).where(User.email == email)).first()
                if user is None and self.settings.bootstrap_admin_password:
                    db.add(
                        User(
                            email=email,
                            name="Administrator",
                            source="local",
                            password_hash=hash_password(self.settings.bootstrap_admin_password),
                        )
                    )
            db.commit()

    # -- authorisation -------------------------------------------------------------
    def grants(self, db: DbSession) -> list[Grant]:
        rows = db.execute(
            select(
                RoleBinding.id,
                RoleBinding.subject_type,
                RoleBinding.subject,
                RoleBinding.scope,
                Role.permissions,
            ).join(Role, Role.id == RoleBinding.role_id)
        ).all()
        return [Grant(t, s, scope, list(p), binding_id=i) for i, t, s, scope, p in rows]

    def permissions_for(self, db: DbSession, principal: Principal) -> dict[str, set[str]]:
        return effective_permissions(principal, self.grants(db), self.catalog, self.projects)

    # -- audit ---------------------------------------------------------------------
    def audit(
        self,
        db: DbSession,
        actor: str,
        action: str,
        target: str = "",
        *,
        project: str | None = None,
        **detail: Any,
    ) -> None:
        db.add(
            AuditEvent(actor=actor, action=action, target=target, project=project, detail=detail)
        )
        db.commit()
        log.info("audit %s %s %s %s", actor, action, target, project or "")
