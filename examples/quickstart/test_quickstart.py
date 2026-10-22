"""Integration test: the quickstart repo works end to end on SQLite."""

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from seed import seed  # noqa: E402

from shalf.data import FeatureStore  # noqa: E402
from shalf.data.types import utcnow  # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SHALF_QUICKSTART_DB", str(seed(tmp_path / "source.db")))
    monkeypatch.setenv("SHALF_ONLINE_PATH", str(tmp_path / "online.db"))
    for name in ("features", "entities"):
        sys.modules.pop(name, None)  # re-import so DB_PATH picks up the env var
    monkeypatch.syspath_prepend(str(HERE / "feature_repo"))
    return FeatureStore.from_repo(HERE / "feature_repo")


def test_offline_and_online_agree(store):
    now = utcnow()
    spine = pd.DataFrame(
        {"customer_id": [1, 2, 3], "event_timestamp": [now] * 3, "amount": [10.0, 20.0, 30.0]}
    )
    offline = store.get_historical_features(spine, feature_service="fraud_model_v1")

    store.materialize(end=now + timedelta(seconds=1))
    online = store.get_online_features(
        {"customer_id": [1, 2, 3]},
        feature_service="fraud_model_v1",
        request_data={"amount": [10.0, 20.0, 30.0]},
    ).to_df()

    columns = [
        "txn_count_7d",
        "txn_amount_sum_7d",
        "risky_spend_ratio_7d",
        "amount_to_avg_ratio",
        "age",
    ]
    pd.testing.assert_frame_equal(
        offline[columns].reset_index(drop=True).astype(float),
        online[columns].astype(float),
        check_exact=False,
    )
    assert offline["txn_count_7d"].gt(0).all()
