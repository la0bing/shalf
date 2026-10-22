"""Quickstart feature definitions on top of the project's dbt models.

    dbt model          feature views
    dim_customers   -> customer_profile
    fct_transactions -> transactions -> customer_txn_stats ----+-> customer_risk_profile
    dim_merchants   -> merchant_profile -+                     |
    fct_transactions + merchant_profile  +-> customer_merchant_risk
    customer_txn_stats + request data   -> txn_amount_vs_avg (on-demand)

Cleaning and business rules live in dbt (transform/); feature semantics
(windows, point-in-time joins, online serving) live here. Reading a database
directly is still possible, e.g. ``SQLiteSource(...)`` / ``PostgresSource(...)``.
"""

import pandas as pd
from features.entities import customer, merchant

from shalf.data import (
    Aggregate,
    AggregationFeatureView,
    DbtModelSource,
    FeatureService,
    FeatureView,
    derived_feature_view,
    on_demand_feature_view,
)

# --- base views: typed columns from dbt models -----------------------------------
customer_profile = FeatureView(
    name="customer_profile",
    entities=[customer],
    source=DbtModelSource(model="dim_customers", timestamp_field="updated_at"),
    schema={"age": int, "country": str, "is_premium": bool},
    ttl="365d",
    owner="growth-team",
)

transactions = FeatureView(
    name="transactions",
    entities=[customer],
    source=DbtModelSource(model="fct_transactions", timestamp_field="created_at"),
    schema={"amount": float, "merchant_id": int},
    ttl="30d",
    online=False,  # raw events: only used to build other features
)

merchant_profile = FeatureView(
    name="merchant_profile",
    entities=[merchant],
    source=DbtModelSource(model="dim_merchants", timestamp_field="updated_at"),
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
