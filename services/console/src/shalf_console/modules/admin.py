"""Administration: users, custom roles, access (role bindings), audit, settings."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from shalf_console.context import Console
from shalf_console.db import AuditEvent, Role, RoleBinding, User, utcnow
from shalf_console.deps import get_console, get_db, require
from shalf_console.modules.base import ConsoleModule
from shalf_console.rbac import GLOBAL_SCOPE, Permission, Principal
from shalf_console.rbac.evaluator import effective_permissions
from shalf_console.security.passwords import hash_password

M = "admin"
PERMISSIONS = [
    Permission("admin.users.read", "List users and their access", M, global_only=True),
    Permission("admin.users.manage", "Create, edit and disable users", M, global_only=True),
    Permission("admin.roles.manage", "Create, edit and delete custom roles", M, global_only=True),
    Permission("admin.bindings.manage", "Grant and revoke roles", M, global_only=True),
    Permission("admin.audit.read", "Read the audit log", M, global_only=True),
    Permission("admin.settings.read", "See SSO and project settings", M, global_only=True),
]
_ROLE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


class RoleIn(BaseModel):
    name: str
    description: str = ""
    permissions: list[str] = Field(min_length=1)


class UserIn(BaseModel):
    email: str
    name: str = ""
    password: str | None = Field(default=None, min_length=12)


class UserPatch(BaseModel):
    name: str | None = None
    disabled: bool | None = None
    password: str | None = Field(default=None, min_length=12)


class BindingIn(BaseModel):
    subject_type: Literal["user", "group"]
    subject: str = Field(min_length=1)
    role: str
    scope: str = GLOBAL_SCOPE


def _role_dict(role: Role, bindings: int = 0) -> dict[str, Any]:
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "builtin": role.builtin,
        "permissions": role.permissions,
        "bindings": bindings,
        "updated_at": role.updated_at.isoformat() if role.updated_at else None,
    }


def _user_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "source": user.source,
        "disabled": user.disabled,
        "has_password": bool(user.password_hash),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _binding_dict(binding: RoleBinding, role_name: str) -> dict[str, Any]:
    return {
        "id": binding.id,
        "subject_type": binding.subject_type,
        "subject": binding.subject,
        "role": role_name,
        "scope": binding.scope,
        "created_at": binding.created_at.isoformat() if binding.created_at else None,
        "created_by": binding.created_by,
    }


def router() -> APIRouter:
    api = APIRouter(prefix="/admin", tags=["admin"])
    G = {"project_scoped": False}

    @api.get("/permissions")
    def permissions(
        console: Console = Depends(get_console),
        _: Principal = require(
            "admin.roles.manage", "admin.bindings.manage", "admin.users.read", any_of=True, **G
        ),
    ) -> list[dict[str, Any]]:
        titles = {m.key: m.title for m in console.modules}
        return [
            {
                "module": module,
                "title": titles.get(module, module),
                "permissions": [
                    {"key": p.key, "description": p.description, "global_only": p.global_only}
                    for p in perms
                ],
            }
            for module, perms in console.catalog.by_module().items()
        ]

    # -- roles -----------------------------------------------------------------------
    @api.get("/roles")
    def list_roles(
        db: DbSession = Depends(get_db),
        _: Principal = require(
            "admin.roles.manage", "admin.bindings.manage", "admin.users.read", any_of=True, **G
        ),
    ) -> list[dict[str, Any]]:
        counts: dict[int, int] = dict(
            db.execute(
                select(RoleBinding.role_id, func.count()).group_by(RoleBinding.role_id)
            ).all()
        )
        roles = db.scalars(select(Role).order_by(Role.builtin.desc(), Role.name)).all()
        return [_role_dict(r, counts.get(r.id, 0)) for r in roles]

    def _validate(
        console: Console, db: DbSession, body: RoleIn, role_id: int | None = None
    ) -> list[str]:
        if not _ROLE_NAME.match(body.name):
            raise HTTPException(422, "Role names are 2-63 lowercase letters, digits and dashes")
        clash = db.scalars(select(Role).where(Role.name == body.name)).first()
        if clash is not None and clash.id != role_id:
            raise HTTPException(409, f"Role {body.name!r} already exists")
        try:
            return console.catalog.validate_patterns(body.permissions)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @api.post("/roles", status_code=201)
    def create_role(
        body: RoleIn,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        principal: Principal = require("admin.roles.manage", **G),
    ) -> dict[str, Any]:
        patterns = _validate(console, db, body)
        role = Role(name=body.name, description=body.description, permissions=patterns)
        db.add(role)
        db.commit()
        console.audit(db, principal.email, "role.create", role.name, permissions=patterns)
        return _role_dict(role)

    @api.put("/roles/{role_id}")
    def update_role(
        role_id: int,
        body: RoleIn,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        principal: Principal = require("admin.roles.manage", **G),
    ) -> dict[str, Any]:
        role = db.get(Role, role_id)
        if role is None:
            raise HTTPException(404, "Unknown role")
        if role.builtin:
            raise HTTPException(
                409, "Built-in roles cannot be changed; create a custom role instead"
            )
        patterns = _validate(console, db, body, role_id)
        before = list(role.permissions)
        role.name, role.description, role.permissions = body.name, body.description, patterns
        role.updated_at = utcnow()
        db.commit()
        console.audit(db, principal.email, "role.update", role.name, before=before, after=patterns)
        return _role_dict(role)

    @api.delete("/roles/{role_id}", status_code=204)
    def delete_role(
        role_id: int,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        principal: Principal = require("admin.roles.manage", **G),
    ) -> None:
        role = db.get(Role, role_id)
        if role is None:
            raise HTTPException(404, "Unknown role")
        if role.builtin:
            raise HTTPException(409, "Built-in roles cannot be deleted")
        in_use = db.scalar(select(func.count()).where(RoleBinding.role_id == role_id))
        if in_use:
            raise HTTPException(409, f"Role is granted by {in_use} binding(s); revoke them first")
        db.delete(role)
        db.commit()
        console.audit(db, principal.email, "role.delete", role.name)

    # -- users -------------------------------------------------------------------------
    @api.get("/users")
    def list_users(
        db: DbSession = Depends(get_db), _: Principal = require("admin.users.read", **G)
    ) -> list[dict[str, Any]]:
        return [_user_dict(u) for u in db.scalars(select(User).order_by(User.email)).all()]

    @api.post("/users", status_code=201)
    def create_user(
        body: UserIn,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        principal: Principal = require("admin.users.manage", **G),
    ) -> dict[str, Any]:
        email = body.email.strip().lower()
        if not _EMAIL.match(email):
            raise HTTPException(422, "Invalid email")
        if db.scalars(select(User).where(User.email == email)).first():
            raise HTTPException(409, "User already exists")
        user = User(
            email=email,
            name=body.name or email,
            source="local",
            password_hash=hash_password(body.password) if body.password else None,
        )
        db.add(user)
        db.commit()
        console.audit(db, principal.email, "user.create", email, local_password=bool(body.password))
        return _user_dict(user)

    @api.patch("/users/{user_id}")
    def update_user(
        user_id: int,
        body: UserPatch,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        principal: Principal = require("admin.users.manage", **G),
    ) -> dict[str, Any]:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(404, "Unknown user")
        if body.disabled and user.email == principal.email:
            raise HTTPException(409, "You cannot disable your own account")
        changes = body.model_dump(exclude_none=True, exclude={"password"})
        if body.name is not None:
            user.name = body.name
        if body.disabled is not None:
            user.disabled = body.disabled
        if body.password:
            user.password_hash = hash_password(body.password)
            changes["password"] = "changed"
        db.commit()
        console.audit(db, principal.email, "user.update", user.email, **changes)
        return _user_dict(user)

    # -- access (role bindings) --------------------------------------------------------
    @api.get("/bindings")
    def list_bindings(
        db: DbSession = Depends(get_db),
        _: Principal = require("admin.bindings.manage", "admin.users.read", any_of=True, **G),
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            select(RoleBinding, Role.name)
            .join(Role, Role.id == RoleBinding.role_id)
            .order_by(RoleBinding.subject_type, RoleBinding.subject)
        ).all()
        return [_binding_dict(b, name) for b, name in rows]

    @api.post("/bindings", status_code=201)
    def create_binding(
        body: BindingIn,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        principal: Principal = require("admin.bindings.manage", **G),
    ) -> dict[str, Any]:
        role = db.scalars(select(Role).where(Role.name == body.role)).first()
        if role is None:
            raise HTTPException(404, f"Unknown role {body.role!r}")
        if body.scope != GLOBAL_SCOPE:
            project = body.scope.removeprefix("project:")
            if not body.scope.startswith("project:") or project not in console.projects:
                raise HTTPException(422, "Scope must be '*' or 'project:<known project>'")
        subject = (
            body.subject.strip().lower() if body.subject_type == "user" else body.subject.strip()
        )
        duplicate = db.scalars(
            select(RoleBinding).where(
                RoleBinding.subject_type == body.subject_type,
                RoleBinding.subject == subject,
                RoleBinding.role_id == role.id,
                RoleBinding.scope == body.scope,
            )
        ).first()
        if duplicate is not None:
            raise HTTPException(409, "This binding already exists")
        binding = RoleBinding(
            subject_type=body.subject_type,
            subject=subject,
            role_id=role.id,
            scope=body.scope,
            created_by=principal.email,
        )
        db.add(binding)
        db.commit()
        console.audit(
            db,
            principal.email,
            "binding.create",
            f"{body.subject_type}:{subject}",
            role=role.name,
            scope=body.scope,
        )
        return _binding_dict(binding, role.name)

    @api.delete("/bindings/{binding_id}", status_code=204)
    def delete_binding(
        binding_id: int,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
        principal: Principal = require("admin.bindings.manage", **G),
    ) -> None:
        binding = db.get(RoleBinding, binding_id)
        if binding is None:
            raise HTTPException(404, "Unknown binding")
        # Refuse to let admins lock themselves out of access management.
        remaining = [g for g in console.grants(db) if g.binding_id != binding.id]
        after = effective_permissions(principal, remaining, console.catalog, [])
        if "admin.bindings.manage" not in after[GLOBAL_SCOPE]:
            raise HTTPException(
                409, "This would remove your own access management; ask another admin"
            )
        role = db.get(Role, binding.role_id)
        db.delete(binding)
        db.commit()
        console.audit(
            db,
            principal.email,
            "binding.delete",
            f"{binding.subject_type}:{binding.subject}",
            role=role.name if role else None,
            scope=binding.scope,
        )

    # -- audit & settings ----------------------------------------------------------------
    @api.get("/audit")
    def audit(
        limit: int = Query(100, ge=1, le=1000),
        action: str | None = None,
        actor: str | None = None,
        db: DbSession = Depends(get_db),
        _: Principal = require("admin.audit.read", **G),
    ) -> list[dict[str, Any]]:
        query = select(AuditEvent).order_by(AuditEvent.at.desc(), AuditEvent.id.desc()).limit(limit)
        if action:
            query = query.where(AuditEvent.action.startswith(action))
        if actor:
            query = query.where(AuditEvent.actor == actor.lower())
        return [
            {
                "id": e.id,
                "at": e.at.isoformat(),
                "actor": e.actor,
                "action": e.action,
                "target": e.target,
                "project": e.project,
                "detail": e.detail,
            }
            for e in db.scalars(query).all()
        ]

    @api.get("/settings")
    def settings(
        console: Console = Depends(get_console), _: Principal = require("admin.settings.read", **G)
    ) -> dict[str, Any]:
        s = console.settings
        return {
            "local_login": s.local_login,
            "session_ttl_hours": s.session_ttl_hours,
            "bootstrap_admins": s.bootstrap_admins,
            "oidc": [
                {
                    "id": p.id,
                    "name": p.name,
                    "issuer": p.issuer,
                    "client_id": p.client_id,
                    "scopes": p.scopes,
                    "groups_claim": p.groups_claim,
                    "allowed_domains": p.allowed_domains,
                }
                for p in s.oidc
            ],
            "projects": [
                {
                    "name": name,
                    "backend": backend.kind,
                    "pipeline_runner": getattr(console.runners.get(name), "kind", None),
                }
                for name, backend in console.projects.items()
            ],
            "model_registry": s.model_registry.get("type"),
        }

    return api


def module() -> ConsoleModule:
    return ConsoleModule(
        key=M,
        title="Admin",
        description="Users, roles, access, audit log and SSO settings",
        status="ready",
        permissions=PERMISSIONS,
        read_permission="admin.users.read",
        project_scoped=False,
        router=router(),
        order=90,
    )
