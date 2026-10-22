from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from shalf_console.rbac.permissions import GLOBAL_SCOPE, PermissionCatalog, expand


@dataclass(frozen=True)
class Principal:
    """Who is asking: a user plus the SSO groups from their current session."""

    email: str
    groups: tuple[str, ...] = ()
    name: str = ""
    user_id: int | None = None


@dataclass
class Grant:
    subject_type: str
    subject: str
    scope: str
    permissions: list[str] = field(default_factory=list)  # patterns of the bound role
    binding_id: int | None = None


def effective_permissions(
    principal: Principal,
    grants: Iterable[Grant],
    catalog: PermissionCatalog,
    projects: Iterable[str],
) -> dict[str, set[str]]:
    """Permissions per scope: ``{"*": {...}, "<project>": {...}}``.

    A project's set includes everything granted globally. Global-only
    (admin) permissions are only ever granted by global bindings.
    """
    groups = {g.lower() for g in principal.groups}
    mine = [
        g
        for g in grants
        if (g.subject_type == "user" and g.subject.lower() == principal.email.lower())
        or (g.subject_type == "group" and g.subject.lower() in groups)
    ]
    global_keys = set()
    for grant in mine:
        if grant.scope == GLOBAL_SCOPE:
            global_keys |= expand(grant.permissions, catalog)

    result = {GLOBAL_SCOPE: global_keys}
    project_level = {p.key for p in catalog if not p.global_only}
    for project in projects:
        keys = set(global_keys)
        for grant in mine:
            if grant.scope == f"project:{project}":
                keys |= expand(grant.permissions, catalog) & project_level
        result[project] = keys
    return result
