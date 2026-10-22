from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import Any

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
    namespace   TEXT    NOT NULL,
    entity_key  TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    event_ts    INTEGER NOT NULL,
    PRIMARY KEY (project, namespace, entity_key)
);
CREATE TABLE IF NOT EXISTS online_metadata (
    project     TEXT    NOT NULL,
    key         TEXT    NOT NULL,
    value       TEXT    NOT NULL,
    PRIMARY KEY (project, key)
);
"""

_UPSERT = """
INSERT INTO online_features (project, namespace, entity_key, payload, event_ts)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (project, namespace, entity_key) DO UPDATE
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
            conn.execute("DELETE FROM online_metadata WHERE project = ?", (self.project,))

    def write_records(
        self, namespace: str, records: Sequence[OnlineRecord], ttl: timedelta | None = None
    ) -> int:
        rows = [
            (
                self.project,
                namespace,
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

    def read_records(self, namespace: str, entity_keys: Sequence[str]) -> list[OnlineRecord | None]:
        found: dict[str, OnlineRecord] = {}
        unique = list(dict.fromkeys(entity_keys))
        with closing(self._connect()) as conn:
            for i in range(0, len(unique), _CHUNK):
                chunk = unique[i : i + _CHUNK]
                placeholders = ", ".join("?" for _ in chunk)
                cursor = conn.execute(
                    "SELECT entity_key, payload, event_ts FROM online_features "
                    f"WHERE project = ? AND namespace = ? AND entity_key IN ({placeholders})",
                    (self.project, namespace, *chunk),
                )
                for key, payload, ts in cursor:
                    found[key] = OnlineRecord(key, decode_values(payload), from_micros(ts))
        return [found.get(key) for key in entity_keys]

    def get_metadata(self, key: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT value FROM online_metadata WHERE project = ? AND key = ?",
                (self.project, key),
            ).fetchone()
        return row[0] if row else None

    def set_metadata(self, key: str, value: str) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO online_metadata (project, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT (project, key) DO UPDATE SET value = excluded.value",
                (self.project, key, value),
            )
