"""Changing feature logic: versions, plan, backfill, promote."""

from datetime import timedelta

import pandas as pd
import pytest

from shalf.core import ShalfError
from shalf.data import (
    DataFrameSource,
    Entity,
    FeatureStore,
    FeatureView,
    InMemoryOnlineStore,
    SQLiteSource,
    derived_feature_view,
)
from shalf.data.types import utcnow

user = Entity(name="user", join_key="user_id")


def base_view(df: pd.DataFrame) -> FeatureView:
    return FeatureView(
        name="scores",
        entities=[user],
        source=DataFrameSource(name="scores", df=df, timestamp_field="ts"),
        schema={"score": float},
        ttl="30d",
    )


def doubled_v1(scores):
    @derived_feature_view(sources=[scores], schema={"scaled": float})
    def scaled(df):
        return df.assign(scaled=df["score"] * 2)

    return scaled


def doubled_v2(scores):
    @derived_feature_view(sources=[scores], schema={"scaled": float})
    def scaled(df):
        return df.assign(scaled=df["score"] * 10)  # the logic change

    return scaled


def downstream(scaled):
    @derived_feature_view(sources=[scaled], schema={"plus_one": float})
    def bumped(df):
        return df.assign(plus_one=df["scaled"] + 1)

    return bumped


def test_version_tracks_logic_not_location():
    a = SQLiteSource(name="s", path="dev.db", table="t", timestamp_field="ts")
    b = SQLiteSource(name="s", path="/prod/prod.db", table="t", timestamp_field="ts")
    c = SQLiteSource(name="s", path="dev.db", table="t2", timestamp_field="ts")
    view = lambda src: FeatureView(name="v", entities=[user], source=src, schema={"x": float})  # noqa: E731
    assert view(a).version == view(b).version  # dev and prod agree
    assert view(a).version != view(c).version  # different table = different logic

    df = pd.DataFrame({"user_id": [1], "score": [1.0], "ts": [utcnow()]})
    v1, v2 = doubled_v1(base_view(df)), doubled_v2(base_view(df))
    assert v1.version != v2.version
    assert downstream(v1).version != downstream(v2).version  # propagates down the DAG

    pinned = FeatureView(name="v", entities=[user], source=a, schema={"x": float}, version="7")
    assert pinned.version == "7"


def test_rollout_old_values_until_promotion():
    now = utcnow()
    df = pd.DataFrame(
        {"user_id": [1, 2], "score": [1.0, 2.0], "ts": [now - timedelta(hours=1)] * 2}
    )
    online = InMemoryOnlineStore()
    rows = {"user_id": [1, 2]}

    old = FeatureStore(online_store=online)
    v1 = doubled_v1(base_view(df))
    old.apply(downstream(v1))
    old.materialize(end=now)
    assert old.get_online_features(rows, ["bumped:plus_one"]).to_dict()["plus_one"] == [3.0, 5.0]

    # Deploy new code: same names, new scaling logic.
    new = FeatureStore(online_store=online)
    new.apply(downstream(doubled_v2(base_view(df))))
    plan = {r["view"]: r["status"] for r in new.plan()}
    assert plan == {"scores": "unchanged", "scaled": "changed", "bumped": "changed"}

    with pytest.raises(ShalfError, match="backfill it first"):
        new.promote()

    assert new.backfill(end=now) == {"scaled": 2, "bumped": 2}
    # Backfilled but not promoted: readers still get the old, consistent values.
    assert new.get_online_features(rows, ["bumped:plus_one"]).to_dict()["plus_one"] == [3.0, 5.0]

    new.promote()
    assert new.get_online_features(rows, ["bumped:plus_one"]).to_dict()["plus_one"] == [11.0, 21.0]
    assert {r["status"] for r in new.plan()} == {"unchanged"}

    # Offline, the new logic applies immediately (no backfill needed for correctness).
    spine = pd.DataFrame({"user_id": [1], "event_timestamp": [now]})
    assert new.get_historical_features(spine, ["bumped:plus_one"])["plus_one"].tolist() == [11.0]


def test_incremental_materialisation_auto_promotes_new_version():
    now = utcnow()
    df = pd.DataFrame({"user_id": [1], "score": [1.0], "ts": [now - timedelta(hours=1)]})
    online = InMemoryOnlineStore()
    old = FeatureStore(online_store=online)
    old.apply(doubled_v1(base_view(df)))
    old.materialize_incremental(end=now)

    new = FeatureStore(online_store=online)
    new.apply(doubled_v2(base_view(df)))
    new.materialize_incremental(end=now)  # warm-up of the new version, then switch
    assert new.get_online_features({"user_id": [1]}, ["scaled:scaled"]).to_dict()["scaled"] == [
        10.0
    ]
