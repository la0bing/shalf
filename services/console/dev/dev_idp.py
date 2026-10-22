"""A tiny OpenID Connect provider for local development and end-to-end tests.

    uv run python services/console/dev/dev_idp.py            # http://127.0.0.1:9555

Environment: DEV_IDP_ISSUER (the URL browsers *and* the console use),
DEV_IDP_HOST, DEV_IDP_PORT.

It shows a sign-in form where you type any email and groups, so you can try
SSO and group-based roles without a real identity provider. Never expose it:
it signs whatever identity you type.
"""

from __future__ import annotations

import base64
import hashlib
import html
import secrets
import time
from urllib.parse import parse_qs, urlencode

import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

CLIENT_ID, CLIENT_SECRET = "shalf-console", "dev-secret"


def create_idp(issuer: str) -> FastAPI:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    codes: dict[str, dict] = {}
    app = FastAPI(title="shalf dev IdP")

    @app.get("/.well-known/openid-configuration")
    def discovery() -> dict:
        return {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/authorize",
            "token_endpoint": f"{issuer}/token",
            "jwks_uri": f"{issuer}/jwks",
            "response_types_supported": ["code"],
            "id_token_signing_alg_values_supported": ["RS256"],
        }

    @app.get("/jwks")
    def jwks() -> dict:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": "dev", "alg": "RS256", "use": "sig"}]}

    @app.get("/authorize", response_class=HTMLResponse)
    def authorize(request: Request) -> str:
        hidden = "".join(
            f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
            for k, v in request.query_params.items()
        )
        return f"""<!doctype html><html><head><title>Dev IdP sign-in</title>
<style>body{{font:15px system-ui;display:grid;place-items:center;min-height:90vh;background:#f2f4f7}}
form{{background:#fff;padding:28px;border-radius:12px;display:grid;gap:12px;width:340px;box-shadow:0 2px 8px #0002}}
input{{padding:8px;font:inherit}}button{{padding:9px;font:inherit;background:#111;color:#fff;border:0;border-radius:8px}}</style></head>
<body><form method="post" action="/authorize"><h2 style="margin:0">Dev identity provider</h2>
<label>Email<br><input name="email" type="email" required value="analyst@example.com"></label>
<label>Name<br><input name="name" value="Ada Analyst"></label>
<label>Groups (comma separated)<br><input name="groups" value="analysts"></label>
{hidden}<button type="submit">Sign in</button></form></body></html>"""

    @app.post("/authorize")
    async def approve(request: Request) -> RedirectResponse:
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        if form.get("client_id") != CLIENT_ID:
            raise HTTPException(400, "unknown client")
        code = secrets.token_urlsafe(16)
        codes[code] = {
            "email": form["email"].lower(),
            "name": form.get("name", ""),
            "groups": [g.strip() for g in form.get("groups", "").split(",") if g.strip()],
            "nonce": form.get("nonce"),
            "challenge": form.get("code_challenge"),
            "redirect_uri": form["redirect_uri"],
        }
        query = urlencode({"code": code, "state": form.get("state", "")})
        return RedirectResponse(f"{form['redirect_uri']}?{query}", status_code=302)

    @app.post("/token")
    async def token(request: Request) -> dict:
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        grant = codes.pop(form.get("code", ""), None)
        if grant is None or form.get("client_secret") != CLIENT_SECRET:
            raise HTTPException(400, "invalid_grant")
        if form.get("redirect_uri") != grant["redirect_uri"]:
            raise HTTPException(400, "redirect_uri mismatch")
        verifier = form.get("code_verifier", "").encode()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier).digest()).rstrip(b"=").decode()
        )
        if challenge != grant["challenge"]:
            raise HTTPException(400, "PKCE verification failed")
        now = int(time.time())
        claims = {
            "iss": issuer,
            "aud": CLIENT_ID,
            "sub": grant["email"],
            "iat": now,
            "exp": now + 300,
            "nonce": grant["nonce"],
            "email": grant["email"],
            "email_verified": True,
            "name": grant["name"],
            "groups": grant["groups"],
        }
        id_token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "dev"})
        return {
            "id_token": id_token,
            "access_token": secrets.token_urlsafe(16),
            "token_type": "Bearer",
        }

    return app


if __name__ == "__main__":
    import os

    uvicorn.run(
        create_idp(os.environ.get("DEV_IDP_ISSUER", "http://127.0.0.1:9555")),
        host=os.environ.get("DEV_IDP_HOST", "127.0.0.1"),
        port=int(os.environ.get("DEV_IDP_PORT", "9555")),
    )
