"""End-to-end walk-through: app DB -> dbt -> features -> training set -> online.

uv run python examples/quickstart/run.py
"""

from __future__ import annotations

import shutil
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from seed import seed  # noqa: E402

from shalf.data import FeatureStore  # noqa: E402
from shalf.data.types import utcnow  # noqa: E402
from shalf.pipelines import run_pipeline  # noqa: E402


def main() -> None:
    shutil.rmtree(HERE / "data", ignore_errors=True)  # fresh demo
    seed()
    store = FeatureStore.from_repo(HERE)

    # 1. What the CronJobs run: dbt build, then materialise the affected views.
    for pipeline in ("daily", "hourly"):
        outputs = run_pipeline(store, str(HERE), pipeline)
        print(
            f"{pipeline}: dbt built {outputs['transform'].models}, features {outputs['features']}"
        )

    # 2. Offline: point-in-time correct training data (served from the cache).
    now = utcnow().floor("h")
    spine = pd.DataFrame(
        {
            "customer_id": [1, 2, 3, 1],
            "event_timestamp": [now - timedelta(days=d) for d in (1, 2, 3, 10)],
            "amount": [120.0, 15.5, 60.0, 300.0],  # request-time data for on-demand features
            "label": [0, 0, 1, 1],
        }
    )
    training = store.get_historical_features(spine, feature_service="fraud_model_v1")
    print("\nTraining frame:\n", training.to_string())

    # 3. Online: what the model server does per request.
    response = store.get_online_features(
        {"customer_id": [1, 2]},
        feature_service="fraud_model_v1",
        request_data={"amount": [120.0, 15.5]},
    )
    print("\nOnline features:\n", response.to_df().to_string())


if __name__ == "__main__":
    main()
