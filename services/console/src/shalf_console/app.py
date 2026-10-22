from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from shalf.core import configure_logging, get_logger
from shalf_console.context import Console
from shalf_console.db import OIDCLogin, Session, User, utcnow
from shalf_console.deps import get_console, get_db, get_permissions, get_principal, get_session
from shalf_console.modules import ConsoleModule, default_modules
from shalf_console.projects import BackendError, PipelineRunner, ProjectBackend
from shalf_console.rbac import GLOBAL_SCOPE, Principal
from shalf_console.security.oidc import OIDCError, pkce_pair
from shalf_console.security.passwords import verify_password
from shalf_console.security.sessions import (
    SESSION_COOKIE,
    clear_session_cookies,
    create_session,
    delete_session,
    set_session_cookies,
)
from shalf_console.settings import ConsoleSettings

log = get_logger(__name__)
_LOGIN_TTL_SECONDS = 600
_STATIC = Path(__file__).parent / "static"


class LoginRequest(BaseModel):
    email: str
    password: str


def _safe_return_to(value: str | None) -> str:
    """Only same-origin paths: never redirect to another site after login."""
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/"


def auth_router() -> APIRouter:
    api = APIRouter(tags=["auth"])

    @api.get("/api/auth/providers")
    def providers(console: Console = Depends(get_console)) -> dict[str, Any]:
        return {
            "local": console.settings.local_login,
            "oidc": [
                {"id": p.id, "name": p.name, "login_url": f"/auth/oidc/{p.id}/login"}
                for p in console.settings.oidc
            ],
        }

    @api.post("/auth/login")
    def login(
        body: LoginRequest,
        response: Response,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
    ) -> dict[str, bool]:
        if not console.settings.local_login:
            raise HTTPException(404, "Local login is disabled; use single sign-on")
        email = body.email.strip().lower()
        user = db.scalars(select(User).where(User.email == email)).first()
        ok = verify_password(body.password, user.password_hash if user else None)
        if not ok or user is None or user.disabled:
            console.audit(db, email, "auth.login_failed", "local")
            raise HTTPException(401, "Invalid email or password")
        token, session = create_session(
            db, user, groups=[], source="local", ttl=console.session_ttl
        )
        set_session_cookies(
            response, token, session, secure=console.settings.cookie_secure, ttl=console.session_ttl
        )
        console.audit(db, email, "auth.login", "local")
        return {"ok": True}

    @api.post("/auth/logout")
    def logout(
        request: Request,
        response: Response,
        console: Console = Depends(get_console),
        session: Session = Depends(get_session),
        db: DbSession = Depends(get_db),
    ) -> dict[str, bool]:
        user = db.get(User, session.user_id)
        delete_session(db, request.cookies.get(SESSION_COOKIE))
        clear_session_cookies(response)
        console.audit(db, user.email if user else "?", "auth.logout")
        return {"ok": True}

    @api.get("/auth/oidc/{provider}/login")
    def oidc_login(
        provider: str,
        return_to: str | None = None,
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
    ) -> RedirectResponse:
        client = console.oidc.get(provider)
        if client is None:
            raise HTTPException(404, "Unknown identity provider")
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        verifier, challenge = pkce_pair()
        db.add(
            OIDCLogin(
                state=state,
                provider=provider,
                nonce=nonce,
                code_verifier=verifier,
                return_to=_safe_return_to(return_to),
            )
        )
        db.commit()
        url = client.authorization_url(
            redirect_uri=_redirect_uri(console, provider),
            state=state,
            nonce=nonce,
            challenge=challenge,
        )
        return RedirectResponse(url, status_code=302)

    @api.get("/auth/oidc/{provider}/callback")
    def oidc_callback(
        provider: str,
        state: str = "",
        code: str = "",
        error: str = "",
        console: Console = Depends(get_console),
        db: DbSession = Depends(get_db),
    ) -> RedirectResponse:
        def fail(reason: str) -> RedirectResponse:
            console.audit(db, "?", "auth.login_failed", provider, reason=reason)
            return RedirectResponse(f"/login?error={quote(reason)}", status_code=302)

        client = console.oidc.get(provider)
        pending = db.get(OIDCLogin, state) if state else None
        if client is None or pending is None or pending.provider != provider:
            return fail("Login expired or invalid; please try again")
        db.delete(pending)  # single use
        db.commit()
        created = (
            pending.created_at
            if pending.created_at.tzinfo
            else pending.created_at.replace(tzinfo=utcnow().tzinfo)
        )
        if (utcnow() - created).total_seconds() > _LOGIN_TTL_SECONDS:
            return fail("Login expired; please try again")
        if error or not code:
            return fail(f"Identity provider returned: {error or 'no code'}")
        try:
            tokens = client.exchange_code(
                code=code,
                redirect_uri=_redirect_uri(console, provider),
                verifier=pending.code_verifier,
            )
            claims = client.verify_id_token(tokens["id_token"], nonce=pending.nonce)
            extra = {}
            if client.provider.groups_claim not in claims and tokens.get("access_token"):
                extra = client.userinfo(tokens["access_token"])
            email, name, groups = client.identity(claims, extra)
        except (OIDCError, httpx.HTTPError) as exc:
            log.warning("OIDC login via %s failed: %s", provider, exc)
            return fail(str(exc))

        user = db.scalars(select(User).where(User.email == email)).first()
        if user is None:  # just-in-time provisioning; access still comes from bindings
            user = User(email=email, name=name, source=provider)
            db.add(user)
            db.commit()
        elif user.disabled:
            return fail("Account disabled")
        else:
            user.name = name or user.name
        token, session = create_session(
            db, user, groups=groups, source=provider, ttl=console.session_ttl
        )
        redirect = RedirectResponse(pending.return_to, status_code=302)
        set_session_cookies(
            redirect, token, session, secure=console.settings.cookie_secure, ttl=console.session_ttl
        )
        console.audit(db, email, "auth.login", provider, groups=groups)
        return redirect

    return api


def _redirect_uri(console: Console, provider: str) -> str:
    return f"{console.settings.base_url.rstrip('/')}/auth/oidc/{provider}/callback"


def core_router() -> APIRouter:
    api = APIRouter(prefix="/api", tags=["core"])

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/me")
    def me(
        session: Session = Depends(get_session),
        principal: Principal = Depends(get_principal),
        granted: dict[str, set[str]] = Depends(get_permissions),
    ) -> dict[str, Any]:
        return {
            "email": principal.email,
            "name": principal.name,
            "groups": list(principal.groups),
            "auth_source": session.auth_source,
            "permissions": {scope: sorted(keys) for scope, keys in granted.items()},
        }

    @api.get("/modules")
    def modules(
        console: Console = Depends(get_console),
        granted: dict[str, set[str]] = Depends(get_permissions),
    ) -> list[dict[str, Any]]:
        out = []
        for module in console.modules:
            if module.project_scoped:
                accessible = any(module.read_permission in keys for keys in granted.values())
            else:
                accessible = module.read_permission in granted[GLOBAL_SCOPE] or (
                    module.key == "admin"
                    and any(k.startswith("admin.") for k in granted[GLOBAL_SCOPE])
                )
            out.append({**module.summary(), "accessible": accessible})
        return out

    @api.get("/projects")
    def projects(
        console: Console = Depends(get_console),
        granted: dict[str, set[str]] = Depends(get_permissions),
    ) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": backend.description,
                "backend": backend.kind,
                "pipeline_runner": getattr(console.runners.get(name), "kind", None),
                "permissions": sorted(granted.get(name, set())),
            }
            for name, backend in console.projects.items()
            if granted.get(name)
        ]

    return api


def create_app(
    settings: ConsoleSettings | None = None,
    *,
    modules: list[ConsoleModule] | None = None,
    http: httpx.Client | None = None,
    projects: dict[str, ProjectBackend] | None = None,
    runners: dict[str, PipelineRunner] | None = None,
) -> FastAPI:
    configure_logging()
    settings = settings or ConsoleSettings.load()
    modules = modules if modules is not None else default_modules()
    app = FastAPI(
        title="shalf console",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.console = Console(settings, modules, http=http, projects=projects, runners=runners)

    @app.exception_handler(BackendError)
    def backend_error(_: Request, exc: BackendError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith(("/api", "/auth")):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(auth_router())
    app.include_router(core_router())
    for module in modules:
        if module.router is not None:
            app.include_router(module.router, prefix="/api")

    static = settings.static_dir or os.environ.get("SHALF_CONSOLE_STATIC")
    _mount_spa(app, Path(static) if static else _STATIC)
    return app


def _mount_spa(app: FastAPI, static: Path) -> None:
    """Serve the built single-page app; unknown non-API paths get index.html."""
    index = static / "index.html"
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path.startswith(("api/", "auth/")):
            raise HTTPException(404)
        file = (static / path).resolve()
        if path and file.is_file() and static.resolve() in file.parents:
            return FileResponse(file)
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse(
            {"detail": "Console UI not built. Run `npm run build` in services/console/web."}, 404
        )
