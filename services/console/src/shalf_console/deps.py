"""Request dependencies: who is calling, and may they do this?"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DbSession

from shalf_console.context import Console
from shalf_console.db import Session, User
from shalf_console.rbac import GLOBAL_SCOPE, Principal
from shalf_console.security.sessions import CSRF_HEADER, SESSION_COOKIE, csrf_ok, load_session

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_console(request: Request) -> Console:
    return request.app.state.console


def get_db(console: Console = Depends(get_console)) -> Iterator[DbSession]:
    with console.sessions() as db:
        yield db


def get_session(request: Request, db: DbSession = Depends(get_db)) -> Session:
    session = load_session(db, request.cookies.get(SESSION_COOKIE))
    if session is None:
        raise HTTPException(401, "Not signed in")
    if request.method not in _SAFE_METHODS and not csrf_ok(
        session, request.headers.get(CSRF_HEADER)
    ):
        raise HTTPException(403, "Missing or invalid CSRF token")
    return session


def get_principal(
    request: Request, session: Session = Depends(get_session), db: DbSession = Depends(get_db)
) -> Principal:
    user = db.get(User, session.user_id)
    if user is None or user.disabled:
        raise HTTPException(401, "Account disabled")
    principal = Principal(
        email=user.email, groups=tuple(session.groups), name=user.name, user_id=user.id
    )
    request.state.principal = principal
    return principal


def get_permissions(
    request: Request,
    principal: Principal = Depends(get_principal),
    console: Console = Depends(get_console),
    db: DbSession = Depends(get_db),
) -> dict[str, set[str]]:
    cached = getattr(request.state, "permissions", None)
    if cached is None:
        cached = console.permissions_for(db, principal)
        request.state.permissions = cached
    return cached


def require(*permissions: str, project_scoped: bool = True, any_of: bool = False) -> Any:
    """Dependency enforcing permissions, in the URL's ``{project}`` scope if any.

    Unknown projects are 404. With ``any_of`` one listed permission suffices.
    """

    def check(
        request: Request,
        console: Console = Depends(get_console),
        granted: dict[str, set[str]] = Depends(get_permissions),
        principal: Principal = Depends(get_principal),
    ) -> Principal:
        scope = GLOBAL_SCOPE
        if project_scoped and "project" in request.path_params:
            scope = request.path_params["project"]
            if scope not in console.projects:
                raise HTTPException(404, f"Unknown project {scope!r}")
        have = granted.get(scope, set())
        ok = any(p in have for p in permissions) if any_of else all(p in have for p in permissions)
        if not ok:
            raise HTTPException(
                403, f"Requires {' or '.join(permissions) if any_of else ', '.join(permissions)}"
            )
        return principal

    return Depends(check)
