from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any

import numpy as np
import pandas as pd

# Canonical column names. Every DataSource returns its event time under
# EVENT_TIMESTAMP so the rest of the data layer never needs to know how a
# particular table names it.
EVENT_TIMESTAMP = "event_timestamp"
CREATED_TIMESTAMP = "created_timestamp"


class ValueType(StrEnum):
    INT64 = "int64"
    FLOAT64 = "float64"
    STRING = "string"
    BOOL = "bool"
    TIMESTAMP = "timestamp"

    @classmethod
    def of(cls, value: ValueType | type | str) -> ValueType:
        """Accept a ValueType, a Python type (``int``, ``str``...) or a name (``"float64"``)."""
        if isinstance(value, ValueType):
            return value
        if isinstance(value, str):
            return cls(value)
        try:
            return _PYTHON_TYPES[value]
        except KeyError:
            raise TypeError(f"Cannot map {value!r} to a ValueType") from None

    def coerce(self, value: Any) -> Any:
        """Coerce a scalar (e.g. an entity key arriving as JSON) to this type."""
        if value is None:
            return None
        if self is ValueType.INT64:
            return int(value)
        if self is ValueType.FLOAT64:
            return float(value)
        if self is ValueType.STRING:
            return str(value)
        if self is ValueType.BOOL:
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "t", "yes", "y"}
            return bool(value)
        return as_utc_datetime(value)


_PYTHON_TYPES: dict[Any, ValueType] = {
    int: ValueType.INT64,
    float: ValueType.FLOAT64,
    str: ValueType.STRING,
    bool: ValueType.BOOL,
    datetime: ValueType.TIMESTAMP,
    date: ValueType.TIMESTAMP,
}

_PANDAS_DTYPES = {
    ValueType.INT64: "Int64",
    ValueType.FLOAT64: "float64",
    ValueType.STRING: "string",
    ValueType.BOOL: "boolean",
}


def cast_series(values: pd.Series, dtype: ValueType) -> pd.Series:
    """Cast a column to the pandas dtype of a declared ValueType (nullable where possible)."""
    if dtype is ValueType.TIMESTAMP:
        return to_utc(values)
    return values.astype(_PANDAS_DTYPES[dtype])


@dataclass(frozen=True)
class Field:
    """A named, typed column: a feature, or a field of request data."""

    name: str
    dtype: ValueType = ValueType.FLOAT64
    description: str = ""
    tags: dict[str, str] = field(default_factory=dict, hash=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "dtype": self.dtype.value, "description": self.description}


SchemaLike = Sequence["Field | str"] | Mapping[str, "ValueType | type | str"]


def normalize_schema(schema: SchemaLike) -> list[Field]:
    """``[Field(...)]``, ``["a", "b"]`` (float64) or ``{"age": int, "country": str}``."""
    if isinstance(schema, Mapping):
        return [Field(name, ValueType.of(dtype)) for name, dtype in schema.items()]
    return [f if isinstance(f, Field) else Field(f) for f in schema]


_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(s|m|h|d|w)\s*$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(value: timedelta | str | None) -> timedelta | None:
    """``"30m"``, ``"12h"``, ``"7d"``, ``"2w"`` or a timedelta."""
    if value is None or isinstance(value, timedelta):
        return value
    match = _DURATION.match(value)
    if not match:
        raise ValueError(f"Invalid duration {value!r}; use e.g. '30m', '12h', '7d', '2w'")
    return timedelta(seconds=float(match.group(1)) * _UNIT_SECONDS[match.group(2)])


def format_duration(value: timedelta) -> str:
    """Shortest exact form in d/h/m/s: 7 days -> "7d", 90 minutes -> "90m"."""
    seconds = int(value.total_seconds())
    for unit in ("d", "h", "m"):
        if seconds % _UNIT_SECONDS[unit] == 0:
            return f"{seconds // _UNIT_SECONDS[unit]}{unit}"
    return f"{seconds}s"


def to_utc(values: pd.Series, unit: str | None = None) -> pd.Series:
    """Normalise timestamps (strings, epochs, naive or aware) to datetime64[ns, UTC]."""
    if unit is not None:
        parsed = pd.to_datetime(values, unit=unit, utc=True)
    elif pd.api.types.is_datetime64_any_dtype(values):
        parsed = pd.to_datetime(values, utc=True)
    else:
        parsed = pd.to_datetime(values, utc=True, format="ISO8601")
    return parsed.astype("datetime64[ns, UTC]")


def as_utc_datetime(value: datetime | str | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def utcnow() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(UTC))


def to_python(value: Any) -> Any:
    """Convert numpy / pandas scalars into plain JSON-friendly Python values."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp | datetime):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NA or value is pd.NaT:
        return None
    return value
