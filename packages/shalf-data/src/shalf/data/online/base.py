from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd

from shalf.core import PluginRegistry
from shalf.data.feature_view import BaseFeatureView
from shalf.data.types import EVENT_TIMESTAMP, as_utc_datetime, to_python


@dataclass
class OnlineRecord:
    """The latest feature values of one entity in one view."""

    entity_key: str
    values: dict[str, Any]
    event_timestamp: pd.Timestamp


def serialize_entity_key(key_values: Mapping[str, Any]) -> str:
    """Stable, backend-agnostic string form of a (possibly composite) entity key."""
    return json.dumps(
        sorted((k, to_python(v)) for k, v in key_values.items()), separators=(",", ":")
    )


def encode_values(values: Mapping[str, Any]) -> str:
    return json.dumps({k: to_python(v) for k, v in values.items()}, separators=(",", ":"))


def decode_values(payload: str | bytes) -> dict[str, Any]:
    return json.loads(payload)


def to_micros(ts: pd.Timestamp) -> int:
    return int(as_utc_datetime(ts).value // 1_000)


def from_micros(value: int | str | bytes) -> pd.Timestamp:
    return pd.Timestamp(int(value), unit="us", tz="UTC")


def frame_to_records(view: BaseFeatureView, df: pd.DataFrame) -> list[OnlineRecord]:
    keys, features = view.join_keys, view.feature_names
    records = []
    for row in df[[*keys, EVENT_TIMESTAMP, *features]].itertuples(index=False, name=None):
        key_values = dict(zip(keys, row[: len(keys)], strict=True))
        values = dict(zip(features, row[len(keys) + 1 :], strict=True))
        records.append(OnlineRecord(serialize_entity_key(key_values), values, row[len(keys)]))
    return records


class OnlineStore(ABC):
    """Low-latency key/value storage of the latest feature values per entity.

    Contract shared by every implementation:

    * one record per (project, view, entity key);
    * a write only replaces a record whose ``event_timestamp`` is not newer
      (so replaying an old materialisation window never regresses values);
    * reads return ``None`` for unknown entities.

    Implement :meth:`write_records` and :meth:`read_records` (plus
    :meth:`get_watermark`/:meth:`set_watermark` to persist incremental
    materialisation state) and register the class to add a backend
    (DynamoDB, Bigtable, Cassandra, ...).
    """

    def __init__(self, *, project: str = "default") -> None:
        self.project = project
        self._watermarks: dict[str, pd.Timestamp] = {}

    def setup(self, views: Sequence[BaseFeatureView]) -> None:  # noqa: B027 - optional hook
        """Create tables/indexes for the given views. Must be idempotent."""

    def teardown(self) -> None:  # noqa: B027 - optional hook
        """Drop everything this store created for the project."""

    def ping(self) -> None:  # noqa: B027 - optional hook
        """Raise if the backend is unreachable. Backs the servers' readiness probes."""

    @abstractmethod
    def write_records(self, view: BaseFeatureView, records: Sequence[OnlineRecord]) -> int:
        """Upsert records; return how many were written."""

    @abstractmethod
    def read_records(
        self, view: BaseFeatureView, entity_keys: Sequence[str]
    ) -> list[OnlineRecord | None]:
        """Return one record (or ``None``) per key, in order."""

    def write_frame(self, view: BaseFeatureView, df: pd.DataFrame) -> int:
        return self.write_records(view, frame_to_records(view, df))

    def get_watermark(self, view_name: str) -> pd.Timestamp | None:
        return self._watermarks.get(view_name)

    def set_watermark(self, view_name: str, value: pd.Timestamp) -> None:
        self._watermarks[view_name] = value


online_store_registry: PluginRegistry[OnlineStore] = PluginRegistry(
    "online store", OnlineStore, entry_point_group="shalf.data.online_stores"
)
