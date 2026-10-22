from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Any

import pandas as pd

from shalf.data.feature_view import BaseFeatureView
from shalf.data.online.base import (
    OnlineRecord,
    OnlineStore,
    decode_values,
    encode_values,
    from_micros,
    online_store_registry,
    to_micros,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS online_features (
    project     TEXT    NOT NULL,
    view        TEXT    NOT NULL,
    entity_key  TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    event_ts    INTEGER NOT NULL,
    PRIMARY KEY (project, view, entity_key)
);
CREATE TABLE IF NOT EXISTS online_watermarks (
    project     TEXT    NOT NULL,
    view        TEXT    NOT NULL,
    watermark   INTEGER NOT NULL,
    PRIMARY KEY (project, view)
);
"""

_UPSERT = """
INSERT INTO online_features (project, view, entity_key, payload, event_ts)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (project, view, entity_key) DO UPDATE
SET payload = excluded.payload, event_ts = excluded.event_ts
WHERE excluded.event_ts >= online_features.event_ts
"""

_CHUNK = 500


@online_store_registry.register("sqlite")
class SQLiteOnlineStore(OnlineStore):
    """A single SQLite file. Good for local development and single-replica demos."""

    def __init__(self, *, path: str | Path = "online_store.db", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.path = str(path)
        self._initialised = False

    def _connect(self) -> sqlite3.Connection:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        if not self._initialised:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            self._initialised = True
        return conn

    def ping(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("SELECT 1")

    def setup(self, views: Sequence[BaseFeatureView]) -> None:
        with closing(self._connect()):
            pass

    def teardown(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM online_features WHERE project = ?", (self.project,))
            conn.execute("DELETE FROM online_watermarks WHERE project = ?", (self.project,))

    def write_records(self, view: BaseFeatureView, records: Sequence[OnlineRecord]) -> int:
        rows = [
            (
                self.project,
                view.name,
                r.entity_key,
                encode_values(r.values),
                to_micros(r.event_timestamp),
            )
            for r in records
        ]
        with closing(self._connect()) as conn, conn:
            before = conn.total_changes
            conn.executemany(_UPSERT, rows)
            return conn.total_changes - before

    def read_records(
        self, view: BaseFeatureView, entity_keys: Sequence[str]
    ) -> list[OnlineRecord | None]:
        found: dict[str, OnlineRecord] = {}
        unique = list(dict.fromkeys(entity_keys))
        with closing(self._connect()) as conn:
            for i in range(0, len(unique), _CHUNK):
                chunk = unique[i : i + _CHUNK]
                placeholders = ", ".join("?" for _ in chunk)
                cursor = conn.execute(
                    "SELECT entity_key, payload, event_ts FROM online_features "
                    f"WHERE project = ? AND view = ? AND entity_key IN ({placeholders})",
                    (self.project, view.name, *chunk),
                )
                for key, payload, ts in cursor:
                    found[key] = OnlineRecord(key, decode_values(payload), from_micros(ts))
        return [found.get(key) for key in entity_keys]

    def get_watermark(self, view_name: str) -> pd.Timestamp | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT watermark FROM online_watermarks WHERE project = ? AND view = ?",
                (self.project, view_name),
            ).fetchone()
        return from_micros(row[0]) if row else None

    def set_watermark(self, view_name: str, value: pd.Timestamp) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO online_watermarks (project, view, watermark) VALUES (?, ?, ?) "
                "ON CONFLICT (project, view) DO UPDATE SET watermark = excluded.watermark",
                (self.project, view_name, to_micros(value)),
            )
