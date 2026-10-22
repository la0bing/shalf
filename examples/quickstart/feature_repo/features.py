"""Quickstart feature definitions on top of a SQLite database.

DAG of views (arrows point downstream):

    customers ── customer_profile ────────────────────────────────┐
    transactions ── transactions ─┬── customer_txn_stats ─────────┼── customer_risk_profile
    merchants ── merchant_profile ┴── customer_merchant_risk ─────┘
                                      customer_txn_stats ── txn_amount_vs_avg (on-demand)

Switching a source to Postgres is a one-line change:
``PostgresSource(name=..., dsn=os.environ["SHALF_PG_DSN"], table=..., timestamp_field=...)``.
"""

import os
from pathlib import Path

import pandas as pd
from entities import customer, merchant

from shalf.data import (
    Aggregate,
    AggregationFeatureView,
    FeatureService,
    FeatureView,
    SQLiteSource,
    derived_feature_view,
    on_demand_feature_view,
)

DB_PATH = os.environ.get("SHALF_QUICKSTART_DB", str(Path(__file__).parent / "data" / "source.db"))

# --- base views: typed columns straight from the database ----------------------
customer_profile = FeatureView(
    name="customer_profile",
    entities=[customer],
    source=SQLiteSource(
        name="customers", path=DB_PATH, table="customers", timestamp_field="updated_at"
    ),
    schema={"age": int, "country": str, "is_premium": bool},
    ttl="365d",
    owner="growth-team",
)

transactions = FeatureView(
    name="transactions",
    entities=[customer],
    source=SQLiteSource(
        name="transactions",
        path=DB_PATH,
        # Any SELECT works; it is wrapped as a sub-query and filtered by time.
        query="SELECT customer_id, merchant_id, amount, created_at FROM transactions "
        "WHERE amount > 0",
        timestamp_field="created_at",
    ),
    schema={"amount": float, "merchant_id": int},
    ttl="30d",
    online=False,  # raw events: only used to build other features
)

merchant_profile = FeatureView(
    name="merchant_profile",
    entities=[merchant],
    source=SQLiteSource(
        name="merchants",
        path=DB_PATH,
        table="merchants",
        timestamp_field="updated_at",
        field_mapping={"risk_score": "merchant_risk_score"},
    ),
    schema={"merchant_risk_score": float, "category": str},
    ttl="365d",
)

# --- windowed aggregations: declared, not coded ----------------------------------
# One DuckDB query computes all of them in a single vectorised pass.
customer_txn_stats = AggregationFeatureView(
    name="customer_txn_stats",
    source=transactions,
    aggregations=[
        Aggregate(None, "count", "7d", name="txn_count_7d"),
        Aggregate("amount", "sum", "7d", name="txn_amount_sum_7d"),
        Aggregate("amount", "mean", "7d", name="txn_amount_avg_7d"),
        Aggregate("amount", "max", "1d"),  # auto-named amount_max_1d
    ],
)

customer_merchant_risk = AggregationFeatureView(
    name="customer_merchant_risk",
    # merchant_profile is joined onto each transaction via its merchant_id,
    # point-in-time correct, so its columns can be used in `where`.
    source=[transactions, merchant_profile],
    aggregations=[
        Aggregate("amount", "sum", "7d", where="merchant_risk_score > 0.7", name="risky_spend_7d"),
    ],
)


# --- custom logic when a declaration is not enough --------------------------------
@derived_feature_view(
    sources=[customer_merchant_risk, customer_txn_stats],  # derived on top of derived
    schema={"risky_spend_ratio_7d": float},
)
def customer_risk_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Share of the last 7 days' spend that went to risky merchants."""
    return df.assign(risky_spend_ratio_7d=df["risky_spend_7d"] / df["txn_amount_sum_7d"])


@on_demand_feature_view(
    sources=[customer_txn_stats],
    request_schema={"amount": float},
    schema={"amount_to_avg_ratio": float},
)
def txn_amount_vs_avg(df: pd.DataFrame) -> pd.DataFrame:
    """How unusual is the amount being scored, relative to the customer's 7-day mean."""
    return df.assign(amount_to_avg_ratio=df["amount"] / df["txn_amount_avg_7d"])


# --- what a model consumes ---------------------------------------------------------
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
