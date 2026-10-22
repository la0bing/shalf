from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pandas as pd

from shalf.data.sources.base import DataSource, filter_time_range, source_registry


@source_registry.register("file")
class FileSource(DataSource):
    """CSV or Parquet file(s) on local disk (or any fsspec URL pandas understands)."""

    type_name: ClassVar[str] = "file"

    def __init__(self, *, path: str | Path, format: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.path = str(path)
        self.format = format or Path(self.path).suffix.lstrip(".").lower()
        if self.format not in {"csv", "parquet"}:
            raise ValueError(f"Unsupported file format {self.format!r}; expected csv or parquet")

    def _read(
        self, columns: list[str] | None, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> pd.DataFrame:
        if self.format == "csv":
            df = pd.read_csv(self.path, usecols=columns)
        else:
            df = pd.read_parquet(self.path, columns=columns)
        return filter_time_range(df, self.timestamp_field, start, end, self.timestamp_unit)

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "path": self.path, "format": self.format}


@source_registry.register("dataframe")
class DataFrameSource(DataSource):
    """An in-memory DataFrame. Handy in notebooks and unit tests."""

    type_name: ClassVar[str] = "dataframe"

    def __init__(self, *, df: pd.DataFrame, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.df = df

    def _read(
        self, columns: list[str] | None, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> pd.DataFrame:
        df = self.df if columns is None else self.df[columns]
        return filter_time_range(df, self.timestamp_field, start, end, self.timestamp_unit).copy()
