from datetime import timedelta

import fakeredis
import pandas as pd
import pytest

from shalf.data import (
    DataFrameSource,
    Entity,
    FeatureStore,
    FeatureView,
    Field,
    InMemoryOnlineStore,
    RedisOnlineStore,
    SQLiteOnlineStore,
    ValueType,
    on_demand_feature_view,
)
from shalf.data.online import OnlineRecord, serialize_entity_key
from shalf.data.types import utcnow


@pytest.fixture(params=["memory", "sqlite", "redis"])
def online_store(request, tmp_path):
    if request.param == "memory":
        return InMemoryOnlineStore(project="t")
    if request.param == "sqlite":
        return SQLiteOnlineStore(path=tmp_path / "online.db", project="t")
    return RedisOnlineStore(client=fakeredis.FakeRedis(), project="t")


def make_view(df: pd.DataFrame, ttl=None) -> FeatureView:
    customer = Entity(name="customer", join_key="customer_id", value_type=ValueType.INT64)
    return FeatureView(
        name="stats",
        entities=[customer],
        source=DataFrameSource(name="stats", df=df, timestamp_field="ts"),
        schema=[Field("score"), Field("segment", ValueType.STRING)],
        ttl=ttl,
    )


def test_newer_values_win(online_store):
    now = utcnow()
    key = serialize_entity_key({"customer_id": 1})
    online_store.write_records("stats@v1", [OnlineRecord(key, {"score": 2.0}, now)])
    online_store.write_records(
        "stats@v1", [OnlineRecord(key, {"score": 1.0}, now - timedelta(hours=1))]
    )
    assert online_store.read_records("stats@v1", [key, "missing"])[0].values == {"score": 2.0}
    assert online_store.read_records("stats@v1", [key, "missing"])[1] is None
    assert online_store.read_records("stats@v2", [key]) == [None]  # versions are isolated

    online_store.set_watermark("stats", "v1", now)
    assert online_store.get_watermark("stats", "v1") == now.floor("us")
    assert online_store.get_watermark("stats", "v2") is None
    online_store.set_active_version("stats", "v1")
    assert online_store.get_active_version("stats") == "v1"


def test_read_only_store_refuses_writes(tmp_path):
    store = SQLiteOnlineStore(path=tmp_path / "o.db", read_only=True)
    view = make_view(pd.DataFrame({"customer_id": [], "score": [], "segment": [], "ts": []}))
    with pytest.raises(PermissionError):
        store.write_frame(view, pd.DataFrame(), "v1")
    with pytest.raises(PermissionError):
        store.set_active_version("stats", "v1")


def test_materialize_and_read(online_store):
    now = utcnow()
    df = pd.DataFrame(
        {
            "customer_id": [1, 1, 2, 3],
            "score": [0.1, 0.2, 0.3, 0.4],
            "segment": ["a", "b", "c", "d"],
            "ts": [
                now - timedelta(hours=3),
                now - timedelta(hours=2),
                now - timedelta(hours=1),
                now - timedelta(days=5),
            ],
        }
    )
    store = FeatureStore(online_store=online_store)
    store.apply(make_view(df, ttl=timedelta(days=1)))
    assert store.materialize(end=now) == {"stats": 3}

    # keys arriving as strings (e.g. JSON / query params) are coerced to the entity type
    out = store.get_online_features(
        {"customer_id": ["1", 2, 3, 4]}, ["stats:score", "stats:segment"]
    ).to_dict()
    assert out["score"] == [0.2, 0.3, None, None]  # customer 3 is older than the ttl
    assert out["segment"] == ["b", "c", None, None]


def test_incremental_uses_watermark(online_store):
    now = utcnow()
    df = pd.DataFrame(
        {"customer_id": [1], "score": [1.0], "segment": ["a"], "ts": [now - timedelta(hours=1)]}
    )
    store = FeatureStore(online_store=online_store)
    store.apply(make_view(df))
    assert store.materialize_incremental(end=now) == {"stats": 1}
    assert store.materialize_incremental(end=now + timedelta(minutes=1)) == {"stats": 0}


def test_python_mode_on_demand_view():
    now = utcnow()
    view = make_view(
        pd.DataFrame({"customer_id": [1], "score": [0.5], "segment": ["a"], "ts": [now]})
    )

    @on_demand_feature_view(sources=[view], schema=[Field("score_x2")], mode="python")
    def doubled(row):
        return {"score_x2": row["score"] * 2}

    store = FeatureStore()
    store.apply(doubled)
    store.materialize(end=now + timedelta(seconds=1))
    assert store.get_online_features([{"customer_id": 1}], ["doubled:score_x2"]).to_dict() == {
        "customer_id": [1],
        "score_x2": [1.0],
    }
