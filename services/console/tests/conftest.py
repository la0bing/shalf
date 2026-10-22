import base64
import hashlib
import secrets
import textwrap
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from shalf_console.app import create_app
from shalf_console.settings import ConsoleSettings, OIDCProvider, ProjectConfig

ADMIN = "admin@example.com"
ADMIN_PASSWORD = "correct-horse-battery"
ISSUER = "https://idp.example"


class FakeIdP:
    """A minimal OpenID provider: discovery, PKCE-checked token endpoint, JWKS."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "test-key"
        self.codes: dict[str, dict] = {}
        self.overrides: dict = {}
        app = FastAPI()

        @app.get("/.well-known/openid-configuration")
        def discovery():
            return {
                "issuer": ISSUER,
                "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token",
                "jwks_uri": f"{ISSUER}/jwks",
                "userinfo_endpoint": f"{ISSUER}/userinfo",
            }

        @app.get("/jwks")
        def jwks():
            jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
            return {"keys": [{**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}]}

        @app.post("/token")
        async def token(request: Request):
            form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
            code, code_verifier = form.get("code", ""), form.get("code_verifier", "")
            client_id, client_secret = form.get("client_id", ""), form.get("client_secret", "")
            grant = self.codes.pop(code, None)
            if grant is None or client_secret != "idp-secret":
                raise HTTPException(400, "invalid_grant")
            challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            if challenge.rstrip(b"=").decode() != grant["challenge"]:
                raise HTTPException(400, "invalid PKCE verifier")
            now = int(time.time())
            claims = {
                "iss": ISSUER,
                "aud": client_id,
                "sub": grant["email"],
                "iat": now,
                "exp": now + 300,
                "nonce": grant["nonce"],
                "email": grant["email"],
                "name": grant["name"],
                "groups": grant["groups"],
                **self.overrides,
            }
            token = jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": self.kid})
            return {"id_token": token, "access_token": "at", "token_type": "Bearer"}

        self.app = app

    def authorize(self, url: str, *, email: str, groups=(), name="Test User") -> str:
        """Simulate the user signing in at the IdP; returns the code."""
        query = parse_qs(urlparse(url).query)
        assert query["code_challenge_method"] == ["S256"]
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            "nonce": query["nonce"][0],
            "challenge": query["code_challenge"][0],
            "email": email,
            "groups": list(groups),
            "name": name,
        }
        return code


@pytest.fixture()
def idp():
    return FakeIdP()


@pytest.fixture()
def project_dir(tmp_path):
    """A tiny shalf project (no dbt) with one feature view."""
    root = tmp_path / "proj"
    (root / "features").mkdir(parents=True)
    (root / "shalf.yaml").write_text(
        textwrap.dedent(
            """
            project: demo
            definitions: [features]
            online_store: {type: sqlite, path: data/online.db}
            offline_store: {type: pandas, cache_path: data/cache}
            pipelines:
              refresh: {views: all}
            """
        )
    )
    (root / "features" / "demo_defs.py").write_text(
        textwrap.dedent(
            """
            from datetime import timedelta
            import pandas as pd
            from shalf.data import DataFrameSource, Entity, FeatureService, FeatureView
            from shalf.data.types import utcnow

            NOW = utcnow().floor("min")
            customer = Entity(name="customer", join_key="customer_id")
            scores = FeatureView(
                name="scores", entities=[customer], schema={"score": float},
                source=DataFrameSource(name="scores", timestamp_field="ts", df=pd.DataFrame({
                    "customer_id": [1, 2], "score": [0.5, 0.9],
                    "ts": [NOW - timedelta(hours=1)] * 2,
                })),
            )
            demo_service = FeatureService(name="demo", features=[scores])
            """
        )
    )
    return root


@pytest.fixture()
def settings(tmp_path, project_dir):
    return ConsoleSettings(
        database_url=f"sqlite:///{tmp_path / 'console.db'}",
        cookie_secure=False,
        base_url="http://testserver",
        bootstrap_admins=[ADMIN],
        bootstrap_admin_password=ADMIN_PASSWORD,
        oidc=[
            OIDCProvider(
                id="corp",
                name="Corp SSO",
                issuer=ISSUER,
                client_id="console",
                client_secret="idp-secret",
                scopes=["openid", "email", "profile", "groups"],
            )
        ],
        projects=[ProjectConfig(name="demo", type="local", path=str(project_dir))],
        model_registry={"type": "local", "root": str(tmp_path / "models")},
    )


@pytest.fixture()
def app(settings, idp):
    return create_app(settings, http=TestClient(idp.app, base_url=ISSUER))


def _login(client: TestClient, email: str = ADMIN, password: str = ADMIN_PASSWORD) -> TestClient:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies.get("shalf_csrf")
    return client


def _sso_login(
    client: TestClient, idp: FakeIdP, email: str, groups=(), return_to="/"
) -> TestClient:
    start = client.get(f"/auth/oidc/corp/login?return_to={return_to}", follow_redirects=False)
    assert start.status_code == 302, start.text
    code = idp.authorize(start.headers["location"], email=email, groups=groups)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    done = client.get(f"/auth/oidc/corp/callback?state={state}&code={code}", follow_redirects=False)
    assert done.status_code == 302 and "error" not in done.headers["location"], done.headers
    client.headers["X-CSRF-Token"] = client.cookies.get("shalf_csrf")
    return client


@pytest.fixture()
def admin(app):
    with TestClient(app) as client:
        yield _login(client)


def _make_user(admin: TestClient, email: str, role: str | None, scope: str = "*") -> None:
    assert (
        admin.post(
            "/api/admin/users", json={"email": email, "password": "a-long-password-1"}
        ).status_code
        == 201
    )
    if role:
        body = {"subject_type": "user", "subject": email, "role": role, "scope": scope}
        assert admin.post("/api/admin/bindings", json=body).status_code == 201


@pytest.fixture()
def login():
    return _login


@pytest.fixture()
def sso_login(idp):
    return lambda client, email, groups=(), return_to="/": _sso_login(
        client, idp, email, groups, return_to
    )


@pytest.fixture()
def make_user(admin):
    return lambda email, role=None, scope="*": _make_user(admin, email, role, scope)


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def other(app):
    """A second browser, for signing in as someone else."""
    with TestClient(app) as c:
        yield c
