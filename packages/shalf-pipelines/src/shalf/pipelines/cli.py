"""``shalf-pipelines``: what the scheduled jobs run.

shalf-pipelines --repo PROJECT list
shalf-pipelines --repo PROJECT run hourly
shalf-pipelines --repo PROJECT run hourly --start 2024-01-01 --end 2024-02-01 [--promote]
shalf-pipelines --repo PROJECT dbt parse          # any dbt command, project settings applied
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from shalf.core import configure_logging
from shalf.data import FeatureStore, FeatureStoreConfig
from shalf.data.types import parse_duration
from shalf.pipelines.project import PipelineError, TransformConfig, run_pipeline
from shalf.pipelines.schedule import run_schedule


def load_project_config(repo: str, profile: str | None) -> FeatureStoreConfig:
    config_file = os.environ.get("SHALF_CONFIG") or os.path.join(repo, "shalf.yaml")
    profile = profile or os.environ.get("SHALF_PROFILE") or None
    return FeatureStoreConfig.load(config_file, profile).resolve_paths(Path(repo))


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(prog="shalf-pipelines", description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=os.getenv("SHALF_REPO_PATH", "."), help="project dir")
    parser.add_argument("--profile", default=None, help="config profile (default $SHALF_PROFILE)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list configured pipelines")
    run = sub.add_parser("run", help="run a pipeline (a backfill when --start/--end are given)")
    run.add_argument("name")
    run.add_argument("--start", default=None)
    run.add_argument("--end", default=None)
    run.add_argument("--promote", action="store_true", help="backfills: switch readers at the end")
    schedule = sub.add_parser("schedule", help="run pipelines periodically (no Kubernetes needed)")
    schedule.add_argument(
        "--every",
        action="append",
        default=[],
        metavar="PIPELINE=DURATION",
        help="override/extend `every:` from shalf.yaml, e.g. hourly=15m (repeatable, ordered)",
    )
    dbt = sub.add_parser("dbt", help="run a dbt command with the project's settings")
    dbt.add_argument("dbt_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    repo = os.path.abspath(args.repo)
    if args.command in ("list", "dbt"):
        # Config only: no stores are created (e.g. `dbt parse` during image builds).
        config = load_project_config(repo, args.profile)
        if args.command == "list":
            print(json.dumps(config.pipelines, indent=2))
            return 0
        project = TransformConfig.model_validate(config.transform).dbt(repo)
        result = project.invoke(args.dbt_args or ["--help"])
        return 0 if result.success else 1

    store = FeatureStore.from_repo(repo, profile=args.profile)
    if args.command == "schedule":
        intervals = {
            name: spec.get("every")
            for name, spec in store.config.pipelines.items()
            if spec and spec.get("every")
        }
        for item in args.every:
            name, _, duration = item.partition("=")
            intervals[name] = duration
        run_schedule(store, repo, [(n, parse_duration(d)) for n, d in intervals.items()])
        return 0
    if args.command == "run":
        try:
            outputs = run_pipeline(
                store, repo, args.name, start=args.start, end=args.end, promote=args.promote
            )
        except PipelineError as exc:
            print(f"pipeline {args.name!r} failed: {exc}", file=sys.stderr)
            return 1
        transform = outputs["transform"]
        summary = {
            "dbt_models": transform.models if transform else [],
            "features": outputs["features"],
        }
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
