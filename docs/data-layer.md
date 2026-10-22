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
| `AggregationFeatureView`  | Windowed aggregates declared with `Aggregate(...)`, computed by DuckDB           |
| `DerivedFeatureView`      | Batch features computed from other views by your code; chains into a DAG         |
| `OnDemandFeatureView`     | Features computed at retrieval time, optionally from request data                |
| `FeatureService`          | The named set of features one model consumes                                     |
| `FeatureRegistry`         | Validated catalogue of all of the above                                          |
| `OfflineStore`            | Computes historical features: point-in-time joins and derived views              |
| `OnlineStore`             | Latest value per entity, for low-latency reads (memory, SQLite, Redis, yours)     |
| `FeatureStore`            | Facade that ties everything together                                             |

## Writing features

The API is built around what data scientists usually write: typed columns
from a table, then "function of column over the last N days per entity",
then a bit of custom pandas.

```python
from shalf.data import Aggregate, AggregationFeatureView, Entity, FeatureView, SQLiteSource
from shalf.data import derived_feature_view

customer = Entity(name="customer", join_key="customer_id")

transactions = FeatureView(
    name="transactions",
    entities=[customer],
    online=False,
    ttl="30d",
    source=SQLiteSource(
        name="txns", path="app.db", table="transactions", timestamp_field="created_at"
    ),
    schema={"amount": float, "merchant_id": int},  # plain Python types
)

txn_stats = AggregationFeatureView(  # no rolling-window code
    name="txn_stats",
    source=transactions,
    aggregations=[
        Aggregate("amount", "sum", "7d"),  # -> amount_sum_7d
        Aggregate("amount", "mean", "30d"),  # -> amount_mean_30d
        Aggregate(None, "count", "1d"),  # -> count_1d
        Aggregate("amount", "sum", "7d", where="amount > 100", name="big_spend_7d"),
    ],
)


@derived_feature_view(sources=[txn_stats], schema={"avg_big_share": float})
def big_share(df):  # escape hatch: any pandas
    return df.assign(avg_big_share=df.big_spend_7d / df.amount_sum_7d)
```

Conveniences:

- `schema` accepts `{"name": type}` (`int`, `float`, `str`, `bool`,
  `datetime`), a list of names (float), or `Field` objects for descriptions/tags.
- Durations accept `"30m"`, `"12h"`, `"7d"`, `"2w"` or `timedelta`.
- An `AggregationFeatureView` inherits entities from its source, and its
  `ttl` / `lookback` default to the longest window, so incremental
  materialisation reads only the history it needs.
- Window semantics are `(t - window, t]`. Supported functions are `count`,
  `sum`, `mean`, `min`, `max` and `std`. `where` is a SQL filter over any
  input column, including columns of views joined in as extra sources.
- `store.preview("txn_stats")` shows computed rows. `shalf-data plan` shows
  what a change to the code would trigger (see [Changing feature logic](#changing-feature-logic-backfills)).

[`examples/quickstart/features/features.py`](../examples/quickstart/features/features.py)
is a complete project: dbt models over three SQLite tables, declarative aggregations (one of them
filtering on a point-in-time joined merchant attribute), a derived-on-derived
view, an on-demand view with request data, and a feature service.

## Sources

`DataSource.read(columns, start, end)` is the only thing the rest of the
system calls. The base class guarantees:

- rows with `start <= event time < end`;
- `field_mapping` applied (raw column → feature name);
- the event-time column is always returned as `event_timestamp`
  (`datetime64[ns, UTC]`), and the optional created-time column as
  `created_timestamp`, which breaks ties between rows with the same event time.

Built in:
- `SQLiteSource`, `PostgresSource`
- `DuckDBSource`: Parquet/CSV globs or any DuckDB query, with filters pushed down
- `DbtModelSource(model=...)`: reads the Parquet output of a dbt model in the project
- `FileSource`, `DataFrameSource`

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

`materialize(start, end)` computes every batch view over `[start, end)` at its
current version. All rows go to the offline cache, raw-event views included,
so later reads never have to go back to the source. For `online=True` views,
the latest row per entity also goes to the online store. A per-version
**watermark** is recorded. `materialize_incremental()` resumes from that
watermark. For a first run it starts from `end - ttl`.

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
# <project>/shalf.yaml
project: quickstart
definitions: [entities.py, features.py]   # files or directories
offline_store: {type: pandas}
online_store:
  type: redis
  url: ${SHALF_REDIS_URL}
```

Relative `path` / `*_path` / `*_dir` entries resolve against the project.
`$SHALF_PROFILE` picks a profile. The platform's Kubernetes base sets
`serving`, `batch` or `eda` per workload, which is how the same file switches
to Redis in the cluster. `$SHALF_CONFIG` can point at a different file
entirely.

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
shalf-data --repo PATH plan | backfill [--start --end --views --promote] | promote [--views]
shalf-data --repo PATH --profile eda preview VIEW [--start --end --limit]
```

## Performance

| Where the time goes                | What shalf does                                                                     |
| ---------------------------------- | ----------------------------------------------------------------------------------- |
| Windowed aggregations              | One DuckDB window-function query per view: vectorised, multi-threaded, one pass for all `Aggregate`s |
| Reading sources                    | Projection (only needed columns) and time filters pushed into SQL                   |
| Recomputing the same history       | Every materialised row lands in the Parquet **offline cache**; training sets, EDA and later backfills read it instead of recomputing |
| Keeping features fresh             | Incremental materialisation from per-version watermarks; `lookback` bounds the history read |
| Online reads                       | Key/value lookups only, pipelined per view (Redis); never touches sources           |

`examples/benchmarks/aggregations.py` compares six windowed features
(count/sum/mean over 1d and 7d) on 2M events and 50k entities against the
equivalent hand-written pandas `groupby().rolling()` code. On a 4-core
machine: **pandas 16.6s, shalf 1.5s (11x)**, with identical values.

## Isolation: serving vs. exploration

Online serving must not slow down because someone runs a heavy query in a
notebook. The data layer splits traffic into separate paths:

```
                    ┌──────────── serving path ────────────┐
inference-api ──▶ feature-server ──▶ Redis primary
                    (priority: shalf-serving, NetworkPolicy: inference-api only)

notebooks ──────▶ feature-server-eda ──▶ Redis replica (read_only)
   │                (priority: shalf-eda, profile: eda)
   └──▶ get_historical_features / preview ──▶ Parquet offline cache (cache_only)

pipelines / backfills ──▶ source DB *replica* ──▶ dbt ──▶ cache + Redis primary
                    (priority: shalf-batch)
```

- **The online path never reads sources.** It only does key/value lookups
  (tested in `test_online_reads_never_touch_sources`). Heavy offline queries
  cannot block it.
- **Exploration has its own online endpoint.** `feature-server-eda` runs the
  same image with `SHALF_PROFILE=eda`. It reads a Redis replica through a
  `read_only` store, runs at the lowest priority class with its own
  autoscaling range, and a NetworkPolicy keeps exploration clients off the
  serving pods.
- **Exploration never hits source databases.** The `eda` profile sets the
  offline store to `cache_only`, so notebooks read the Parquet cache that
  materialisation keeps up to date. A range that isn't cached raises
  `CacheMissError` instead of silently querying production. Derived views
  can still be computed on the fly from cached upstreams.
- **Batch work reads replicas.** Point the source DSN (`SHALF_PG_DSN`) at a
  read replica or the warehouse. Materialisation and backfills run at
  `shalf-batch` priority, which never preempts serving.

All of this is configuration of the same code. A `shalf.yaml` holds one
profile per deployment flavour, and `$SHALF_PROFILE` picks one. Environment
variables are only resolved for the profile actually used.

```yaml
profiles:
  eda:
    offline_store: {type: pandas, cache_path: /cache, cache_only: true}
    online_store: {type: redis, url: "${SHALF_REDIS_REPLICA_URL}", read_only: true}
```

## Changing feature logic: backfills

Every batch view has a **version**: a fingerprint of the logic that produces
its values. It covers the source table or query, column mapping, schema,
transformation code (decorators excluded) or `Aggregate` definitions, and
the versions of its upstream views. Connection details (paths, DSNs) are not
part of it, so dev and prod agree. A change therefore re-versions the view
**and everything downstream of it**. When the logic depends on something the
fingerprint can't see, such as a helper function, set `version="2"` on the
view and bump it by hand.

Values are stored per version: online in a namespace `view@version`, offline
in `cache/<view>/<version>/`. Readers follow each view's **active version**
pointer, so old and new logic never mix:

```bash
shalf-data plan                     # status per view: new / unchanged / changed,
                                    # plus the feature services (models) affected
shalf-data backfill --start 2024-01-01          # recompute changed views + dependents
shalf-data preview customer_txn_stats           # check the new values
shalf-data promote                  # switch readers to the new versions together
```

- **Before promotion** serving keeps returning the old version's values.
  Promotion is one metadata write per view. Feature servers pick it up within
  `version_cache_seconds` (default 10s) without a restart.
- **Training is correct immediately.** `get_historical_features` uses the
  code's version. When that version isn't cached yet it is computed from the
  upstream views, preferring their cached rows. The backfill only makes it
  fast.
- **Without a manual step** (`auto_promote: true`, the default), the first
  `materialize-incremental` run after a deploy warms the new version (from
  `now - ttl`, or the full history without a ttl) and promotes it when the run
  completes. Readers see old values until then and new values afterwards.
  Set `auto_promote: false` to review before switching. The old version then
  goes stale until promotion, because the old code is no longer deployed. Run
  the old image's materialiser side by side if that matters.
- **Models.** `plan` lists the feature services that read a changed view.
  A model trained on the old logic should be retrained on the new version
  before (or as) it is promoted.
- Old versions stay in the cache and online store until removed. Garbage
  collection is not implemented yet.

dbt models take part in the same flow. `DbtModelSource` includes the
checksum of the model's SQL, macros and upstream models (from dbt's
`manifest.json`) in the view version. Editing `fct_transactions.sql` therefore
re-versions every view built on it, and only those.

On Kubernetes, `shalf-pipelines run hourly --start ... --end ...` runs a
backfill (see the quickstart's `deploy/jobs/backfill.yaml`). It passes the
range to dbt as `--vars` for incremental models, and uses the same image tag
as the deployed code so the versions match.

## Known limitations / next steps

- **Scale of the offline store.** Aggregations are vectorised (DuckDB), but
  the point-in-time join and custom transformations run in one process.
  Next: push the whole retrieval down to the warehouse as SQL, or run it on
  Spark/Ray.
- **Rolling windows are event driven.** A 7-day count is as of the entity's
  last event. It does not decay without new events, except through the
  view's `ttl`. Tiled aggregates (partial aggregates per time bucket,
  combined at read time) would fix this and make online freshness independent
  of the materialisation schedule.
- **Late-arriving data.** Rows inserted with old timestamps after a range was
  cached are not picked up until that range is backfilled again.
- **One pipeline writes at a time.** dbt-duckdb's warehouse file has a
  single writer, so runs take an exclusive lock on the warehouse directory
  and queue up. dbt runs in a child process per command, so nothing keeps the
  file open between runs.
- **Offline cache storage** is a filesystem path (a ReadWriteMany volume on
  Kubernetes). Object storage (`s3://`, `gs://`) through DuckDB's `httpfs`
  is the natural next step.
- **Online value encoding** is JSON. Timestamps come back as ISO strings.
- **The registry is code-first and in memory**, rebuilt in each process.
- **Postgres** shares the SQL code path tested on SQLite, but the query
  builder is only unit-tested here. Redis is tested against fakeredis.
- **Streaming / push ingestion** (Kafka → online store), data-quality hooks
  and garbage collection of old versions are not implemented yet.
