"""Integration test: the quickstart project end to end (SQLite -> dbt -> features)."""

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from seed import seed  # noqa: E402

from shalf.data import FeatureStore  # noqa: E402
from shalf.data.types import utcnow  # noqa: E402
from shalf.pipelines import PipelineError, TransformConfig, run_pipeline  # noqa: E402


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("SHALF_SOURCE_SQLITE", str(seed(tmp_path / "source.db")))
    for var, sub in (
        ("SHALF_WAREHOUSE_PATH", "warehouse"),
        ("SHALF_OFFLINE_CACHE", "cache"),
        ("SHALF_DBT_TARGET_PATH", "dbt-target"),
    ):
        monkeypatch.setenv(var, str(tmp_path / sub))
    monkeypatch.setenv("SHALF_DBT_MANIFEST", str(tmp_path / "dbt-target" / "manifest.json"))
    monkeypatch.setenv("SHALF_ONLINE_PATH", str(tmp_path / "online.db"))
    for name in [m for m in sys.modules if m == "features" or m.startswith("features.")]:
        monkeypatch.delitem(sys.modules, name)
    return tmp_path


def test_pipelines_then_offline_and_online_agree(project):
    store = FeatureStore.from_repo(HERE)
    daily = run_pipeline(store, str(HERE), "daily")
    assert sorted(daily["transform"].models) == [
        "dim_customers", "dim_merchants", "stg_customers", "stg_merchants"
    ]  # fmt: skip
    assert set(daily["features"]) == {"customer_profile", "merchant_profile"}

    hourly = run_pipeline(store, str(HERE), "hourly")
    assert set(hourly["features"]) == {
        "transactions", "customer_txn_stats", "customer_merchant_risk", "customer_risk_profile"
    }  # fmt: skip

    now = utcnow()
    spine = pd.DataFrame(
        {"customer_id": [1, 2, 3], "event_timestamp": [now] * 3, "amount": [10.0, 20.0, 30.0]}
    )
    offline = store.get_historical_features(spine, feature_service="fraud_model_v1")
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


def test_dbt_model_change_reversions_downstream_views(project):
    store = FeatureStore.from_repo(HERE)
    run_pipeline(store, str(HERE), "hourly")
    before = {v.name: v.version for v in store.list_feature_views()}

    sql = HERE / "transform" / "models" / "marts" / "fct_transactions.sql"
    original = sql.read_text()
    try:
        sql.write_text(original.replace("where amount > 0", "where amount > 5"))
        TransformConfig.model_validate(store.config.transform).dbt(str(HERE)).parse()
        after = {v.name: v.version for v in store.list_feature_views()}
    finally:
        sql.write_text(original)

    changed = {name for name in before if before[name] != after[name]}
    # Everything downstream of fct_transactions, including the on-demand view;
    # the dims and the views reading only them keep their versions.
    assert changed == {
        "transactions",
        "customer_txn_stats",
        "customer_merchant_risk",
        "customer_risk_profile",
        "txn_amount_vs_avg",
    }


def test_failing_dbt_test_stops_the_pipeline(project):
    with sqlite3.connect(project / "source.db") as conn:
        conn.execute("UPDATE customers SET country = 'XX' WHERE customer_id = 1")
    store = FeatureStore.from_repo(HERE)
    with pytest.raises(PipelineError, match="accepted_values"):
        run_pipeline(store, str(HERE), "daily")
    assert store.online_store.get_active_version("customer_profile") is None  # nothing written


def test_cli_dbt_passthrough_and_backfill(project, capsys):
    from shalf.pipelines.cli import main

    assert main(["--repo", str(HERE), "dbt", "ls", "--select", "tag:daily"]) == 0
    assert main(["--repo", str(HERE), "run", "daily", "--start", "2000-01-01", "--promote"]) == 0
    summary = capsys.readouterr().out
    assert '"customer_profile": 50' in summary
    assert main(["--repo", str(HERE), "run", "nope"]) == 1
