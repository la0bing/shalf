from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
