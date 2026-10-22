import pandas as pd
import pytest

from shalf.data import (
    EVENT_TIMESTAMP,
    DataFrameSource,
    FileSource,
    PostgresSource,
    SQLiteSource,
    source_registry,
)


def test_sqlite_table_time_filter_and_timestamp_normalisation(db_path, ts):
    source = SQLiteSource(name="p", path=db_path, table="profiles", timestamp_field="updated_at")
    df = source.read(columns=["customer_id", "tier"], start=ts(0), end=ts(10))
    assert list(df.columns) == ["customer_id", "tier", EVENT_TIMESTAMP]
    assert df["tier"].tolist() == ["bronze", "silver"]  # end is exclusive
    assert str(df[EVENT_TIMESTAMP].dtype) == "datetime64[ns, UTC]"


def test_sqlite_epoch_seconds_query_and_field_mapping(db_path, ts):
    source = SQLiteSource(
        name="o",
        path=db_path,
        query="SELECT customer_id, amount AS amt, created_at FROM orders WHERE amount > 6",
        timestamp_field="created_at",
        timestamp_unit="s",
        field_mapping={"amt": "order_amount"},
    )
    df = source.read(columns=["customer_id", "order_amount"], start=ts(1.5))
    assert df["order_amount"].tolist() == [20.0, 30.0]
    assert df[EVENT_TIMESTAMP].tolist() == [ts(2), ts(12)]


def test_sql_query_building_for_postgres(ts):
    source = PostgresSource(
        name="pg",
        dsn="postgresql://u:secret@h/db",
        table="analytics.orders",
        timestamp_field="created_at",
    )
    sql, params = source.build_query(["customer_id", "amount"], ts(0), ts(1))
    assert sql == (
        'SELECT "customer_id", "amount" FROM "analytics"."orders" '
        'WHERE "created_at" >= %s AND "created_at" < %s'
    )
    assert params == [ts(0).to_pydatetime(), ts(1).to_pydatetime()]
    assert "secret" not in str(source.describe())


def test_table_xor_query():
    with pytest.raises(ValueError):
        SQLiteSource(name="x", path="x.db", timestamp_field="t")


def test_file_and_dataframe_sources(tmp_path, ts):
    df = pd.DataFrame({"id": [1, 2], "v": [1.0, 2.0], "t": [ts(0).isoformat(), ts(5).isoformat()]})
    path = tmp_path / "data.csv"
    df.to_csv(path, index=False)
    assert FileSource(name="f", path=path, timestamp_field="t").read(start=ts(1))[
        "id"
    ].tolist() == [2]
    assert DataFrameSource(name="d", df=df, timestamp_field="t").read(end=ts(1))["id"].tolist() == [
        1
    ]


def test_sources_can_be_built_from_config(db_path):
    source = source_registry.create(
        {
            "type": "sqlite",
            "name": "p",
            "path": str(db_path),
            "table": "profiles",
            "timestamp_field": "updated_at",
        }
    )
    assert isinstance(source, SQLiteSource)
    assert len(source.read()) == 3
