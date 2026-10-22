"""Server-side sessions in an httpOnly cookie, plus double-submit CSRF.

The session cookie holds a random token; the database stores only its hash.
A second, script-readable cookie carries the CSRF token, which the SPA echoes
in the ``X-CSRF-Token`` header on every state-changing request.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Response
from sqlalchemy.orm import Session as DbSession

from shalf_console.db import Session, User, utcnow

SESSION_COOKIE = "shalf_session"
CSRF_COOKIE = "shalf_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: DbSession, user: User, *, groups: list[str], source: str, ttl: timedelta
) -> tuple[str, Session]:
    token = secrets.token_urlsafe(32)
    session = Session(
        id_hash=_hash(token),
        user_id=user.id,
        groups=groups,
        csrf_token=secrets.token_urlsafe(24),
        auth_source=source,
        expires_at=utcnow() + ttl,
    )
    db.add(session)
    user.last_login_at = utcnow()
    db.commit()
    return token, session


def load_session(db: DbSession, token: str | None) -> Session | None:
    if not token:
        return None
    session = db.get(Session, _hash(token))
    if session is None:
        return None
    expires = session.expires_at
    if expires.tzinfo is None:  # SQLite drops tz info
        expires = expires.replace(tzinfo=utcnow().tzinfo)
    if expires <= utcnow():
        db.delete(session)
        db.commit()
        return None
    return session


def delete_session(db: DbSession, token: str | None) -> None:
    if token and (session := db.get(Session, _hash(token))) is not None:
        db.delete(session)
        db.commit()


def csrf_ok(session: Session, header_value: str | None) -> bool:
    return bool(header_value) and hmac.compare_digest(session.csrf_token, header_value or "")


def set_session_cookies(
    response: Response, token: str, session: Session, *, secure: bool, ttl: timedelta
) -> None:
    max_age = int(ttl.total_seconds())
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        session.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
