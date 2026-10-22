# Data layer design (`shalf-data`)

The data layer turns rows in operational databases into features that are

- **point-in-time correct offline**, for building training sets, and
- **low latency online**, for inference,

from a single set of definitions. Users can keep building new features on
top of existing ones.

## Concepts

| Concept                   | What it is                                                                       |
| ------------------------- | -------------------------------------------------------------------------------- |
| `DataSource`              | Where timestamped rows come from (SQLite, Postgres, CSV/Parquet, DataFrame, yours) |
| `Entity`                  | What features describe; has one join key (`customer_id`)                         |
| `FeatureView`             | Typed features read directly from a source, keyed by entities                    |
| `DerivedFeatureView`      | Batch features computed from other views; chains into a DAG                      |
| `OnDemandFeatureView`     | Features computed at retrieval time, optionally from request data                |
| `FeatureService`          | The named set of features one model consumes                                     |
| `FeatureRegistry`         | Validated catalogue of all of the above                                          |
| `OfflineStore`            | Computes historical features: point-in-time joins and derived views              |
| `OnlineStore`             | Latest value per entity, for low-latency reads (memory, SQLite, Redis, yours)     |
| `FeatureStore`            | Facade that ties everything together                                             |

```python
from datetime import timedelta
from shalf.data import Entity, FeatureView, Field, SQLiteSource, ValueType, derived_feature_view

customer = Entity(name="customer", join_key="customer_id")
txns = FeatureView(
    name="transactions",
    entities=[customer],
    ttl=timedelta(days=30),
    online=False,
    source=SQLiteSource(
        name="txns", path="app.db", table="transactions", timestamp_field="created_at"
    ),
    schema=[Field("amount", ValueType.FLOAT64), Field("merchant_id", ValueType.INT64)],
)


@derived_feature_view(
    sources=[txns], schema=[Field("txn_count_7d", ValueType.INT64)], lookback=timedelta(days=7)
)
def txn_stats(df): ...
```

[`examples/quickstart/feature_repo/features.py`](../examples/quickstart/feature_repo/features.py)
is a complete repo: three SQLite tables, a two-upstream derived view, a
derived-on-derived view, an on-demand view with request data, and a feature
service.

## Sources

`DataSource.read(columns, start, end)` is the only thing the rest of the
system calls. The base class guarantees:

- rows with `start <= event time < end`;
- `field_mapping` applied (raw column → feature name);
- the event-time column is always returned as `event_timestamp`
  (`datetime64[ns, UTC]`), and the optional created-time column as
  `created_timestamp`, which breaks ties between rows with the same event time.

Subclasses implement `_read()`. `SQLDataSource` covers any DB-API driver: it
takes a `table` *or* an arbitrary `query` (wrapped as a sub-query), pushes the
time filter into SQL, and needs only `connect()` and a `paramstyle`.
`SQLiteSource` and `PostgresSource` are about 30 lines each. Moving a feature
from SQLite to Postgres means swapping the source object; the views stay the same.

Base views cast every column to its declared `ValueType` (nullable pandas
dtypes), so types do not depend on the backend. SQLite's integer booleans come
back as `bool`, for example.

## The feature DAG

Derived and on-demand views name their `sources` either as objects or by
name (`"order_totals"`). On `apply`, the registry:

1. registers upstream views and entities referenced as objects;
2. resolves by-name references and topologically sorts the views, rejecting
   cycles and unknown names;
3. lets derived views inherit `entities` and `ttl` from their primary upstream
   unless they set them explicitly;
4. validates joinability and name collisions (see below).

### Derived views (batch)

The first source is the **primary** upstream. Its rows (keys +
`event_timestamp` + features) form the *spine*. Every other upstream is
joined onto the spine point-in-time correctly **using its own join keys**,
which must be spine columns. That is how merchant features attach to
transactions through the transaction's `merchant_id`. The transformation
receives the spine and returns the derived features:

- return one row per input row, **or**
- return the join keys and `event_timestamp` yourself, and you may change the
  number of rows (aggregations, rolling windows).

A derived view's output behaves exactly like a source, so it can be joined,
derived from again, and materialised.

`lookback` bounds how much upstream history is read for a window
`[start, end)`. Without it the full history is read: always correct, but
slower. `test_incremental_materialisation_with_lookback_matches_full` checks
that incremental materialisation with a lookback matches a full rebuild.

### On-demand views

These are computed after the other features have been fetched, from those
features plus `request_schema` fields (for example, the amount of the
transaction being scored). They are never materialised. The function runs
over the training frame offline and over the request rows online. Online it
sees `event_timestamp = now`.

Transformations are pluggable engines (`transformation_registry`):
`pandas` (vectorised, `df -> df`) and `python` (per-row, `dict -> dict`) are
built in.

## Offline retrieval semantics

`get_historical_features(entity_df, features | feature_service)`:

- `entity_df` holds entity keys, `event_timestamp` (renameable via
  `timestamp_column`) and any request columns or labels;
- for each row and view, the result takes the latest view row with the same
  keys and `event_timestamp <= row time`, and only if it is newer than
  `row time - ttl`;
- rows keep their order; missing values are null;
- `full_feature_names=True` names columns `view__feature`. Without it,
  requesting the same feature name from two views is an error, not a silent
  overwrite.

The built-in `PandasOfflineStore` reads each source once per request and joins
with `pandas.merge_asof`.

## Materialisation and online retrieval

`materialize(start, end)` writes the latest row per entity in `[start, end)`
for every view with `online=True`, derived views included, and records a
per-view **watermark** in the online store. `materialize_incremental()` resumes
from that watermark. For a first run it starts from `end - ttl`.

Every online store follows the same contract: one record per
`(project, view, entity key)`, and **a newer event timestamp always wins**, so
replaying an old window never regresses values. Redis enforces this with a
Lua compare-and-set, SQLite with a conditional upsert. Redis keys also expire
at `event_timestamp + ttl`.

`get_online_features(entity_rows, ..., request_data=...)`:

- coerces join-key values to the entity's `value_type`, so `"42"` from JSON
  finds `42`;
- returns null for unknown entities and for values older than the view's ttl;
- runs on-demand transformations with the same code as offline.

`test_quickstart.py` asserts that offline and online return the same values
for the same entities and time.

## Configuration

```yaml
# feature_repo/shalf.yaml
project: quickstart
definitions: [entities.py, features.py]   # files or directories
offline_store: {type: pandas}
online_store:
  type: redis
  url: ${SHALF_REDIS_URL}
```

Relative `path`s resolve against the repo. `$SHALF_CONFIG` replaces the file
entirely, which is how the Kubernetes ConfigMap switches the online store to
Redis.

## Extending

All four extension points work the same way:

| Extension point       | Base class          | Registry                    | Entry-point group               |
| --------------------- | ------------------- | --------------------------- | ------------------------------- |
| Data source           | `DataSource` / `SQLDataSource` | `source_registry`   | `shalf.data.sources`            |
| Online store          | `OnlineStore`       | `online_store_registry`     | `shalf.data.online_stores`      |
| Offline store         | `OfflineStore`      | `offline_store_registry`    | `shalf.data.offline_stores`     |
| Transformation engine | `Transformation`    | `transformation_registry`   | `shalf.data.transformations`    |

Example: a new SQL warehouse needs a connection, a parameter style and the
registration.

```python
from shalf.data import SQLDataSource, source_registry


@source_registry.register("mysql")
class MySQLSource(SQLDataSource):
    paramstyle = "format"

    def __init__(self, *, url: str, **kwargs):
        super().__init__(**kwargs)
        self.url = url

    def connect(self):
        import pymysql

        return pymysql.connect(...)
```

For a non-SQL backend, subclass `DataSource` and implement
`_read(columns, start, end)`. `filter_time_range()` helps when the backend
can't filter by time itself. To ship the plugin as its own package:

```toml
[project.entry-points."shalf.data.sources"]
mysql = "shalf_mysql:MySQLSource"
```

after which `type: mysql` works in config with no imports.
`tests/test_extensibility.py` plugs in a custom source, online store and
transformation engine end to end.

## CLI

```bash
shalf-data --repo PATH apply | list [entities|views|services]
shalf-data --repo PATH materialize --start ... --end ... [--views ...]
shalf-data --repo PATH materialize-incremental
shalf-data --repo PATH online --feature-service fraud_model_v1 --entities '{"customer_id":[1]}'
shalf-data --repo PATH historical --entity-csv spine.csv --feature-service fraud_model_v1 --out train.csv
```

## Known limitations / next steps

- **Scale of the offline store.** `PandasOfflineStore` works in memory. Next: an
  offline store that pushes the point-in-time join down to the warehouse as
  SQL (`ASOF JOIN` / window functions), and a Spark/Ray one.
- **Rolling windows are event driven.** A 7-day count is as of the entity's
  last event. It does not decay without new events, except through the
  view's `ttl`.
- **Online value encoding** is JSON. Timestamps come back as ISO strings.
  A typed codec (msgpack/Arrow) is a natural extension point.
- **The registry is code-first and in memory**, rebuilt in each process. A
  persisted registry (for UI/lineage and change review) can sit behind the
  same `FeatureRegistry` API.
- **Postgres** shares the SQL code path that is tested on SQLite, but the
  query builder is only unit-tested here. Add a Postgres service container
  in CI for an integration test.
- **Streaming / push ingestion** (Kafka → online store) and data-quality
  validation hooks are not implemented yet.
