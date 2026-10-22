"""Declarative windowed aggregations.

Most features data scientists write are "<function> of <column> over the last
<window> per <entity>". Instead of hand-writing pandas rolling code::

    customer_txn_stats = AggregationFeatureView(
        name="customer_txn_stats",
        source=transactions,
        aggregations=[
            Aggregate("amount", "sum", "7d"),             # -> amount_sum_7d
            Aggregate("amount", "mean", "30d"),           # -> amount_mean_30d
            Aggregate(None, "count", "1d"),               # -> count_1d
            Aggregate("amount", "sum", "7d", where="merchant_risk_score > 0.7",
                      name="risky_spend_7d"),
        ],
    )

All aggregates are compiled into one SQL query with window functions and run
by DuckDB: vectorised, multi-threaded, and a single pass over the data however
many features are declared. ``lookback`` and ``ttl`` default to the longest
window, so incremental materialisation reads only the history it needs.

Window semantics: the value at time ``t`` covers events in ``(t - window, t]``.
Events sharing a timestamp are all included.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, ClassVar

import duckdb
import pandas as pd

from shalf.data.entity import Entity
from shalf.data.feature_view import BaseFeatureView, DerivedFeatureView
from shalf.data.transformations import Transformation
from shalf.data.types import (
    EVENT_TIMESTAMP,
    Field,
    ValueType,
    format_duration,
    parse_duration,
    to_utc,
)

_SQL_FUNCTIONS = {
    "count": "COUNT",
    "sum": "SUM",
    "mean": "AVG",
    "min": "MIN",
    "max": "MAX",
    "std": "STDDEV_SAMP",
}


@dataclass(frozen=True)
class Aggregate:
    """``function`` of ``column`` over ``window``; ``column=None`` with ``count`` counts rows.

    ``where`` is an optional SQL filter over the input columns, e.g.
    ``"status = 'refunded'"``.
    """

    column: str | None
    function: str
    window: timedelta | str
    name: str | None = None
    where: str | None = None

    def __post_init__(self) -> None:
        if self.function not in _SQL_FUNCTIONS:
            raise ValueError(
                f"Unknown aggregate {self.function!r}; use one of {sorted(_SQL_FUNCTIONS)}"
            )
        if self.column is None and self.function != "count":
            raise ValueError(f"Aggregate {self.function!r} needs a column")
        object.__setattr__(self, "window", parse_duration(self.window))

    @property
    def window_delta(self) -> timedelta:
        assert isinstance(self.window, timedelta)
        return self.window

    @property
    def output_name(self) -> str:
        if self.name:
            return self.name
        window = format_duration(self.window_delta)
        return (
            f"count_{window}" if self.column is None else f"{self.column}_{self.function}_{window}"
        )

    @property
    def dtype(self) -> ValueType:
        return ValueType.INT64 if self.function == "count" else ValueType.FLOAT64

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "function": self.function,
            "window": format_duration(self.window_delta),
            "name": self.output_name,
            "where": self.where,
        }


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class AggregationTransformation(Transformation):
    """Compiles :class:`Aggregate` s into one DuckDB window-function query."""

    mode: ClassVar[str] = "aggregate"

    def __init__(self, aggregations: Sequence[Aggregate], partition_by: Sequence[str] = ()) -> None:
        super().__init__(fn=self.transform)
        self.aggregations = list(aggregations)
        self.partition_by = list(partition_by)

    @property
    def name(self) -> str:
        return "aggregate"

    def describe(self) -> dict[str, Any]:
        return {"mode": self.mode, "aggregations": [a.to_dict() for a in self.aggregations]}

    def fingerprint(self) -> dict[str, Any]:
        return self.describe()

    def sql(self) -> str:
        windows = sorted({a.window_delta for a in self.aggregations})
        window_names = {w: f"w{i}" for i, w in enumerate(windows)}
        partition = ", ".join(_quote(k) for k in self.partition_by)
        ts = _quote(EVENT_TIMESTAMP)

        selects = [_quote(k) for k in self.partition_by] + [ts]
        for agg in self.aggregations:
            argument = "*" if agg.column is None else _quote(agg.column)
            expr = f"{_SQL_FUNCTIONS[agg.function]}({argument})"
            if agg.where:
                expr += f" FILTER (WHERE {agg.where})"
            expr += f" OVER {window_names[agg.window_delta]}"
            if agg.function in ("count", "sum"):
                expr = f"COALESCE({expr}, 0)"
            selects.append(f"{expr} AS {_quote(agg.output_name)}")

        clauses = []
        for window, label in window_names.items():
            # (t - window, t]: RANGE PRECEDING is inclusive, so stop 1 microsecond short.
            micros = int(window.total_seconds() * 1_000_000) - 1
            clauses.append(
                f"{label} AS (PARTITION BY {partition} ORDER BY {ts} "
                f"RANGE BETWEEN INTERVAL ({micros}::BIGINT) MICROSECOND PRECEDING AND CURRENT ROW)"
            )
        return f"SELECT {', '.join(selects)} FROM spine WINDOW {', '.join(clauses)}"

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.partition_by:
            raise RuntimeError("AggregationTransformation has no partition keys")
        spine = df.copy()
        spine[EVENT_TIMESTAMP] = to_utc(spine[EVENT_TIMESTAMP]).dt.tz_convert(None)
        with duckdb.connect() as con:
            con.register("spine", spine)
            out = con.execute(self.sql()).df()
        out[EVENT_TIMESTAMP] = to_utc(out[EVENT_TIMESTAMP].dt.tz_localize("UTC"))
        for agg in self.aggregations:
            if agg.function == "count":
                out[agg.output_name] = out[agg.output_name].astype("int64")
        return out


class AggregationFeatureView(DerivedFeatureView):
    """A derived view declared as windowed aggregates over its upstream view(s).

    ``source`` is the events view (or a list: primary first, then views joined
    onto it point-in-time, e.g. merchant attributes usable in ``where``).
    Entities default to the primary's; ``lookback`` and ``ttl`` default to the
    longest window.
    """

    kind = "aggregation"

    def __init__(
        self,
        *,
        name: str,
        source: BaseFeatureView | str | Sequence[BaseFeatureView | str],
        aggregations: Sequence[Aggregate],
        entities: Sequence[Entity] | None = None,
        ttl: timedelta | str | None = None,
        lookback: timedelta | str | None = None,
        **kwargs: Any,
    ) -> None:
        if not aggregations:
            raise ValueError(f"Aggregation view {name!r} needs at least one Aggregate")
        sources = list(source) if isinstance(source, list | tuple) else [source]
        longest = max(a.window_delta for a in aggregations)
        self.aggregations = list(aggregations)
        super().__init__(
            name=name,
            sources=sources,
            schema=[Field(a.output_name, a.dtype) for a in aggregations],
            transformation=AggregationTransformation(aggregations),
            entities=entities,
            ttl=ttl if ttl is not None else longest,
            lookback=lookback if lookback is not None else longest,
            **kwargs,
        )

    def _inherit_from_primary(self) -> None:
        super()._inherit_from_primary()
        assert isinstance(self.transformation, AggregationTransformation)
        self.transformation.partition_by = self.join_keys
