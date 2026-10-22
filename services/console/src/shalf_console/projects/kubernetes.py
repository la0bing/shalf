"""Pipeline runs as Kubernetes Jobs, created from the project's CronJobs.

The console needs a Role in the project namespace allowing: get/list
cronjobs, create/get/list jobs, list pods, get pods/log (see
deploy/k8s/console/).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx

from shalf_console.projects.base import BackendError, PipelineRunner

_SA = Path("/var/run/secrets/kubernetes.io/serviceaccount")
_COMPONENT = "app.kubernetes.io/component=pipeline"


class KubernetesPipelineRunner(PipelineRunner):
    kind = "kubernetes"

    def __init__(
        self,
        *,
        namespace: str,
        api_url: str = "https://kubernetes.default.svc",
        token_path: str = str(_SA / "token"),
        ca_path: str = str(_SA / "ca.crt"),
        http: httpx.Client | None = None,
    ) -> None:
        self.namespace = namespace
        self.api_url = api_url.rstrip("/")
        self.token_path = token_path
        verify: Any = ca_path if Path(ca_path).exists() else True
        self.http = http or httpx.Client(verify=verify, timeout=30)

    # -- API plumbing ------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        token = Path(self.token_path).read_text().strip() if Path(self.token_path).exists() else ""
        return {"Authorization": f"Bearer {token}"} if token else {}  # re-read: tokens rotate

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self.http.request(
                method, self.api_url + path, headers=self._headers(), **kwargs
            )
        except httpx.HTTPError as exc:
            raise BackendError(f"Kubernetes API: {exc}") from exc
        if response.status_code == 404:
            raise BackendError("Not found", 404)
        if response.status_code >= 400:
            raise BackendError(f"Kubernetes API {response.status_code}: {response.text[:300]}")
        return response

    def _batch(self, kind: str, name: str = "") -> str:
        return f"/apis/batch/v1/namespaces/{self.namespace}/{kind}" + (f"/{name}" if name else "")

    # -- runner ------------------------------------------------------------------
    def schedules(self) -> dict[str, str]:
        items = self._request("GET", self._batch("cronjobs"), params={"labelSelector": _COMPONENT})
        return {
            item["metadata"]["name"].removeprefix("pipeline-"): item["spec"]["schedule"]
            for item in items.json().get("items", [])
        }

    def start(self, pipeline, *, start, end, promote, actor) -> dict[str, Any]:
        cronjob = self._request("GET", self._batch("cronjobs", f"pipeline-{pipeline}")).json()
        job_spec = copy.deepcopy(cronjob["spec"]["jobTemplate"]["spec"])
        container = job_spec["template"]["spec"]["containers"][0]
        extra = []
        if start:
            extra += ["--start", start]
        if end:
            extra += ["--end", end]
        if promote:
            extra.append("--promote")
        container["command"] = [*container.get("command", []), *extra]
        labels = {
            **(cronjob["spec"]["jobTemplate"].get("metadata", {}).get("labels") or {}),
            "app.kubernetes.io/component": "pipeline",
            "shalf.io/pipeline": pipeline,
            "shalf.io/trigger": "console",
        }
        job = {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "generateName": f"pipeline-{pipeline}-manual-",
                "labels": labels,
                "annotations": {
                    "shalf.io/triggered-by": actor,
                    "shalf.io/args": json.dumps({"start": start, "end": end, "promote": promote}),
                },
            },
            "spec": job_spec,
        }
        created = self._request("POST", self._batch("jobs"), json=job).json()
        return _job_dict(created)

    def runs(self, limit: int = 50) -> list[dict[str, Any]]:
        items = self._request("GET", self._batch("jobs"), params={"labelSelector": _COMPONENT})
        runs = [_job_dict(item) for item in items.json().get("items", [])]
        return sorted(runs, key=lambda r: r["started_at"] or "", reverse=True)[:limit]

    def get(self, run_id: str) -> dict[str, Any]:
        job = _job_dict(self._request("GET", self._batch("jobs", run_id)).json())
        pods = self._request(
            "GET",
            f"/api/v1/namespaces/{self.namespace}/pods",
            params={"labelSelector": f"job-name={run_id}"},
        ).json()
        log = ""
        for pod in pods.get("items", [])[-1:]:
            log = self._request(
                "GET",
                f"/api/v1/namespaces/{self.namespace}/pods/{pod['metadata']['name']}/log",
                params={"tailLines": 1000},
            ).text
        return {**job, "log": log}


def _job_dict(job: dict[str, Any]) -> dict[str, Any]:
    meta, status = job.get("metadata", {}), job.get("status", {})
    labels, annotations = meta.get("labels") or {}, meta.get("annotations") or {}
    pipeline = labels.get("shalf.io/pipeline")
    if not pipeline:
        owners = meta.get("ownerReferences") or [{}]
        pipeline = owners[0].get("name", "").removeprefix("pipeline-")
    if status.get("succeeded"):
        state = "succeeded"
    elif status.get("failed") and not status.get("active"):
        state = "failed"
    else:
        state = "running"
    return {
        "id": meta.get("name"),
        "pipeline": pipeline,
        "status": state,
        "args": json.loads(annotations.get("shalf.io/args", "{}")),
        "triggered_by": annotations.get("shalf.io/triggered-by", "schedule"),
        "started_at": status.get("startTime") or meta.get("creationTimestamp"),
        "finished_at": status.get("completionTime"),
        "result": {},
    }
