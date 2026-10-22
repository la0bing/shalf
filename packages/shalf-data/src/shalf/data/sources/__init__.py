"""Pluggable data sources. Import side effect: built-in types are registered."""

from shalf.data.sources.base import DataSource, filter_time_range, source_registry
from shalf.data.sources.file import DataFrameSource, FileSource
from shalf.data.sources.postgres import PostgresSource
from shalf.data.sources.sql import SQLDataSource
from shalf.data.sources.sqlite import SQLiteSource

__all__ = [
    "DataFrameSource",
    "DataSource",
    "FileSource",
    "PostgresSource",
    "SQLDataSource",
    "SQLiteSource",
    "filter_time_range",
    "source_registry",
]
