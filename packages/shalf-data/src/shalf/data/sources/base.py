from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, ClassVar

import pandas as pd

from shalf.core import PluginRegistry
from shalf.data.types import CREATED_TIMESTAMP, EVENT_TIMESTAMP, as_utc_datetime, to_utc


class DataSource(ABC):
    """Where raw, timestamped rows come from.

    Subclasses implement one method, :meth:`_read`, which returns raw rows whose
    event time falls in ``[start, end)``. The base class takes care of the
    contract every consumer relies on:

    * columns are renamed according to ``field_mapping`` (raw -> feature name);
    * the event-time column is always returned as ``event_timestamp``
      (``datetime64[ns, UTC]``), the optional created-time column as
      ``created_timestamp``.

    To add a new backend (BigQuery, Snowflake, S3, Kafka snapshots, ...),
    subclass this (or :class:`~shalf.data.sources.sql.SQLDataSource` for
    anything DB-API compatible) and register it::

        @source_registry.register("bigquery")
        class BigQuerySource(DataSource):
            def _read(self, columns, start, end): ...
    """

    type_name: ClassVar[str] = "abstract"

    def __init__(
        self,
        *,
        name: str,
        timestamp_field: str,
        created_timestamp_field: str | None = None,
        timestamp_unit: str | None = None,
        field_mapping: Mapping[str, str] | None = None,
        description: str = "",
        tags: Mapping[str, str] | None = None,
    ) -> None:
        self.name = name
        self.timestamp_field = timestamp_field
        self.created_timestamp_field = created_timestamp_field
        self.timestamp_unit = timestamp_unit
        self.field_mapping = dict(field_mapping or {})
        self.description = description
        self.tags = dict(tags or {})

    def read(
        self,
        columns: Sequence[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Return rows with ``start <= event_timestamp < end``.

        ``columns`` are feature-side (post-mapping) names; timestamp columns are
        always included and need not be listed.
        """
        inverse = {v: k for k, v in self.field_mapping.items()}
        raw_columns = None
        if columns is not None:
            raw_columns = [inverse.get(c, c) for c in columns]
            for ts in (self.timestamp_field, self.created_timestamp_field):
                if ts and ts not in raw_columns:
                    raw_columns.append(ts)

        df = self._read(raw_columns, as_utc_datetime(start), as_utc_datetime(end))

        renames = dict(self.field_mapping)
        renames[self.timestamp_field] = EVENT_TIMESTAMP
        if self.created_timestamp_field:
            renames[self.created_timestamp_field] = CREATED_TIMESTAMP
        df = df.rename(columns=renames)
        df[EVENT_TIMESTAMP] = to_utc(df[EVENT_TIMESTAMP], self.timestamp_unit)
        if CREATED_TIMESTAMP in df:
            df[CREATED_TIMESTAMP] = to_utc(df[CREATED_TIMESTAMP], self.timestamp_unit)
        return df.reset_index(drop=True)

    @abstractmethod
    def _read(
        self,
        columns: list[str] | None,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        """Return raw rows (raw column names) with event time in ``[start, end)``."""

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type_name,
            "timestamp_field": self.timestamp_field,
            "created_timestamp_field": self.created_timestamp_field,
            "field_mapping": self.field_mapping,
            "description": self.description,
            "tags": self.tags,
        }

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


source_registry: PluginRegistry[DataSource] = PluginRegistry(
    "data source", DataSource, entry_point_group="shalf.data.sources"
)


def filter_time_range(
    df: pd.DataFrame,
    column: str,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    unit: str | None = None,
) -> pd.DataFrame:
    """Helper for sources that cannot push the time filter down to the backend."""
    if start is None and end is None:
        return df
    ts = to_utc(df[column], unit)
    mask = pd.Series(True, index=df.index)
    if start is not None:
        mask &= ts >= start
    if end is not None:
        mask &= ts < end
    return df[mask]
