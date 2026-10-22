from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from shalf.data import (
    Aggregate,
    AggregationFeatureView,
    DataFrameSource,
    Entity,
    FeatureStore,
    FeatureView,
    Field,
    ValueType,
)
from shalf.data.types import format_duration, normalize_schema, parse_duration


def events(n: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-01-01", tz="UTC")
    return pd.DataFrame(
        {
            "user_id": rng.integers(1, 6, n),
            "amount": rng.gamma(2.0, 10.0, n).round(2),
            "kind": rng.choice(["a", "b"], n),
            # minute resolution so some events share timestamps
            "ts": start + pd.to_timedelta(rng.integers(0, 60 * 24 * 20, n), unit="min"),
        }
    )


def make_view(df: pd.DataFrame) -> FeatureView:
    user = Entity(name="user", join_key="user_id")
    return FeatureView(
        name="events",
        entities=[user],
        source=DataFrameSource(name="events", df=df, timestamp_field="ts"),
        schema={"amount": float, "kind": str},
        online=False,
    )


def brute_force(df: pd.DataFrame, at: pd.Timestamp, user: int, window: timedelta) -> pd.DataFrame:
    rows = df[(df.user_id == user) & (df.ts > at - window) & (df.ts <= at)]
    return rows


def test_aggregates_match_brute_force():
    df = events()
    view = AggregationFeatureView(
        name="user_stats",
        source=make_view(df),
        aggregations=[
            Aggregate(None, "count", "3d"),
            Aggregate("amount", "sum", "3d"),
            Aggregate("amount", "mean", "7d"),
            Aggregate("amount", "max", "1d"),
            Aggregate("amount", "std", "7d"),
            Aggregate("amount", "sum", "7d", where="kind = 'b'", name="b_spend_7d"),
        ],
    )
    assert view.feature_names == [
        "count_3d",
        "amount_sum_3d",
        "amount_mean_7d",
        "amount_max_1d",
        "amount_std_7d",
        "b_spend_7d",
    ]
    assert view.ttl == view.lookback == timedelta(days=7)
    assert view.field("count_3d").dtype is ValueType.INT64

    store = FeatureStore()
    store.apply(view)
    spine = df.sample(60, random_state=1)[["user_id", "ts"]].rename(
        columns={"ts": "event_timestamp"}
    )
    out = store.get_historical_features(spine.reset_index(drop=True), ["user_stats:*"])

    for row in out.itertuples():
        at, user = row.event_timestamp, row.user_id
        w3 = brute_force(df, at, user, timedelta(days=3))
        w7 = brute_force(df, at, user, timedelta(days=7))
        w1 = brute_force(df, at, user, timedelta(days=1))
        assert row.count_3d == len(w3)
        assert row.amount_sum_3d == pytest.approx(w3.amount.sum())
        assert row.amount_mean_7d == pytest.approx(w7.amount.mean())
        assert row.amount_max_1d == pytest.approx(w1.amount.max())
        if len(w7) > 1:
            assert row.amount_std_7d == pytest.approx(w7.amount.std())
        assert row.b_spend_7d == pytest.approx(w7[w7.kind == "b"].amount.sum())


def test_aggregate_validation():
    with pytest.raises(ValueError, match="Unknown aggregate"):
        Aggregate("amount", "median", "7d")
    with pytest.raises(ValueError, match="needs a column"):
        Aggregate(None, "sum", "7d")
    with pytest.raises(ValueError, match="Invalid duration"):
        Aggregate("amount", "sum", "7 days")


def test_shorthands():
    assert parse_duration("90m") == timedelta(minutes=90)
    assert parse_duration("2w") == timedelta(days=14)
    assert format_duration(timedelta(days=7)) == "7d"
    assert normalize_schema({"a": int, "b": "string", "c": bool}) == [
        Field("a", ValueType.INT64),
        Field("b", ValueType.STRING),
        Field("c", ValueType.BOOL),
    ]
    assert normalize_schema(["x"]) == [Field("x", ValueType.FLOAT64)]
