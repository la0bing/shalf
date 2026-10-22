"""Browser end-to-end test of the console: SSO, custom roles and RBAC in the UI.

    (cd services/console/web && npm ci && npm run build)
    uv run --with playwright python services/console/e2e/run_e2e.py [--screenshots DIR]

Starts the dev OIDC provider and the console against the quickstart project,
then drives Chromium:

1. an admin signs in locally, runs a pipeline, previews features, creates a
   custom role and grants it to the SSO group "analysts" for one project;
2. an analyst signs in through SSO and sees exactly what the role allows -
   in the navigation, on pages, and in the API.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dev"))
sys.path.insert(0, str(ROOT / "examples" / "quickstart"))

from dev_idp import CLIENT_ID, CLIENT_SECRET, create_idp  # noqa: E402

from shalf.models import ModelArtifact  # noqa: E402
from shalf_console.app import create_app  # noqa: E402
from shalf_console.settings import ConsoleSettings, OIDCProvider, ProjectConfig  # noqa: E402

IDP, CONSOLE = "http://127.0.0.1:9555", "http://127.0.0.1:8095"
ADMIN, PASSWORD = "admin@example.com", "e2e-admin-password"


def serve(app, port: int) -> uvicorn.Server:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started:
        if not thread.is_alive() or time.time() > deadline:
            raise SystemExit(f"could not start a server on port {port} (in use? e.g. the compose PoC)")
        time.sleep(0.05)
    return server


def shot(page: Page, directory: Path | None, name: str) -> None:
    if directory:
        page.screenshot(path=str(directory / f"{name}.png"), full_page=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshots", type=Path, default=None)
    parser.add_argument("--color-scheme", default="light", choices=["light", "dark"])
    args = parser.parse_args()
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)

    import run as quickstart  # examples/quickstart/run.py: seed + dbt + features

    quickstart.main()

    tmp = Path(tempfile.mkdtemp(prefix="shalf-e2e-"))
    settings = ConsoleSettings(
        base_url=CONSOLE,
        database_url=f"sqlite:///{tmp / 'console.db'}",
        cookie_secure=False,
        bootstrap_admins=[ADMIN],
        bootstrap_admin_password=PASSWORD,
        oidc=[
            OIDCProvider(
                id="dev",
                name="Corp SSO",
                issuer=IDP,
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
            )
        ],
        projects=[
            ProjectConfig(
                name="quickstart",
                path=str(ROOT / "examples" / "quickstart"),
                description="Fraud features on the example app database",
            )
        ],
        model_registry={"type": "local", "root": str(tmp / "models")},
    )
    app = create_app(settings)
    registry = app.state.console.model_registry
    registry.register(
        ModelArtifact(
            "fraud-detector",
            "7",
            "s3://models/fraud/7",
            "fraud_model_v1",
            metrics={"auc": 0.912, "recall@1%": 0.64},
            stage="production",
        )
    )
    registry.register(
        ModelArtifact(
            "fraud-detector",
            "8",
            "s3://models/fraud/8",
            "fraud_model_v1",
            metrics={"auc": 0.927, "recall@1%": 0.69},
        )
    )
    serve(create_idp(IDP), 9555)
    serve(app, 8095)

    launch = (
        {"executable_path": "/opt/pw-browsers/chromium"}
        if os.path.exists("/opt/pw-browsers/chromium")
        else {}
    )
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch)
        size = {"width": 1440, "height": 900}

        # ---- admin -------------------------------------------------------------
        admin = browser.new_context(viewport=size, color_scheme=args.color_scheme).new_page()
        admin.goto(f"{CONSOLE}/features")
        expect(admin).to_have_url(f"{CONSOLE}/login?return_to=%2Ffeatures")
        shot(admin, args.screenshots, "01-login")
        admin.get_by_label("Email").fill(ADMIN)
        admin.get_by_label("Password").fill(PASSWORD)
        admin.get_by_role("button", name="Sign in").click()
        expect(admin.get_by_role("heading", name="Features")).to_be_visible()
        expect(admin.get_by_text("customer_txn_stats").first).to_be_visible()
        shot(admin, args.screenshots, "03-features")

        admin.get_by_role("link", name="Overview").click()
        expect(admin.get_by_text("Your projects")).to_be_visible()
        shot(admin, args.screenshots, "02-overview")

        admin.goto(f"{CONSOLE}/features/customer_txn_stats")
        expect(admin.get_by_text("Lineage")).to_be_visible()
        admin.get_by_role("button", name="Preview rows").click()
        expect(admin.locator("table").get_by_text("txn_count_7d")).to_be_visible()
        shot(admin, args.screenshots, "04-feature-detail")

        admin.get_by_role("link", name="Pipelines").click()
        admin.get_by_role("row", name="hourly").get_by_role("button", name="Run now").click()
        dialog = admin.locator("dialog[open]")
        expect(dialog.get_by_text("succeeded")).to_be_visible(timeout=60_000)
        shot(admin, args.screenshots, "05-pipeline-run")
        dialog.get_by_role("button", name="Close").click()

        admin.get_by_role("link", name="Models").click()
        expect(admin.get_by_text("s3://models/fraud/8")).to_be_visible()
        shot(admin, args.screenshots, "06-models")

        # Custom role: read + preview features, nothing else.
        admin.get_by_role("link", name="Roles").click()
        admin.get_by_role("button", name="New role").click()
        editor = admin.locator("dialog[open]")
        editor.get_by_label("Name").fill("feature-explorer")
        editor.get_by_label("Description").fill("Browse and preview features")
        editor.get_by_role("checkbox", name="features.read").check()
        editor.get_by_role("checkbox", name="features.preview").check()
        editor.get_by_role("checkbox", name="serving.read").check()
        shot(admin, args.screenshots, "07-role-editor")
        editor.get_by_role("button", name="Create role").click()
        expect(
            admin.get_by_role("cell", name="feature-explorer", exact=False).first
        ).to_be_visible()

        # Grant it to the SSO group, in one project.
        admin.get_by_role("link", name="Access").click()
        admin.get_by_role("button", name="Grant access").click()
        grant = admin.locator("dialog[open]")
        grant.get_by_label("Group name").fill("analysts")
        grant.get_by_label("Role").select_option("feature-explorer")
        grant.get_by_label("Scope").select_option("project:quickstart")
        grant.get_by_role("button", name="Grant", exact=True).click()
        expect(admin.get_by_role("cell", name="Group analysts")).to_be_visible()
        shot(admin, args.screenshots, "08-access")

        # ---- analyst via SSO ------------------------------------------------------
        analyst = browser.new_context(viewport=size, color_scheme=args.color_scheme).new_page()
        analyst.goto(f"{CONSOLE}/login")
        analyst.get_by_role("link", name="Continue with Corp SSO").click()
        expect(analyst).to_have_url(re.compile(re.escape(f"{IDP}/authorize")))
        analyst.get_by_label("Email").fill("ada@example.com")
        analyst.get_by_label("Groups (comma separated)").fill("analysts")
        analyst.get_by_role("button", name="Sign in").click()
        expect(analyst.get_by_text("Welcome, Ada")).to_be_visible()
        nav = analyst.get_by_role("navigation", name="Main")
        expect(nav.get_by_role("link", name="Features")).to_be_visible()
        expect(nav.get_by_role("link", name="Serving")).to_be_visible()
        expect(nav.get_by_role("link", name="Pipelines")).to_have_count(0)
        expect(nav.get_by_text("Administration")).to_have_count(0)
        shot(analyst, args.screenshots, "09-analyst-overview")

        analyst.goto(f"{CONSOLE}/pipelines")
        expect(analyst.get_by_role("heading", name="Access denied")).to_be_visible()
        expect(analyst.get_by_text("pipelines.read")).to_be_visible()
        shot(analyst, args.screenshots, "10-analyst-denied")

        analyst.goto(f"{CONSOLE}/features")
        expect(analyst.get_by_role("button", name="Promote", exact=False)).to_have_count(0)
        status = analyst.evaluate(
            """async () => {
                const csrf = document.cookie.split('; ').find(c => c.startsWith('shalf_csrf=')).split('=')[1];
                const r = await fetch('/api/projects/quickstart/pipelines/hourly/runs', {
                  method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: '{}'});
                return r.status;
            }"""
        )
        assert status == 403, status

        # ---- audit trail ---------------------------------------------------------------
        admin.get_by_role("link", name="Audit log").click()
        expect(admin.get_by_role("cell", name="binding.create")).to_be_visible()
        expect(admin.get_by_role("cell", name="ada@example.com").first).to_be_visible()
        shot(admin, args.screenshots, "11-audit")
        browser.close()
    print("e2e: all checks passed")


if __name__ == "__main__":
    main()
