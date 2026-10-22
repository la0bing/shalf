from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any

from shalf.data.feature_view import BaseFeatureView
from shalf.data.online.base import OnlineRecord, OnlineStore, online_store_registry


@online_store_registry.register("memory")
class InMemoryOnlineStore(OnlineStore):
    """Process-local dict. For tests and notebooks only - not shared between replicas."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._data: dict[tuple[str, str], OnlineRecord] = {}
        self._lock = threading.Lock()

    def write_records(self, view: BaseFeatureView, records: Sequence[OnlineRecord]) -> int:
        written = 0
        with self._lock:
            for record in records:
                key = (view.name, record.entity_key)
                current = self._data.get(key)
                if current is None or current.event_timestamp <= record.event_timestamp:
                    self._data[key] = record
                    written += 1
        return written

    def read_records(
        self, view: BaseFeatureView, entity_keys: Sequence[str]
    ) -> list[OnlineRecord | None]:
        with self._lock:
            return [self._data.get((view.name, key)) for key in entity_keys]

    def teardown(self) -> None:
        with self._lock:
            self._data.clear()
            self._watermarks.clear()
