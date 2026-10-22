"""Declarative aggregations (DuckDB) vs. hand-written pandas rolling windows.

    uv run python examples/benchmarks/aggregations.py [rows]

Computes six features (count/sum/mean over 1d and 7d) per entity over
synthetic events, and checks both engines return the same values.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

from shalf.data import EVENT_TIMESTAMP, Aggregate
from shalf.data.aggregations import AggregationTransformation


def make_events(rows: int, entities: int = 50_000) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    start = pd.Timestamp("2024-01-01", tz="UTC")
    return pd.DataFrame(
        {
            "customer_id": rng.integers(0, entities, rows),
            EVENT_TIMESTAMP: start + pd.to_timedelta(rng.integers(0, 90 * 86_400, rows), unit="s"),
            "amount": rng.gamma(2.0, 30.0, rows),
        }
    )


def with_pandas(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.sort_values(EVENT_TIMESTAMP).set_index(EVENT_TIMESTAMP).groupby("customer_id")["amount"]
    )
    parts = []
    for window in ("1D", "7D"):
        rolled = grouped.rolling(window).agg(["count", "sum", "mean"])
        parts.append(rolled.add_suffix(f"_{window.lower()}"))
    return pd.concat(parts, axis=1).reset_index()


def with_shalf(df: pd.DataFrame) -> pd.DataFrame:
    aggregations = [
        Aggregate("amount", fn, window, name=f"{fn}_{window}")
        for window in ("1d", "7d")
        for fn in ("count", "sum", "mean")
    ]
    return AggregationTransformation(aggregations, ["customer_id"]).transform(df)


def timed(fn, df):
    started = time.perf_counter()
    out = fn(df)
    return out, time.perf_counter() - started


if __name__ == "__main__":
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
    events = make_events(rows)
    pandas_out, pandas_s = timed(with_pandas, events)
    shalf_out, shalf_s = timed(with_shalf, events)

    key = ["customer_id", EVENT_TIMESTAMP]
    a = pandas_out.sort_values(key).drop_duplicates(key, keep="last").reset_index(drop=True)
    b = shalf_out.sort_values(key).drop_duplicates(key, keep="last").reset_index(drop=True)
    for column in ("sum_1d", "mean_7d"):
        np.testing.assert_allclose(a[column], b[column], rtol=1e-9)

    print(f"{rows:,} events, 6 windowed features")
    print(f"  pandas rolling (hand-written): {pandas_s:6.2f}s")
    print(f"  shalf Aggregate (DuckDB):      {shalf_s:6.2f}s  ({pandas_s / shalf_s:.1f}x)")
