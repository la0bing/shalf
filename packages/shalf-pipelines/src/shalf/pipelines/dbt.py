"""Run dbt (dbt-core >= 1.5) for a project.

No dbt Cloud, no extra service. With the dbt-duckdb adapter the computation
runs in DuckDB, reading the source databases through DuckDB's ``ATTACH``
(read-only) and writing models as Parquet files to the project's warehouse
path.

Every dbt command runs in a **child process**. dbt's in-process runner is not
safe for concurrent use, and dbt-duckdb keeps its database file open (and
locked) for the life of the process, which would block every other process,
e.g. a console-triggered run while the scheduler idles. A child process
releases everything when it exits. Results come from ``run_results.json``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shalf.core import ShalfError, get_logger

log = get_logger(__name__)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_DBT = "import sys; from dbt.cli.main import cli; sys.exit(cli())"


@dataclass
class DbtResult:
    success: bool
    models: list[str]  # models built successfully
    failures: list[str]  # nodes (models or tests) that failed or errored


@dataclass
class DbtInvocation:
    success: bool
    returncode: int
    output: list[str]


class DbtProject:
    def __init__(
        self,
        *,
        project_dir: str,
        profiles_dir: str,
        target: str | None,
        target_path: str,
        env: Mapping[str, str],
    ) -> None:
        self.project_dir = project_dir
        self.profiles_dir = profiles_dir
        self.target = target
        self.target_path = target_path
        self.env = dict(env)

    def invoke(
        self, args: Sequence[str], on_log: Callable[[str], None] | None = None
    ) -> DbtInvocation:
        """Run ``dbt <args>`` with the project's settings in a child process.

        Output lines go to ``on_log`` if given, otherwise to this process's
        stdout (so CronJob logs show them).
        """
        env = {
            **os.environ,
            **self.env,  # profiles.yml reads these through env_var()
            # No telemetry, and no ~/.dbt or .user.yml writes (read-only filesystems).
            "DBT_SEND_ANONYMOUS_USAGE_STATS": os.environ.get(
                "DBT_SEND_ANONYMOUS_USAGE_STATS", "false"
            ),
        }
        common = [
            "--project-dir", self.project_dir,
            "--profiles-dir", self.profiles_dir,
            "--target-path", self.target_path,
            "--log-path", os.path.join(self.target_path, "logs"),
        ]  # fmt: skip
        if self.target:
            common += ["--target", self.target]
        log.info("dbt %s", " ".join(args))
        # Options after the (possibly multi-word, e.g. `docs generate`) command.
        command = [sys.executable, "-c", _DBT, *args, *common]
        output: list[str] = []
        try:
            process = subprocess.Popen(
                command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:  # pragma: no cover
            raise ShalfError(f"Could not start dbt: {exc}") from exc
        assert process.stdout is not None
        for raw in process.stdout:
            line = _ANSI.sub("", raw.rstrip("\n"))
            output.append(line)
            if on_log is not None:
                on_log(f"dbt | {line}")
            else:
                print(line, flush=True)
        returncode = process.wait()
        if returncode != 0 and any("No module named 'dbt'" in line for line in output):
            raise ShalfError("dbt is not installed: `pip install shalf-pipelines[dbt]`")
        return DbtInvocation(returncode == 0, returncode, output)

    def build(
        self,
        select: str | None,
        variables: Mapping[str, Any] | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> DbtResult:
        if "SHALF_WAREHOUSE_PATH" in self.env:  # dbt-duckdb creates files, not directories
            os.makedirs(self.env["SHALF_WAREHOUSE_PATH"], exist_ok=True)
        results_file = Path(self.target_path) / "run_results.json"
        results_file.unlink(missing_ok=True)  # never read a previous run's results
        args = ["build"]
        if select:
            args += ["--select", select]
        if variables:
            args += ["--vars", json.dumps(dict(variables))]
        invocation = self.invoke(args, on_log)

        models, failures = [], []
        if results_file.exists():
            for node in json.loads(results_file.read_text()).get("results", []):
                uid, status = node.get("unique_id", ""), node.get("status")
                if status in ("error", "fail"):
                    failures.append(uid)
                elif uid.startswith("model.") and status == "success":
                    models.append(uid.split(".")[-1])
        if not invocation.success and not failures:
            errors = [line for line in invocation.output if "Error" in line][-3:]
            failures.append(f"dbt exited with code {invocation.returncode}: {' / '.join(errors)}")
        return DbtResult(invocation.success and not failures, models, failures)

    def parse(self) -> None:
        invocation = self.invoke(["parse"])
        if not invocation.success:
            tail = "\n".join(invocation.output[-10:])
            raise ShalfError(f"dbt parse failed:\n{tail}")
