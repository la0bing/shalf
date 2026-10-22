"""Parquet cache of computed feature-view frames, keyed by view *version*.

Layout::

    <path>/<view>/<version>/date=YYYY-MM-DD.parquet
    <path>/<view>/<version>/_coverage.json      # [[start|null, end], ...]

Materialisation and backfills write every row they compute here, so:

* training sets and EDA read precomputed features instead of recomputing
  them or querying the source databases (``cache_only`` makes that strict);
* a logic change produces a new version directory, and old versions stay
  readable for reproducing past training sets.

Files are written to a temp name and atomically renamed, so concurrent readers
never see a partial file. DuckDB does the Parquet I/O.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import duckdb
import pandas as pd

from shalf.data.types import EVENT_TIMESTAMP, to_utc

Interval = tuple[pd.Timestamp | None, pd.Timestamp]


class ParquetFeatureCache:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _dir(self, view: str, version: str) -> Path:
        return self.path / view / version

    # -- coverage ----------------------------------------------------------------
    def coverage(self, view: str, version: str) -> list[Interval]:
        file = self._dir(view, version) / "_coverage.json"
        if not file.exists():
            return []
        raw = json.loads(file.read_text())
        return [(pd.Timestamp(s) if s else None, pd.Timestamp(e)) for s, e in raw]

    def latest_interval(self, view: str, version: str) -> Interval | None:
        """The most recent contiguous cached range, if any."""
        intervals = self.coverage(view, version)
        return max(intervals, key=lambda i: i[1]) if intervals else None

    def covers(
        self, view: str, version: str, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> bool:
        if end is None:
            return False
        for c_start, c_end in self.coverage(view, version):
            if (c_start is None or (start is not None and c_start <= start)) and end <= c_end:
                return True
        return False

    def _add_coverage(
        self, view: str, version: str, start: pd.Timestamp | None, end: pd.Timestamp
    ) -> None:
        intervals = [*self.coverage(view, version), (start, end)]
        intervals.sort(
            key=lambda i: (i[0] is not None, i[0] or pd.Timestamp.min.tz_localize("UTC"))
        )
        merged: list[Interval] = []
        for s, e in intervals:
            if merged and (s is None or merged[-1][1] >= s):
                prev_s, prev_e = merged[-1]
                merged[-1] = (
                    prev_s if prev_s is None or s is None else min(prev_s, s),
                    max(prev_e, e),
                )
            else:
                merged.append((s, e))
        payload = [[s.isoformat() if s is not None else None, e.isoformat()] for s, e in merged]
        _atomic_write_text(self._dir(view, version) / "_coverage.json", json.dumps(payload))

    # -- data --------------------------------------------------------------------
    def write(
        self,
        view: str,
        version: str,
        df: pd.DataFrame,
        start: pd.Timestamp | None,
        end: pd.Timestamp,
    ) -> None:
        """Replace the cached rows with event time in ``[start, end)`` by ``df``."""
        directory = self._dir(view, version)
        directory.mkdir(parents=True, exist_ok=True)
        df = df.copy()
        df[EVENT_TIMESTAMP] = to_utc(df[EVENT_TIMESTAMP])
        days = set(df[EVENT_TIMESTAMP].dt.strftime("%Y-%m-%d"))
        for file in directory.glob("date=*.parquet"):
            day = file.stem.removeprefix("date=")
            day_start = pd.Timestamp(day, tz="UTC")
            if (start is None or day_start + pd.Timedelta(days=1) > start) and day_start < end:
                days.add(day)  # existing day overlapping the window: rewrite it

        with duckdb.connect() as con:
            for day in sorted(days):
                file = directory / f"date={day}.parquet"
                new = df[df[EVENT_TIMESTAMP].dt.strftime("%Y-%m-%d") == day]
                if file.exists():
                    old = self._read_files(con, [file])
                    in_window = old[EVENT_TIMESTAMP] < end
                    if start is not None:
                        in_window &= old[EVENT_TIMESTAMP] >= start
                    new = pd.concat([old[~in_window], new], ignore_index=True)
                if new.empty:
                    file.unlink(missing_ok=True)
                    continue
                _write_parquet(con, new, file)
        self._add_coverage(view, version, start, end)

    def read(
        self, view: str, version: str, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> pd.DataFrame:
        files = sorted(self._dir(view, version).glob("date=*.parquet"))
        if not files:
            return pd.DataFrame()
        with duckdb.connect() as con:
            df = self._read_files(con, files)
        mask = pd.Series(True, index=df.index)
        if start is not None:
            mask &= df[EVENT_TIMESTAMP] >= start
        if end is not None:
            mask &= df[EVENT_TIMESTAMP] < end
        return df[mask].reset_index(drop=True)

    def versions(self, view: str) -> list[str]:
        directory = self.path / view
        return (
            sorted(p.name for p in directory.iterdir() if p.is_dir()) if directory.exists() else []
        )

    @staticmethod
    def _read_files(con: duckdb.DuckDBPyConnection, files: list[Path]) -> pd.DataFrame:
        df = con.execute("SELECT * FROM read_parquet(?)", [[str(f) for f in files]]).df()
        for column in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[column]):
                df[column] = to_utc(
                    df[column].dt.tz_localize("UTC") if df[column].dt.tz is None else df[column]
                )
        return df


def _write_parquet(con: duckdb.DuckDBPyConnection, df: pd.DataFrame, file: Path) -> None:
    frame = df.copy()
    for column in frame.columns:
        if isinstance(frame[column].dtype, pd.DatetimeTZDtype):
            frame[column] = frame[column].dt.tz_convert("UTC").dt.tz_localize(None)
    tmp = file.with_name(f".{file.name}.{uuid.uuid4().hex}.tmp")
    con.register("frame", frame)
    target = str(tmp).replace("'", "''")
    con.execute(f"COPY frame TO '{target}' (FORMAT parquet)")
    con.unregister("frame")
    os.replace(tmp, file)


def _atomic_write_text(file: Path, text: str) -> None:
    tmp = file.with_name(f".{file.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(text)
    os.replace(tmp, file)
