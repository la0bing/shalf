import sqlite3
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from shalf.data import Entity, FeatureView, Field, SQLiteSource, ValueType

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _ts(hours: float) -> pd.Timestamp:
    return pd.Timestamp(T0 + timedelta(hours=hours))


@pytest.fixture()
def ts():
    """``ts(h)`` -> timestamp ``h`` hours after T0."""
    return _ts


@pytest.fixture()
def db_path(tmp_path):
    """customers: profile updates; orders: events. Times are hours after T0."""
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE profiles (customer_id INTEGER, tier TEXT, credit REAL, updated_at TEXT);
            CREATE TABLE orders (customer_id INTEGER, store_id INTEGER, amount REAL,
                                 created_at INTEGER);
            CREATE TABLE stores (store_id INTEGER, store_score REAL, updated_at TEXT);
            """
        )
        conn.executemany(
            "INSERT INTO profiles VALUES (?, ?, ?, ?)",
            [
                (1, "bronze", 100.0, _ts(0).isoformat()),
                (1, "gold", 500.0, _ts(10).isoformat()),
                (2, "silver", 200.0, _ts(5).isoformat()),
            ],
        )
        conn.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?)",
            [
                (1, 10, 10.0, int(_ts(1).timestamp())),
                (1, 20, 20.0, int(_ts(2).timestamp())),
                (2, 10, 5.0, int(_ts(3).timestamp())),
                (1, 10, 30.0, int(_ts(12).timestamp())),
            ],
        )
        conn.executemany(
            "INSERT INTO stores VALUES (?, ?, ?)",
            [
                (10, 0.1, _ts(0).isoformat()),
                (20, 0.9, _ts(0).isoformat()),
                (10, 0.5, _ts(11).isoformat()),
            ],
        )
    return path


@pytest.fixture()
def customer():
    return Entity(name="customer", join_key="customer_id")


@pytest.fixture()
def store_entity():
    return Entity(name="store", join_key="store_id")


@pytest.fixture()
def profiles(db_path, customer):
    return FeatureView(
        name="profiles",
        entities=[customer],
        source=SQLiteSource(
            name="profiles", path=db_path, table="profiles", timestamp_field="updated_at"
        ),
        schema=[Field("tier", ValueType.STRING), Field("credit", ValueType.FLOAT64)],
    )


@pytest.fixture()
def orders(db_path, customer):
    return FeatureView(
        name="orders",
        entities=[customer],
        source=SQLiteSource(
            name="orders",
            path=db_path,
            table="orders",
            timestamp_field="created_at",
            timestamp_unit="s",
        ),
        schema=[Field("amount", ValueType.FLOAT64), Field("store_id", ValueType.INT64)],
        online=False,
    )


@pytest.fixture()
def stores(db_path, store_entity):
    return FeatureView(
        name="stores",
        entities=[store_entity],
        source=SQLiteSource(
            name="stores", path=db_path, table="stores", timestamp_field="updated_at"
        ),
        schema=[Field("store_score", ValueType.FLOAT64)],
    )
