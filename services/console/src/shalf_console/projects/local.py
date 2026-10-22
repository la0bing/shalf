from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from shalf.data import FeatureStore
from shalf.data.types import to_python, utcnow
from shalf.pipelines import run_pipeline
from shalf_console.db import PipelineRun
from shalf_console.projects.base import BackendError, PipelineRunner, ProjectBackend


class LocalProject(ProjectBackend):
    """A project loaded in-process from a directory.

    Used for local development, and in Kubernetes when the console image is
    built FROM a project's jobs image.
    """

    kind = "local"

    def __init__(self, name: str, path: str, *, profile: str | None = None, description: str = ""):
        super().__init__(name, description)
        self.path = path
        self.profile = profile
        self._store: FeatureStore | None = None
        self._lock = threading.Lock()

    @property
    def store(self) -> FeatureStore:
        with self._lock:
            if self._store is None:
                self._store = FeatureStore.from_repo(self.path, profile=self.profile)
            return self._store

    def registry(self) -> dict[str, Any]:
        return self.store.registry.to_dict()

    def plan(self) -> list[dict[str, Any]]:
        return self.store.plan()

    def preview(self, view: str, limit: int) -> dict[str, Any]:
        try:
            df = self.store.preview(view, limit=limit)
        except KeyError as exc:
            raise BackendError(str(exc), 404) from exc
        except Exception as exc:  # e.g. CacheMissError, dbt model not built
            raise BackendError(str(exc), 409) from exc
        return {
            "columns": list(df.columns),
            "rows": [[to_python(v) for v in row] for row in df.itertuples(index=False)],
        }

    def promote(self, views: list[str] | None) -> dict[str, str]:
        try:
            return self.store.promote(views)
        except Exception as exc:
            raise BackendError(str(exc), 409) from exc

    def online(self, entities, features, feature_service, request_data) -> dict[str, Any]:
        try:
            response = self.store.get_online_features(
                entities, features, feature_service=feature_service, request_data=request_data
            )
        except (KeyError, ValueError) as exc:
            raise BackendError(str(exc), 400) from exc
        except Exception as exc:
            raise BackendError(str(exc), 400) from exc
        return {"feature_names": response.feature_names, "results": response.to_dict()}

    def pipelines(self) -> dict[str, Any]:
        return dict(self.store.config.pipelines)

    def health(self) -> dict[str, Any]:
        try:
            self.store.online_store.ping()
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
        return {"status": "ok", "online_store": type(self.store.online_store).__name__}


class _RunLog(logging.Handler):
    """Collects one run's log: shalf log records from the run's thread, plus
    dbt's events (forwarded through dbt's callback API)."""

    def __init__(self, thread_id: int) -> None:
        super().__init__(logging.INFO)
        self.thread_id = thread_id
        self.lines: list[str] = []
        self._lock = threading.Lock()
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread == self.thread_id:
            self.add(self.format(record))

    def add(self, line: str) -> None:
        with self._lock:
            self.lines.append(line)


class ThreadPipelineRunner(PipelineRunner):
    """Runs pipelines of a :class:`LocalProject` in a background thread.

    Suitable for development and small single-replica installs; in
    Kubernetes use :class:`KubernetesPipelineRunner` so runs get their own pods.
    """

    kind = "thread"

    def __init__(self, project: LocalProject, sessions: sessionmaker) -> None:
        self.project = project
        self.sessions = sessions

    def start(self, pipeline, *, start, end, promote, actor) -> dict[str, Any]:
        if pipeline not in self.project.pipelines():
            raise BackendError(f"Unknown pipeline {pipeline!r}", 404)
        with self.sessions() as db:
            running = db.scalars(
                select(PipelineRun).where(
                    PipelineRun.project == self.project.name, PipelineRun.status == "running"
                )
            ).first()
            if running is not None:
                raise BackendError(f"Run {running.id} is still running for this project", 409)
            run = PipelineRun(
                id=uuid.uuid4().hex[:12],
                project=self.project.name,
                pipeline=pipeline,
                status="running",
                args={"start": start, "end": end, "promote": promote},
                triggered_by=actor,
            )
            db.add(run)
            db.commit()
            run_id = run.id

        thread = threading.Thread(
            target=self._run, args=(run_id, pipeline, start, end, promote), daemon=True
        )
        thread.start()
        return self.get(run_id)

    def _run(self, run_id, pipeline, start, end, promote) -> None:
        handler = _RunLog(threading.get_ident())
        shalf_logger = logging.getLogger("shalf")
        previous_level = shalf_logger.level
        shalf_logger.addHandler(handler)
        if shalf_logger.getEffectiveLevel() > logging.INFO:
            shalf_logger.setLevel(logging.INFO)
        status, result = "succeeded", {}
        try:
            outputs = run_pipeline(
                self.project.store,
                self.project.path,
                pipeline,
                start=start,
                end=end,
                promote=promote,
                on_log=handler.add,
            )
            transform = outputs.get("transform")
            result = {
                "dbt_models": transform.models if transform else [],
                "features": outputs.get("features", {}),
            }
        except Exception as exc:
            status, result = "failed", {"error": str(exc)}
            handler.add(f"ERROR {exc}")
        finally:
            shalf_logger.removeHandler(handler)
            shalf_logger.setLevel(previous_level)
            with self.sessions() as db:
                run = db.get(PipelineRun, run_id)
                run.status, run.result = status, result
                run.finished_at = utcnow().to_pydatetime()
                run.log = "\n".join(handler.lines)
                db.commit()

    def runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.sessions() as db:
            rows = db.scalars(
                select(PipelineRun)
                .where(PipelineRun.project == self.project.name)
                .order_by(PipelineRun.started_at.desc())
                .limit(limit)
            ).all()
            return [_run_dict(r) for r in rows]

    def get(self, run_id: str) -> dict[str, Any]:
        with self.sessions() as db:
            run = db.get(PipelineRun, run_id)
            if run is None or run.project != self.project.name:
                raise BackendError(f"Unknown run {run_id!r}", 404)
            return {**_run_dict(run), "log": run.log}


def _run_dict(run: PipelineRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "pipeline": run.pipeline,
        "status": run.status,
        "args": run.args,
        "triggered_by": run.triggered_by,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "result": run.result,
    }
