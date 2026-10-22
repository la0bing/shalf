"""Quickstart feature definitions on top of a SQLite database.

DAG of views (arrows point downstream):

    customers ── customer_profile ─────────────────────────────┐
    transactions ── transactions ─┬── customer_txn_stats ──┬── customer_risk_profile
    merchants ── merchant_profile ┴── customer_merchant_risk ┘
                                      customer_txn_stats ── txn_amount_vs_avg (on-demand)

Switching the source to Postgres is a one-line change per source:
``PostgresSource(name=..., dsn=os.environ["SHALF_PG_DSN"], table=..., timestamp_field=...)``.
"""

import os
from datetime import timedelta
from pathlib import Path

import pandas as pd
from entities import customer, merchant

from shalf.data import (
    EVENT_TIMESTAMP,
    FeatureService,
    FeatureView,
    Field,
    SQLiteSource,
    ValueType,
    derived_feature_view,
    on_demand_feature_view,
)

DB_PATH = os.environ.get("SHALF_QUICKSTART_DB", str(Path(__file__).parent / "data" / "source.db"))

# --- sources -----------------------------------------------------------------
customers_source = SQLiteSource(
    name="customers", path=DB_PATH, table="customers", timestamp_field="updated_at"
)
transactions_source = SQLiteSource(
    name="transactions",
    path=DB_PATH,
    # Any SELECT works; it is wrapped as a sub-query and filtered by time.
    query="SELECT customer_id, merchant_id, amount, created_at FROM transactions WHERE amount > 0",
    timestamp_field="created_at",
)
merchants_source = SQLiteSource(
    name="merchants",
    path=DB_PATH,
    table="merchants",
    timestamp_field="updated_at",
    field_mapping={"risk_score": "merchant_risk_score"},
)

# --- base views: columns straight from the database ----------------------------
customer_profile = FeatureView(
    name="customer_profile",
    entities=[customer],
    source=customers_source,
    ttl=timedelta(days=365),
    schema=[
        Field("age", ValueType.INT64),
        Field("country", ValueType.STRING),
        Field("is_premium", ValueType.BOOL),
    ],
    owner="growth-team",
)

transactions = FeatureView(
    name="transactions",
    entities=[customer],
    source=transactions_source,
    ttl=timedelta(days=30),
    schema=[Field("amount", ValueType.FLOAT64), Field("merchant_id", ValueType.INT64)],
    online=False,  # raw events: only used to build other features
)

merchant_profile = FeatureView(
    name="merchant_profile",
    entities=[merchant],
    source=merchants_source,
    ttl=timedelta(days=365),
    schema=[Field("merchant_risk_score", ValueType.FLOAT64), Field("category", ValueType.STRING)],
)


# --- derived views: features on top of features --------------------------------
@derived_feature_view(
    sources=[transactions],
    schema=[
        Field("txn_count_7d", ValueType.INT64),
        Field("txn_amount_sum_7d", ValueType.FLOAT64),
        Field("txn_amount_avg_7d", ValueType.FLOAT64),
    ],
    ttl=timedelta(days=7),
    lookback=timedelta(days=7),
)
def customer_txn_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling 7-day transaction count / sum / mean per customer."""
    rolled = (
        df.sort_values(EVENT_TIMESTAMP)
        .set_index(EVENT_TIMESTAMP)
        .groupby("customer_id")["amount"]
        .rolling("7D")
        .agg(["count", "sum"])
        .reset_index()
    )
    return pd.DataFrame(
        {
            "customer_id": rolled["customer_id"],
            EVENT_TIMESTAMP: rolled[EVENT_TIMESTAMP],
            "txn_count_7d": rolled["count"].astype("int64"),
            "txn_amount_sum_7d": rolled["sum"],
            "txn_amount_avg_7d": rolled["sum"] / rolled["count"],
        }
    )


@derived_feature_view(
    # Two upstreams: merchant_profile is joined onto each transaction via the
    # transaction's merchant_id, point-in-time correct.
    sources=[transactions, merchant_profile],
    schema=[Field("risky_spend_7d", ValueType.FLOAT64)],
    ttl=timedelta(days=7),
    lookback=timedelta(days=7),
)
def customer_merchant_risk(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling 7-day spend at merchants with a risk score above 0.7."""
    df = df.assign(risky_amount=df["amount"].where(df["merchant_risk_score"] > 0.7, 0.0))
    rolled = (
        df.sort_values(EVENT_TIMESTAMP)
        .set_index(EVENT_TIMESTAMP)
        .groupby("customer_id")["risky_amount"]
        .rolling("7D")
        .sum()
        .reset_index()
    )
    return rolled.rename(columns={"risky_amount": "risky_spend_7d"})


@derived_feature_view(
    # Derived on top of two *derived* views.
    sources=[customer_merchant_risk, customer_txn_stats],
    schema=[Field("risky_spend_ratio_7d", ValueType.FLOAT64)],
)
def customer_risk_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Share of the last 7 days' spend that went to risky merchants."""
    return df.assign(risky_spend_ratio_7d=df["risky_spend_7d"] / df["txn_amount_sum_7d"])


# --- on-demand: computed at request time, here from request data --------------
@on_demand_feature_view(
    sources=[customer_txn_stats],
    request_schema=[Field("amount", ValueType.FLOAT64)],
    schema=[Field("amount_to_avg_ratio", ValueType.FLOAT64)],
)
def txn_amount_vs_avg(df: pd.DataFrame) -> pd.DataFrame:
    """How unusual is the amount being scored, relative to the customer's 7-day mean."""
    return df.assign(amount_to_avg_ratio=df["amount"] / df["txn_amount_avg_7d"])


# --- what a model consumes -------------------------------------------------------
fraud_model_v1 = FeatureService(
    name="fraud_model_v1",
    features=[
        customer_profile[["age", "is_premium"]],
        customer_txn_stats,
        customer_risk_profile,
        txn_amount_vs_avg,
    ],
    owner="risk-team",
)
