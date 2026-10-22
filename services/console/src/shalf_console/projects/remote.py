from __future__ import annotations

from typing import Any

import httpx

from shalf_console.projects.base import BackendError, ProjectBackend


class RemoteProject(ProjectBackend):
    """A project running in Kubernetes, reached through its feature servers.

    ``serving_url`` is the project's feature-server (registry, plan, promote,
    online lookups); ``eda_url`` its EDA feature server, which can read the
    offline cache for previews. Admin calls carry the project's admin token.
    """

    kind = "remote"

    def __init__(
        self,
        name: str,
        *,
        serving_url: str,
        eda_url: str | None = None,
        admin_token: str = "",
        http: httpx.Client | None = None,
        description: str = "",
    ) -> None:
        super().__init__(name, description)
        self.serving_url = serving_url.rstrip("/")
        self.eda_url = (eda_url or serving_url).rstrip("/")
        self.http = http or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

    def _call(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            response = self.http.request(method, url, headers=self.headers, **kwargs)
        except httpx.HTTPError as exc:
            raise BackendError(f"{self.name}: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            status = response.status_code if response.status_code in (400, 404, 409) else 502
            raise BackendError(f"{self.name}: {detail}", status)
        return response.json()

    def registry(self) -> dict[str, Any]:
        return self._call("GET", f"{self.serving_url}/v1/registry")

    def plan(self) -> list[dict[str, Any]]:
        return self._call("GET", f"{self.serving_url}/v1/admin/plan")

    def preview(self, view: str, limit: int) -> dict[str, Any]:
        return self._call("GET", f"{self.eda_url}/v1/admin/preview/{view}", params={"limit": limit})

    def promote(self, views: list[str] | None) -> dict[str, str]:
        return self._call("POST", f"{self.serving_url}/v1/admin/promote", json={"views": views})

    def online(self, entities, features, feature_service, request_data) -> dict[str, Any]:
        body = {
            "entities": entities,
            "features": features,
            "feature_service": feature_service,
            "request_data": request_data,
        }
        return self._call("POST", f"{self.serving_url}/v1/features/online", json=body)

    def pipelines(self) -> dict[str, Any]:
        return self._call("GET", f"{self.serving_url}/v1/admin/pipelines")

    def health(self) -> dict[str, Any]:
        try:
            ready = self._call("GET", f"{self.serving_url}/readyz")
        except BackendError as exc:
            return {"status": "error", "detail": str(exc)}
        return {**ready, "status": "ok"}
