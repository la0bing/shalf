from __future__ import annotations

from abc import abstractmethod
from contextlib import closing
from typing import Any, ClassVar

import pandas as pd

from shalf.data.sources.base import DataSource


class SQLDataSource(DataSource):
    """Shared logic for any DB-API 2.0 database.

    A concrete SQL source only has to say how to open a connection and which
    parameter style the driver uses. Time filtering is pushed down into SQL.
    Override :meth:`timestamp_expression` / :meth:`timestamp_parameter` if a
    backend stores timestamps in an unusual way.
    """

    paramstyle: ClassVar[str] = "qmark"  # "qmark" (?) or "format" (%s)

    def __init__(
        self, *, table: str | None = None, query: str | None = None, **kwargs: Any
    ) -> None:
        if (table is None) == (query is None):
            raise ValueError("Specify exactly one of `table` or `query`")
        super().__init__(**kwargs)
        self.table = table
        self.query = query

    @abstractmethod
    def connect(self) -> Any:
        """Return a new DB-API connection."""

    @staticmethod
    def quote_identifier(name: str) -> str:
        return ".".join('"' + part.replace('"', '""') + '"' for part in name.split("."))

    def timestamp_expression(self, column: str) -> str:
        return self.quote_identifier(column)

    def timestamp_parameter(self, value: pd.Timestamp, bound: str) -> Any:
        """Driver parameter for a time bound; ``bound`` is "start" or "end"."""
        return value.to_pydatetime()

    def build_query(
        self, columns: list[str] | None, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> tuple[str, list[Any]]:
        placeholder = "?" if self.paramstyle == "qmark" else "%s"
        select = ", ".join(self.quote_identifier(c) for c in columns) if columns else "*"
        from_clause = self.quote_identifier(self.table) if self.table else f"({self.query}) AS src"
        sql = f"SELECT {select} FROM {from_clause}"

        conditions, params = [], []
        ts = self.timestamp_expression(self.timestamp_field)
        if start is not None:
            conditions.append(f"{ts} >= {placeholder}")
            params.append(self.timestamp_parameter(start, "start"))
        if end is not None:
            conditions.append(f"{ts} < {placeholder}")
            params.append(self.timestamp_parameter(end, "end"))
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        return sql, params

    def _read(
        self, columns: list[str] | None, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> pd.DataFrame:
        sql, params = self.build_query(columns, start, end)
        with closing(self.connect()) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                names = [d[0] for d in cursor.description]
            finally:
                cursor.close()
        return pd.DataFrame.from_records(rows, columns=names)

    def fingerprint(self) -> dict[str, Any]:
        return {**super().fingerprint(), "table": self.table, "query": self.query}

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "table": self.table, "query": self.query}
