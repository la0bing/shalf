from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

from shalf.data.sources.base import source_registry
from shalf.data.sources.sql import SQLDataSource


@source_registry.register("sqlite")
class SQLiteSource(SQLDataSource):
    """SQLite-backed source. Ideal for local development and tests.

    SQLite has no native timestamp type, so the time filter normalises both
    sides with ``strftime``. ISO-8601 text columns work out of the box; for
    integer epoch-seconds columns pass ``timestamp_unit="s"``.
    """

    type_name: ClassVar[str] = "sqlite"
    paramstyle: ClassVar[str] = "qmark"

    def __init__(self, *, path: str | Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.path = str(path)
        if self.timestamp_unit not in (None, "s"):
            raise ValueError(
                "SQLiteSource supports timestamp_unit=None (ISO text) or 's' (epoch seconds)"
            )

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def timestamp_expression(self, column: str) -> str:
        col = self.quote_identifier(column)
        if self.timestamp_unit == "s":
            return f"strftime('%Y-%m-%d %H:%M:%f', {col}, 'unixepoch')"
        return f"strftime('%Y-%m-%d %H:%M:%f', {col})"

    def timestamp_parameter(self, value: pd.Timestamp, bound: str) -> str:
        # Columns are compared at millisecond precision; round the exclusive
        # end bound up so rows just below it are not dropped.
        value = value.tz_convert("UTC")
        value = value.ceil("ms") if bound == "end" else value.floor("ms")
        return value.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "path": self.path}
