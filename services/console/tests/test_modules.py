"""Module APIs over a real (local) project, and what each role may do."""

import json
import time

import httpx
from fastapi.testclient import TestClient

from feature_server.app import create_app as feature_server_app
from shalf.data import FeatureStore
from shalf.models import ModelArtifact
from shalf_console.projects import KubernetesPipelineRunner, RemoteProject


def wait_for(admin, run_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = admin.get(f"/api/projects/demo/pipelines/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.2)
    raise AssertionError("pipeline run did not finish")


def test_modules_and_projects_follow_permissions(admin, make_user, other, login):
    modules = {m["key"]: m for m in admin.get("/api/modules").json()}
    assert modules["features"]["status"] == "ready" and modules["training"]["status"] == "planned"
    assert all(m["accessible"] for m in modules.values())

    make_user("ds@example.com", "data-scientist", "project:demo")
    login(other, "ds@example.com", "a-long-password-1")
    visible = {m["key"]: m["accessible"] for m in other.get("/api/modules").json()}
    assert (
        visible["features"]
        and visible["serving"]
        and not visible["admin"]
        and not visible["models"]
    )
    projects = other.get("/api/projects").json()
    assert [p["name"] for p in projects] == ["demo"] and "features.promote" not in projects[0][
        "permissions"
    ]


def test_features_pipelines_and_serving(admin):
    views = admin.get("/api/projects/demo/features/views").json()
    assert views[0]["name"] == "scores" and views[0]["rollout"]["status"] == "new"
    assert admin.get("/api/projects/demo/features/views/nope").status_code == 404
    assert admin.get("/api/projects/ghost/features/views").status_code == 404

    pipelines = admin.get("/api/projects/demo/pipelines").json()
    assert pipelines == [{"name": "refresh", "schedule": None, "views": "all"}]
    run = admin.post("/api/projects/demo/pipelines/refresh/runs", json={}).json()
    finished = wait_for(admin, run["id"])
    assert finished["status"] == "succeeded", finished
    assert finished["result"]["features"] == {"scores": 2}
    assert finished["triggered_by"] == "admin@example.com"

    preview = admin.get("/api/projects/demo/features/views/scores/preview?limit=5").json()
    assert preview["columns"] == ["customer_id", "event_timestamp", "score"]
    status = admin.get("/api/projects/demo/serving/status").json()
    assert status["health"]["status"] == "ok" and status["views"][0]["status"] == "unchanged"
    online = admin.post(
        "/api/projects/demo/serving/online",
        json={"entities": {"customer_id": [1, 3]}, "feature_service": "demo"},
    ).json()
    assert online["results"]["score"] == [0.5, None]
    assert admin.post("/api/projects/demo/serving/online", json={"entities": {}}).status_code == 422


def test_backfill_and_promote_need_extra_permissions(admin, make_user, other, login):
    admin.post("/api/admin/roles", json={"name": "runner", "permissions": ["pipelines.*"]})
    make_user("op@example.com", "runner", "project:demo")
    login(other, "op@example.com", "a-long-password-1")
    assert (
        other.post(
            "/api/projects/demo/pipelines/refresh/runs", json={"start": "2024-01-01"}
        ).status_code
        == 403
    )
    assert (
        other.post("/api/projects/demo/pipelines/refresh/runs", json={"promote": True}).status_code
        == 403
    )
    run = other.post("/api/projects/demo/pipelines/refresh/runs", json={}).json()
    assert wait_for(admin, run["id"])["status"] == "succeeded"
    assert "pipelines.run" in [e["action"] for e in admin.get("/api/admin/audit").json()]


def test_models_module(admin, app, make_user, other, login):
    registry = app.state.console.model_registry
    registry.register(
        ModelArtifact("fraud", "3", "s3://m/3", feature_service="demo", metrics={"auc": 0.91})
    )
    assert admin.get("/api/models").json()[0]["metrics"] == {"auc": 0.91}
    promoted = admin.post(
        "/api/models/fraud/versions/3/promote", json={"stage": "production"}
    ).json()
    assert promoted["stage"] == "production"
    assert (
        admin.post("/api/models/fraud/versions/9/promote", json={"stage": "production"}).status_code
        == 404
    )

    make_user("v@example.com", "viewer")
    login(other, "v@example.com", "a-long-password-1")
    assert other.get("/api/models").status_code == 200
    assert (
        other.post("/api/models/fraud/versions/3/promote", json={"stage": "archived"}).status_code
        == 403
    )


def test_remote_project_through_feature_server_admin_api(project_dir):
    store = FeatureStore.from_repo(project_dir)
    store.materialize()
    server = TestClient(feature_server_app(store, admin_token="tok"), base_url="http://fs")
    with server:
        remote = RemoteProject("demo", serving_url="http://fs", admin_token="tok", http=server)
        assert remote.registry()["feature_views"][0]["name"] == "scores"
        assert remote.plan()[0]["status"] == "unchanged"
        assert remote.preview("scores", 5)["columns"][-1] == "score"
        assert remote.pipelines() == {"refresh": {"views": "all"}}
        assert remote.online({"customer_id": [2]}, None, "demo", None)["results"]["score"] == [0.9]
        assert remote.health()["status"] == "ok"
        unauthorised = RemoteProject(
            "demo", serving_url="http://fs", admin_token="wrong", http=server
        )
        try:
            unauthorised.plan()
            raise AssertionError("expected failure")
        except Exception as exc:
            assert "Invalid admin token" in str(exc)


def test_kubernetes_runner_creates_jobs_from_cronjobs(tmp_path):
    token = tmp_path / "token"
    token.write_text("sa-token")
    cronjob = {
        "metadata": {"name": "pipeline-hourly"},
        "spec": {
            "schedule": "7 * * * *",
            "jobTemplate": {
                "metadata": {"labels": {"app.kubernetes.io/component": "pipeline"}},
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "pipeline",
                                    "command": ["shalf-pipelines", "run", "hourly"],
                                }
                            ]
                        }
                    }
                },
            },
        },
    }
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["authorization"] == "Bearer sa-token"
        path = request.url.path
        if path.endswith("/cronjobs"):
            return httpx.Response(200, json={"items": [cronjob]})
        if path.endswith("/cronjobs/pipeline-hourly"):
            return httpx.Response(200, json=cronjob)
        if path.endswith("/jobs") and request.method == "POST":
            body = json.loads(request.content)
            body["metadata"]["name"] = "pipeline-hourly-manual-abc"
            body["status"] = {"active": 1, "startTime": "2026-01-01T00:00:00Z"}
            return httpx.Response(201, json=body)
        if path.endswith("/jobs/pipeline-hourly-manual-abc"):
            return httpx.Response(
                200,
                json={
                    "metadata": {
                        "name": "pipeline-hourly-manual-abc",
                        "labels": {"shalf.io/pipeline": "hourly"},
                    },
                    "status": {"succeeded": 1},
                },
            )
        if path.endswith("/pods"):
            return httpx.Response(200, json={"items": [{"metadata": {"name": "pod-1"}}]})
        if path.endswith("/pods/pod-1/log"):
            return httpx.Response(200, text="dbt build ... OK")
        return httpx.Response(404)

    runner = KubernetesPipelineRunner(
        namespace="fraud",
        api_url="https://k8s",
        token_path=str(token),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert runner.schedules() == {"hourly": "7 * * * *"}
    run = runner.start("hourly", start="2024-01-01", end=None, promote=True, actor="ana@x.com")
    assert run["status"] == "running" and run["triggered_by"] == "ana@x.com"
    created = json.loads(next(r for r in seen if r.method == "POST").content)
    command = created["spec"]["template"]["spec"]["containers"][0]["command"]
    assert command == ["shalf-pipelines", "run", "hourly", "--start", "2024-01-01", "--promote"]
    assert created["metadata"]["labels"]["shalf.io/pipeline"] == "hourly"
    detail = runner.get("pipeline-hourly-manual-abc")
    assert detail["status"] == "succeeded" and detail["log"] == "dbt build ... OK"
