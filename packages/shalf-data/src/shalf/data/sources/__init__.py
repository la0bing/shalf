"""Pluggable data sources. Import side effect: built-in types are registered."""

from shalf.data.sources.base import DataSource, filter_time_range, source_registry
from shalf.data.sources.dbt import DbtModelSource, configure_dbt
from shalf.data.sources.duckdb import DuckDBSource
from shalf.data.sources.file import DataFrameSource, FileSource
from shalf.data.sources.postgres import PostgresSource
from shalf.data.sources.sql import SQLDataSource
from shalf.data.sources.sqlite import SQLiteSource

__all__ = [
    "DataFrameSource",
    "DataSource",
    "DbtModelSource",
    "DuckDBSource",
    "FileSource",
    "PostgresSource",
    "SQLDataSource",
    "SQLiteSource",
    "configure_dbt",
    "filter_time_range",
    "source_registry",
]
