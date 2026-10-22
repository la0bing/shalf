from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
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

    Records live in a *namespace* per ``(view, version)``. A new version of a
    view's logic is materialised next to the old one, and readers follow the
    view's *active version* pointer, so a backfill never mixes old and new
    values and the switch-over is one metadata write.

    Contract shared by every implementation:

    * one record per (project, namespace, entity key);
    * a write only replaces a record whose ``event_timestamp`` is not newer
      (so replaying an old materialisation window never regresses values);
    * reads return ``None`` for unknown entities.

    Implement :meth:`write_records`, :meth:`read_records` and
    :meth:`get_metadata` / :meth:`set_metadata` (the defaults keep metadata
    in process memory), then register the class to add a backend (DynamoDB,
    Bigtable, Cassandra, ...).

    ``read_only=True`` refuses every write. Use it for exploration
    deployments that point at a replica.
    """

    def __init__(self, *, project: str = "default", read_only: bool = False) -> None:
        self.project = project
        self.read_only = read_only
        self._metadata: dict[str, str] = {}

    # -- backend hooks -----------------------------------------------------------
    def setup(self, views: Sequence[BaseFeatureView]) -> None:  # noqa: B027 - optional hook
        """Create tables/indexes for the given views. Must be idempotent."""

    def teardown(self) -> None:  # noqa: B027 - optional hook
        """Drop everything this store created for the project."""

    def ping(self) -> None:  # noqa: B027 - optional hook
        """Raise if the backend is unreachable. Backs the servers' readiness probes."""

    @abstractmethod
    def write_records(
        self, namespace: str, records: Sequence[OnlineRecord], ttl: timedelta | None = None
    ) -> int:
        """Upsert records; return how many were written. ``ttl`` may be used for expiry."""

    @abstractmethod
    def read_records(self, namespace: str, entity_keys: Sequence[str]) -> list[OnlineRecord | None]:
        """Return one record (or ``None``) per key, in order."""

    def get_metadata(self, key: str) -> str | None:
        return self._metadata.get(key)

    def set_metadata(self, key: str, value: str) -> None:
        self._metadata[key] = value

    # -- API used by the FeatureStore -------------------------------------------
    @staticmethod
    def namespace(view_name: str, version: str) -> str:
        return f"{view_name}@{version}"

    def write_frame(self, view: BaseFeatureView, df: pd.DataFrame, version: str) -> int:
        self._check_writable()
        records = frame_to_records(view, df)
        return self.write_records(self.namespace(view.name, version), records, view.ttl)

    def read(
        self, view: BaseFeatureView, entity_keys: Sequence[str], version: str
    ) -> list[OnlineRecord | None]:
        return self.read_records(self.namespace(view.name, version), entity_keys)

    def get_watermark(self, view_name: str, version: str) -> pd.Timestamp | None:
        value = self.get_metadata(f"watermark:{self.namespace(view_name, version)}")
        return from_micros(value) if value is not None else None

    def set_watermark(self, view_name: str, version: str, value: pd.Timestamp) -> None:
        self._check_writable()
        self.set_metadata(f"watermark:{self.namespace(view_name, version)}", str(to_micros(value)))

    def get_active_version(self, view_name: str) -> str | None:
        return self.get_metadata(f"active:{view_name}")

    def set_active_version(self, view_name: str, version: str) -> None:
        self._check_writable()
        self.set_metadata(f"active:{view_name}", version)

    def _check_writable(self) -> None:
        if self.read_only:
            raise PermissionError(f"{type(self).__name__} is configured read_only")


online_store_registry: PluginRegistry[OnlineStore] = PluginRegistry(
    "online store", OnlineStore, entry_point_group="shalf.data.online_stores"
)
