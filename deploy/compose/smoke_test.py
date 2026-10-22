"""Smoke test for the running docker compose PoC (standard library only).

    docker compose -f deploy/compose/docker-compose.yml up -d --build
    python deploy/compose/smoke_test.py

Checks every service from the outside, including a full SSO login through the
dev identity provider and a pipeline run started from the console.
"""

from __future__ import annotations

import html.parser
import http.cookiejar
import json
import time
import urllib.parse
import urllib.request

CONSOLE, SERVING, EDA = "http://localhost:8090", "http://localhost:8080", "http://localhost:8081"
ADMIN_TOKEN = "poc-admin-token"


def call(opener, url, body=None, headers=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def wait_until_ready(timeout=180):
    deadline = time.time() + timeout
    for url in (f"{CONSOLE}/api/health", f"{SERVING}/readyz", f"{EDA}/readyz"):
        while True:
            try:
                urllib.request.urlopen(url, timeout=5)
                break
            except OSError:
                if time.time() > deadline:
                    raise AssertionError(f"{url} not ready") from None
                time.sleep(2)


def browser():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def csrf(jar):
    return next(c.value for c in jar if c.name == "shalf_csrf")


class _Form(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields, self.action = {}, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.action = attrs.get("action")
        if tag == "input" and attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")


def main():
    wait_until_ready()

    # Online serving (Redis primary) and request-time features. On a fresh
    # start, wait for the scheduler's first daily + hourly runs.
    deadline = time.time() + 300
    while True:
        status, online = call(urllib.request.build_opener(), f"{SERVING}/v1/features/online", {
            "entities": {"customer_id": [1, 2]}, "feature_service": "fraud_model_v1",
            "request_data": {"amount": [120.0, 15.5]}})  # fmt: skip
        ready = status == 200 and all(
            v is not None for k in ("txn_count_7d", "risky_spend_ratio_7d", "age")
            for v in online["results"][k]
        )  # fmt: skip
        if ready:
            break
        assert time.time() < deadline, f"features never materialised: {online}"
        time.sleep(3)
    print("ok  feature-server: online lookup", online["results"]["txn_count_7d"])

    # Exploration server: replica, offline cache, read-only.
    plain = urllib.request.build_opener()
    auth = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    status, preview = call(
        plain, f"{EDA}/v1/admin/preview/customer_txn_stats?limit=3", headers=auth
    )
    assert status == 200 and preview["rows"], preview
    status, _ = call(
        plain, f"{EDA}/v1/admin/promote", {"views": ["customer_txn_stats"]}, headers=auth
    )
    assert status == 409, status
    print("ok  feature-server-eda: cache preview works, writes refused")

    # Console UI is served by the console itself.
    with urllib.request.urlopen(f"{CONSOLE}/features", timeout=10) as page:
        body = page.read().decode()
        assert '<div id="root">' in body, "console UI not built into the image"
        assert "frame-ancestors 'none'" in page.headers["Content-Security-Policy"]
    asset = body.split('src="')[1].split('"')[0]
    with urllib.request.urlopen(f"{CONSOLE}{asset}", timeout=10) as script:
        assert script.status == 200
    print("ok  console UI served", asset)

    # Console: local admin, then a pipeline run that coexists with the scheduler.
    admin, jar = browser()
    status, _ = call(
        admin, f"{CONSOLE}/auth/login", {"email": "admin@example.com", "password": "change-me"}
    )
    assert status == 200, status
    token = {"X-CSRF-Token": csrf(jar)}
    status, run = call(
        admin, f"{CONSOLE}/api/projects/quickstart/pipelines/hourly/runs", {}, headers=token
    )
    assert status == 202, run
    for _ in range(120):
        status, run = call(admin, f"{CONSOLE}/api/projects/quickstart/pipelines/runs/{run['id']}")
        if run["status"] != "running":
            break
        time.sleep(1)
    assert run["status"] == "succeeded", run
    assert "dbt | " in run["log"] and "Done. PASS=" in run["log"], "dbt output missing from run log"
    print("ok  console: pipeline run", run["id"], run["result"]["features"])

    # Grant the SSO group "analysts" read access, then sign in through the dev IdP.
    status, _ = call(
        admin,
        f"{CONSOLE}/api/admin/bindings",
        {
            "subject_type": "group",
            "subject": "analysts",
            "role": "viewer",
            "scope": "project:quickstart",
        },
        headers=token,
    )
    assert status in (201, 409), status

    sso, sso_jar = browser()
    with sso.open(
        f"{CONSOLE}/auth/oidc/dev/login?return_to=/features", timeout=30
    ) as page:  # follows to IdP form
        form = _Form()
        form.feed(page.read().decode())
        idp_url = page.url
    form.fields.update({"email": "ada@example.com", "name": "Ada", "groups": "analysts"})
    target = urllib.parse.urljoin(idp_url, form.action)
    with sso.open(
        urllib.request.Request(target, data=urllib.parse.urlencode(form.fields).encode()),
        timeout=30,
    ) as page:
        assert urllib.parse.urlparse(page.url).path == "/features", page.url  # back in the console
    status, me = call(sso, f"{CONSOLE}/api/me")
    assert status == 200 and me["email"] == "ada@example.com" and me["groups"] == ["analysts"], me
    assert "features.read" in me["permissions"]["quickstart"]
    status, _ = call(
        sso,
        f"{CONSOLE}/api/projects/quickstart/pipelines/hourly/runs",
        {},
        headers={"X-CSRF-Token": csrf(sso_jar)},
    )
    assert status == 403, status
    print("ok  SSO: ada@example.com via dev IdP, group 'analysts' -> viewer; run denied (403)")
    print("PoC smoke test passed")


if __name__ == "__main__":
    main()
