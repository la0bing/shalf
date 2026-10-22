from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any, ClassVar

import duckdb
import pandas as pd

from shalf.data.sources.base import source_registry
from shalf.data.sources.sql import SQLDataSource


@source_registry.register("duckdb")
class DuckDBSource(SQLDataSource):
    """Parquet/CSV files (globs allowed) or any DuckDB query.

    ``path="warehouse/fct_orders.parquet"`` reads files with projection and the
    time filter pushed into DuckDB. ``query=`` runs any DuckDB SQL (which can
    itself read files, join them, or scan an attached database). ``database``
    optionally opens a DuckDB database file read-only.
    """

    type_name: ClassVar[str] = "duckdb"
    paramstyle: ClassVar[str] = "qmark"

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        query: str | None = None,
        database: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        if (path is None) == (query is None):
            raise ValueError("Specify exactly one of `path` or `query`")
        self.path = str(path) if path is not None else None
        self.database = str(database) if database is not None else None
        super().__init__(query=query or "", **kwargs)

    def file_reader(self) -> str:
        assert self.path is not None
        path = self.path.replace("'", "''")
        if self.path.endswith(".csv"):
            return f"read_csv_auto('{path}')"
        return f"read_parquet('{path}')"

    def build_query(
        self, columns: list[str] | None, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> tuple[str, list[Any]]:
        if self.path is not None:
            self.query = f"SELECT * FROM {self.file_reader()}"
        return super().build_query(columns, start, end)

    def connect(self) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect(self.database or ":memory:", read_only=self.database is not None)
        con.execute("SET TimeZone = 'UTC'")
        return con

    def _read(
        self, columns: list[str] | None, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> pd.DataFrame:
        sql, params = self.build_query(columns, start, end)
        with closing(self.connect()) as con:
            return con.execute(sql, params).df()

    def fingerprint(self) -> dict[str, Any]:
        # The file location is *where*, not *what*: leave it out like DSNs.
        base = super().fingerprint()
        if self.path is not None:
            base["query"] = Path(self.path).suffix
        return base

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "path": self.path, "database": self.database}
