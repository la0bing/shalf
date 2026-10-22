from datetime import timedelta

import pandas as pd
import pytest

from shalf.core import ShalfError
from shalf.data import DataFrameSource, Entity, FeatureStore, FeatureView, Field, ValueType


@pytest.fixture()
def fs(profiles):
    store = FeatureStore()
    store.apply(profiles)
    return store


def test_point_in_time_join_never_leaks_future_values(fs, ts):
    spine = pd.DataFrame(
        {
            "customer_id": [1, 1, 1, 2, 2, 3],
            "event_timestamp": [ts(-1), ts(9), ts(10), ts(4), ts(6), ts(6)],
        },
        index=[10, 11, 12, 13, 14, 15],
    )
    df = fs.get_historical_features(spine, ["profiles:tier", "profiles:credit"])
    tiers = [None if pd.isna(t) else t for t in df["tier"]]
    assert tiers == [None, "bronze", "gold", None, "silver", None]
    assert df["credit"].tolist()[2] == 500.0
    assert list(df.columns) == ["customer_id", "event_timestamp", "tier", "credit"]
    pd.testing.assert_frame_equal(
        df[["customer_id"]], spine[["customer_id"]].reset_index(drop=True)
    )


def test_ttl_expires_old_values(profiles, ts):
    profiles.ttl = timedelta(hours=3)
    store = FeatureStore()
    store.apply(profiles)
    spine = pd.DataFrame({"customer_id": [1, 1], "event_timestamp": [ts(2), ts(4)]})
    tiers = store.get_historical_features(spine, ["profiles:tier"])["tier"]
    assert tiers.iloc[0] == "bronze"
    assert pd.isna(tiers.iloc[1])


def test_created_timestamp_breaks_ties(ts):
    customer = Entity(name="customer", join_key="customer_id")
    source = DataFrameSource(
        name="s",
        df=pd.DataFrame(
            {"customer_id": [1, 1], "v": [2.0, 1.0], "t": [ts(0), ts(0)], "c": [ts(2), ts(1)]}
        ),
        timestamp_field="t",
        created_timestamp_field="c",
    )
    view = FeatureView(name="s", entities=[customer], source=source, schema=[Field("v")])
    store = FeatureStore()
    store.apply(view)
    out = store.get_historical_features(
        pd.DataFrame({"customer_id": [1], "event_timestamp": [ts(1)]}), ["s:v"]
    )
    assert out["v"].tolist() == [2.0]


def test_full_feature_names_and_collisions(profiles, customer, ts):
    other = FeatureView(
        name="other",
        entities=[customer],
        source=profiles.source,
        schema=[Field("tier", ValueType.STRING)],
    )
    store = FeatureStore()
    store.apply(profiles, other)
    spine = pd.DataFrame({"customer_id": [1], "event_timestamp": [ts(11)]})
    with pytest.raises(ShalfError, match="full_feature_names"):
        store.get_historical_features(spine, ["profiles:tier", "other:tier"])
    df = store.get_historical_features(
        spine, ["profiles:tier", "other:tier"], full_feature_names=True
    )
    assert df[["profiles__tier", "other__tier"]].iloc[0].tolist() == ["gold", "gold"]


def test_wildcard_and_custom_timestamp_column(fs, ts):
    spine = pd.DataFrame({"customer_id": [2], "as_of": [ts(6)]})
    df = fs.get_historical_features(spine, ["profiles:*"], timestamp_column="as_of")
    assert list(df.columns) == ["customer_id", "as_of", "tier", "credit"]


def test_declared_types_are_enforced(fs, ts):
    df = fs.get_historical_features(
        pd.DataFrame({"customer_id": [1], "event_timestamp": [ts(11)]}), ["profiles:credit"]
    )
    assert df["credit"].dtype == "float64"
