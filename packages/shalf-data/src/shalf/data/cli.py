"""``shalf-data`` command line: the same operations the services and jobs run.

    shalf-data --repo examples/quickstart/feature_repo apply
    shalf-data --repo ... list views
    shalf-data --repo ... materialize --start 2024-01-01 --end 2024-02-01
    shalf-data --repo ... materialize-incremental
    shalf-data --repo ... online --features customer_txn_stats:txn_count_7d \\
        --entities '{"customer_id": [1, 2]}'
    shalf-data --repo ... historical --entity-csv spine.csv \\
        --feature-service fraud_model_v1 --out train.csv
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence

import pandas as pd

from shalf.core import configure_logging
from shalf.data.store import FeatureStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shalf-data", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo", default=os.getenv("SHALF_REPO_PATH", "."), help="feature repo dir"
    )
    parser.add_argument("--config", default=None, help="override path to shalf.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("apply", help="validate definitions and prepare the online store")

    ls = sub.add_parser("list", help="print definitions as JSON")
    ls.add_argument(
        "kind", choices=["entities", "views", "services", "all"], nargs="?", default="all"
    )

    mat = sub.add_parser("materialize", help="materialise a time window")
    mat.add_argument("--start", default=None)
    mat.add_argument("--end", default=None)
    mat.add_argument("--views", nargs="*", default=None)

    inc = sub.add_parser("materialize-incremental", help="materialise since the last watermark")
    inc.add_argument("--end", default=None)
    inc.add_argument("--views", nargs="*", default=None)

    for name, help_text in (
        ("online", "read online features"),
        ("historical", "build a training set"),
    ):
        p = sub.add_parser(name, help=help_text)
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument("--features", nargs="+")
        group.add_argument("--feature-service")
        p.add_argument("--full-feature-names", action="store_true")

    online = sub.choices["online"]
    online.add_argument("--entities", required=True, help='JSON, e.g. {"customer_id": [1, 2]}')
    online.add_argument("--request-data", default=None, help="JSON, same shape as --entities")

    hist = sub.choices["historical"]
    hist.add_argument("--entity-csv", required=True, help="entity keys + event_timestamp")
    hist.add_argument("--out", default="-", help="output CSV path, '-' for stdout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    args = _parser().parse_args(argv)
    store = FeatureStore.from_repo(args.repo, args.config)

    if args.command == "apply":
        print(
            f"Applied {len(store.list_feature_views())} feature views "
            f"to project {store.config.project!r}"
        )
    elif args.command == "list":
        data = store.registry.to_dict()
        key = {"entities": "entities", "views": "feature_views", "services": "feature_services"}
        print(
            json.dumps(data if args.kind == "all" else data[key[args.kind]], indent=2, default=str)
        )
    elif args.command == "materialize":
        print(json.dumps(store.materialize(args.start, args.end, args.views), indent=2))
    elif args.command == "materialize-incremental":
        print(json.dumps(store.materialize_incremental(args.end, args.views), indent=2))
    elif args.command == "online":
        response = store.get_online_features(
            json.loads(args.entities),
            args.features,
            feature_service=args.feature_service,
            request_data=json.loads(args.request_data) if args.request_data else None,
            full_feature_names=args.full_feature_names,
        )
        print(json.dumps(response.to_dict(), indent=2))
    elif args.command == "historical":
        entity_df = pd.read_csv(args.entity_csv)
        df = store.get_historical_features(
            entity_df,
            args.features,
            feature_service=args.feature_service,
            full_feature_names=args.full_feature_names,
        )
        df.to_csv(sys.stdout if args.out == "-" else args.out, index=False)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
