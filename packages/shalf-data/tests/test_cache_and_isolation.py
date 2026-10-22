"""Offline cache, cache-only exploration, profiles, and online isolation from sources."""

from datetime import timedelta

import pandas as pd
import pytest

from shalf.data import (
    Aggregate,
    AggregationFeatureView,
    DataFrameSource,
    Entity,
    FeatureStore,
    FeatureStoreConfig,
    FeatureView,
)
from shalf.data.offline import CacheMissError, ParquetFeatureCache
from shalf.data.types import utcnow


class CountingSource(DataFrameSource):
    reads = 0
    fail = False

    def _read(self, columns, start, end):
        if self.fail:
            raise AssertionError("source database must not be queried")
        self.reads += 1
        return super()._read(columns, start, end)


@pytest.fixture()
def setup(tmp_path):
    now = utcnow().floor("min")
    df = pd.DataFrame(
        {
            "user_id": [1, 1, 2, 2, 1],
            "amount": [1.0, 2.0, 3.0, 4.0, 5.0],
            "ts": [now - timedelta(hours=h) for h in (50, 30, 20, 10, 1)],
        }
    )
    source = CountingSource(name="events", df=df, timestamp_field="ts")
    user = Entity(name="user", join_key="user_id")
    events = FeatureView(
        name="events", entities=[user], source=source, schema={"amount": float}, online=False
    )
    stats = AggregationFeatureView(
        name="stats", source=events, aggregations=[Aggregate("amount", "sum", "2d")]
    )
    config = FeatureStoreConfig(
        offline_store={"type": "pandas", "cache_path": str(tmp_path / "cache")}
    )
    return now, source, events, stats, config


def test_materialised_ranges_are_served_from_cache(setup):
    now, source, _events, stats, config = setup
    store = FeatureStore(config)
    store.apply(stats)
    store.materialize(end=now + timedelta(seconds=5))
    reads_after_materialize = source.reads
    assert reads_after_materialize == 1  # raw events read once, then cached

    source.fail = True  # from here on any source query fails the test
    spine = pd.DataFrame({"user_id": [1, 2], "event_timestamp": [now, now]})
    out = store.get_historical_features(spine, ["stats:amount_sum_2d"])
    assert out["amount_sum_2d"].tolist() == [7.0, 7.0]  # 2+5 (50h-old event excluded), 3+4


def test_cache_only_never_touches_sources(setup, tmp_path):
    now, source, _events, stats, config = setup
    eda = FeatureStore(
        config.model_copy(update={"offline_store": {**config.offline_store, "cache_only": True}})
    )
    eda.apply(stats)
    spine = pd.DataFrame({"user_id": [1], "event_timestamp": [now]})
    with pytest.raises(CacheMissError):
        eda.get_historical_features(spine, ["stats:amount_sum_2d"])
    assert source.reads == 0


def test_online_reads_never_touch_sources(setup):
    now, source, _events, stats, config = setup
    store = FeatureStore(config)
    store.apply(stats)
    store.materialize(end=now + timedelta(seconds=5))
    source.fail = True
    assert store.get_online_features({"user_id": [1, 2]}, ["stats:amount_sum_2d"]).to_dict()[
        "amount_sum_2d"
    ] == [7.0, 7.0]


def test_cache_window_rewrites_do_not_duplicate(tmp_path):
    cache = ParquetFeatureCache(tmp_path)
    t = pd.Timestamp("2024-01-01", tz="UTC")
    frame = lambda hours, v: pd.DataFrame(  # noqa: E731
        {
            "k": [1] * len(hours),
            "event_timestamp": [t + pd.Timedelta(hours=h) for h in hours],
            "x": v,
        }
    )
    cache.write("v", "1", frame([1, 30], [1.0, 2.0]), None, t + pd.Timedelta(hours=48))
    cache.write(
        "v", "1", frame([30], [9.0]), t + pd.Timedelta(hours=24), t + pd.Timedelta(hours=48)
    )
    cache.write(
        "v", "1", frame([50], [3.0]), t + pd.Timedelta(hours=48), t + pd.Timedelta(hours=72)
    )
    df = cache.read("v", "1", None, None)
    assert df.sort_values("event_timestamp")["x"].tolist() == [1.0, 9.0, 3.0]
    assert cache.coverage("v", "1") == [(None, t + pd.Timedelta(hours=72))]
    assert cache.covers("v", "1", t, t + pd.Timedelta(hours=70))
    assert not cache.covers("v", "1", t, t + pd.Timedelta(hours=80))
    assert not cache.covers("v", "2", t, t + pd.Timedelta(hours=1))


def test_profiles_select_isolated_stores(tmp_path, monkeypatch):
    monkeypatch.delenv("REPLICA_URL", raising=False)
    (tmp_path / "shalf.yaml").write_text(
        """
project: p
definitions: []
online_store: {type: sqlite, path: online.db}
profiles:
  eda:
    online_store: {type: sqlite, path: "${REPLICA_URL}", read_only: true}
    offline_store: {type: pandas, cache_path: cache, cache_only: true}
"""
    )
    serving = FeatureStore.from_repo(tmp_path)  # REPLICA_URL unset: only eda needs it
    assert not serving.online_store.read_only

    monkeypatch.setenv("REPLICA_URL", str(tmp_path / "replica.db"))
    eda = FeatureStore.from_repo(tmp_path, profile="eda")
    assert eda.online_store.read_only
    assert eda.online_store.path == str(tmp_path / "replica.db")
    assert eda.offline_store.cache_only
    assert str(eda.offline_store.cache.path) == str(tmp_path / "cache")
