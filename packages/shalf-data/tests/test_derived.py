from datetime import timedelta

import pandas as pd
import pytest

from shalf.core import ShalfError
from shalf.data import (
    EVENT_TIMESTAMP,
    DerivedFeatureView,
    FeatureStore,
    Field,
    PandasTransformation,
    RegistryError,
    ValueType,
    derived_feature_view,
    on_demand_feature_view,
)


def build(orders, stores, profiles):
    @derived_feature_view(
        sources=[orders], schema=[Field("cum_amount"), Field("order_count", ValueType.INT64)]
    )
    def order_totals(df):
        df = df.sort_values(EVENT_TIMESTAMP)
        grouped = df.groupby("customer_id")["amount"]
        return df.assign(cum_amount=grouped.cumsum(), order_count=grouped.cumcount() + 1)

    # Multi-upstream: stores is joined on the order's store_id.
    @derived_feature_view(sources=[orders, stores], schema=[Field("weighted_amount")])
    def weighted_orders(df):
        return df.assign(weighted_amount=df["amount"] * df["store_score"])

    # Derived on top of derived, referencing an upstream by name.
    @derived_feature_view(sources=["order_totals", profiles], schema=[Field("spend_vs_credit")])
    def spend_ratio(df):
        return df.assign(spend_vs_credit=df["cum_amount"] / df["credit"])

    @on_demand_feature_view(
        sources=[order_totals], request_schema=[Field("basket")], schema=[Field("basket_vs_avg")]
    )
    def basket_ratio(df):
        return df.assign(basket_vs_avg=df["basket"] / (df["cum_amount"] / df["order_count"]))

    return order_totals, weighted_orders, spend_ratio, basket_ratio


def test_derived_chain_offline(orders, stores, profiles, ts):
    views = build(orders, stores, profiles)
    store = FeatureStore()
    store.apply(*views)  # orders/stores/profiles are registered implicitly
    assert {v.name for v in store.list_feature_views()} >= {"orders", "stores", "profiles"}
    assert views[2].entities == orders.entities  # inherited through a by-name upstream

    spine = pd.DataFrame({"customer_id": [1, 1, 1], "event_timestamp": [ts(1.5), ts(2.5), ts(12)]})
    df = store.get_historical_features(
        spine,
        [
            "order_totals:cum_amount",
            "weighted_orders:weighted_amount",
            "spend_ratio:spend_vs_credit",
        ],
    )
    assert df["cum_amount"].tolist() == [10.0, 30.0, 60.0]
    # store 20 (0.9) at t=2; at t=12 the order is at store 10 whose score changed to 0.5 at t=11
    assert df["weighted_amount"].tolist() == pytest.approx([1.0, 18.0, 15.0])
    # bronze credit 100 until t=10, then gold 500
    assert df["spend_vs_credit"].tolist() == pytest.approx([0.1, 0.3, 60.0 / 500.0])


def test_on_demand_offline_matches_online(orders, stores, profiles, ts):
    store = FeatureStore()
    store.apply(*build(orders, stores, profiles))
    spine = pd.DataFrame(
        {"customer_id": [1, 2], "event_timestamp": [ts(13), ts(13)], "basket": [40.0, 10.0]}
    )
    offline = store.get_historical_features(spine, ["basket_ratio:basket_vs_avg"])
    assert offline["basket_vs_avg"].tolist() == pytest.approx([2.0, 2.0])

    store.materialize(end=ts(13))
    online = store.get_online_features(
        {"customer_id": [1, 2]},
        ["basket_ratio:basket_vs_avg"],
        request_data={"basket": [40.0, 10.0]},
    )
    assert online.to_dict()["basket_vs_avg"] == pytest.approx([2.0, 2.0])


def test_on_demand_requires_request_data(orders, stores, profiles, ts):
    store = FeatureStore()
    store.apply(*build(orders, stores, profiles))
    spine = pd.DataFrame({"customer_id": [1], "event_timestamp": [ts(13)]})
    with pytest.raises(ShalfError, match="basket"):
        store.get_historical_features(spine, ["basket_ratio:basket_vs_avg"])


def test_cycles_are_rejected(customer, orders):
    t = PandasTransformation(lambda df: df)
    a = DerivedFeatureView(
        name="a", sources=["b"], schema=[Field("x")], transformation=t, entities=[customer]
    )
    b = DerivedFeatureView(
        name="b", sources=["a"], schema=[Field("y")], transformation=t, entities=[customer]
    )
    with pytest.raises(RegistryError, match="cycle"):
        FeatureStore().apply(a, b)


def test_unknown_upstream_and_unjoinable_upstream(customer, orders, profiles, stores):
    t = PandasTransformation(lambda df: df)
    with pytest.raises(RegistryError, match="unknown"):
        FeatureStore().apply(
            DerivedFeatureView(
                name="a",
                sources=["nope"],
                schema=[Field("x")],
                transformation=t,
                entities=[customer],
            )
        )
    # profiles has no store_id, so stores cannot be joined onto it.
    bad = DerivedFeatureView(
        name="bad", sources=[profiles, stores], schema=[Field("x")], transformation=t
    )
    with pytest.raises(RegistryError, match="store_id"):
        FeatureStore().apply(bad)


def test_transformation_output_is_validated(orders, ts):
    store = FeatureStore()
    missing = DerivedFeatureView(
        name="m",
        sources=[orders],
        schema=[Field("x")],
        transformation=PandasTransformation(lambda df: df),
    )
    store.apply(missing)
    with pytest.raises(ShalfError, match="did not produce"):
        store.get_historical_features(
            pd.DataFrame({"customer_id": [1], "event_timestamp": [ts(5)]}), ["m:x"]
        )


def test_incremental_materialisation_with_lookback_matches_full(orders, ts):
    @derived_feature_view(
        sources=[orders],
        schema=[Field("amount_6h")],
        lookback=timedelta(hours=6),
        ttl=timedelta(days=1),
    )
    def rolling(df):
        out = (
            df.sort_values(EVENT_TIMESTAMP)
            .set_index(EVENT_TIMESTAMP)
            .groupby("customer_id")["amount"]
            .rolling("6h")
            .sum()
            .reset_index()
        )
        return out.rename(columns={"amount": "amount_6h"})

    full, incremental = FeatureStore(), FeatureStore()
    for s in (full, incremental):
        s.apply(rolling)
    full.materialize(end=ts(13))
    incremental.materialize(end=ts(2.5))
    incremental.materialize(start=ts(2.5), end=ts(13))

    # Values are older than the ttl relative to the wall clock, so compare the stored records.
    view = full.registry.get_view("rolling")
    keys = ['[["customer_id",1]]', '[["customer_id",2]]']
    assert (
        [r.values for r in full.online_store.read_records(view, keys)]
        == [r.values for r in incremental.online_store.read_records(view, keys)]
        == [{"amount_6h": 30.0}, {"amount_6h": 5.0}]
    )
