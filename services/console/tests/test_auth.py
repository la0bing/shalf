"""Local login, sessions, CSRF and OIDC single sign-on."""

import time
from urllib.parse import parse_qs, urlparse

import jwt


def test_local_login_session_and_logout(client, login):
    assert client.get("/api/me").status_code == 401
    assert (
        client.post(
            "/auth/login", json={"email": "admin@example.com", "password": "wrong"}
        ).status_code
        == 401
    )
    login(client)
    me = client.get("/api/me").json()
    assert me["email"] == "admin@example.com"
    assert "admin.roles.manage" in me["permissions"]["*"]
    cookie = client.cookies  # httpOnly session, readable CSRF cookie
    assert cookie.get("shalf_session") and cookie.get("shalf_csrf")

    assert client.post("/auth/logout").status_code == 200
    assert client.get("/api/me").status_code == 401


def test_state_changing_requests_need_csrf(client, login):
    login(client)
    token = client.headers.pop("X-CSRF-Token")
    body = {"name": "x-role", "permissions": ["features.read"]}
    assert client.post("/api/admin/roles", json=body).status_code == 403
    client.headers["X-CSRF-Token"] = token
    assert client.post("/api/admin/roles", json=body).status_code == 201


def test_security_headers(client):
    response = client.get("/api/health")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def test_sso_login_provisions_user_with_groups(client, sso_login, admin):
    providers = client.get("/api/auth/providers").json()
    assert providers == {
        "local": True,
        "oidc": [{"id": "corp", "name": "Corp SSO", "login_url": "/auth/oidc/corp/login"}],
    }

    # No bindings yet: signed in, but no access.
    sso_login(client, "dana@example.com", groups=["ml-team"])
    me = client.get("/api/me").json()
    assert me["groups"] == ["ml-team"] and me["auth_source"] == "corp"
    assert me["permissions"]["demo"] == []
    assert client.get("/api/projects/demo/features/views").status_code == 403

    # Admin grants the SSO *group* a role: membership is managed in the IdP.
    body = {
        "subject_type": "group",
        "subject": "ml-team",
        "role": "ml-engineer",
        "scope": "project:demo",
    }
    assert admin.post("/api/admin/bindings", json=body).status_code == 201
    assert client.get("/api/projects/demo/features/views").status_code == 200
    assert "features.promote" in client.get("/api/me").json()["permissions"]["demo"]


def test_sso_redirect_is_same_origin_only(client, idp):
    for unsafe in ("//evil.example/x", "https://evil.example", "/\\evil.example"):
        start = client.get(
            "/auth/oidc/corp/login", params={"return_to": unsafe}, follow_redirects=False
        )
        code = idp.authorize(start.headers["location"], email="e@example.com")
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        done = client.get(
            f"/auth/oidc/corp/callback?state={state}&code={code}", follow_redirects=False
        )
        assert done.headers["location"] == "/"

    start = client.get(
        "/auth/oidc/corp/login", params={"return_to": "/features"}, follow_redirects=False
    )
    code = idp.authorize(start.headers["location"], email="e@example.com")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    done = client.get(f"/auth/oidc/corp/callback?state={state}&code={code}", follow_redirects=False)
    assert done.headers["location"] == "/features"


def test_sso_rejects_bad_tokens(client, idp, settings):
    def attempt(**overrides):
        idp.overrides = overrides
        start = client.get("/auth/oidc/corp/login", follow_redirects=False)
        code = idp.authorize(start.headers["location"], email="mallory@example.com")
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        done = client.get(
            f"/auth/oidc/corp/callback?state={state}&code={code}", follow_redirects=False
        )
        return done.headers["location"]

    assert "error=" in attempt(aud="someone-else")
    assert "error=" in attempt(nonce="replayed")
    assert "error=" in attempt(iss="https://evil.example")
    assert "error=" in attempt(exp=int(time.time()) - 3600)
    assert "error=" in attempt(email_verified=False)
    idp.overrides = {}
    assert "error=" not in attempt()


def test_sso_state_is_single_use_and_unsigned_tokens_fail(client, idp):
    start = client.get("/auth/oidc/corp/login", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    code = idp.authorize(start.headers["location"], email="x@example.com")
    assert (
        "error"
        not in client.get(
            f"/auth/oidc/corp/callback?state={state}&code={code}", follow_redirects=False
        ).headers["location"]
    )
    replay = client.get(
        f"/auth/oidc/corp/callback?state={state}&code={code}", follow_redirects=False
    )
    assert "error=" in replay.headers["location"]

    from shalf_console.security.oidc import OIDCClient, OIDCError

    forged = jwt.encode(
        {"iss": "https://idp.example", "aud": "console"}, "secret", algorithm="HS256"
    )
    oidc: OIDCClient = client.app.state.console.oidc["corp"]
    try:
        oidc.verify_id_token(forged, nonce="n")
        raise AssertionError("HS256 token accepted")
    except OIDCError as exc:
        assert "not allowed" in str(exc)


def test_allowed_domains_and_disabled_users(app, idp, client, sso_login, admin):
    app.state.console.oidc["corp"].provider.allowed_domains = ["example.com"]
    start = client.get("/auth/oidc/corp/login", follow_redirects=False)
    code = idp.authorize(start.headers["location"], email="intruder@other.org")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    done = client.get(f"/auth/oidc/corp/callback?state={state}&code={code}", follow_redirects=False)
    assert "domain" in done.headers["location"]

    sso_login(client, "leaver@example.com")
    user = next(
        u for u in admin.get("/api/admin/users").json() if u["email"] == "leaver@example.com"
    )
    assert admin.patch(f"/api/admin/users/{user['id']}", json={"disabled": True}).status_code == 200
    assert client.get("/api/me").status_code == 401  # existing session stops working
