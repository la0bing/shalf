"""shalf data layer.

Typical feature repository::

    from shalf.data import Entity, Field, FeatureView, SQLiteSource, ValueType

    customer = Entity(name="customer", join_key="customer_id")
    source = SQLiteSource(name="txns", path="app.db", table="transactions",
                          timestamp_field="created_at")
    stats = FeatureView(name="customer_stats", entities=[customer], source=source,
                        schema=[Field("amount", ValueType.FLOAT64)])
"""

from shalf.data.aggregations import Aggregate, AggregationFeatureView
from shalf.data.config import FeatureStoreConfig
from shalf.data.entity import Entity
from shalf.data.feature_service import FeatureService
from shalf.data.feature_view import (
    BaseFeatureView,
    DerivedFeatureView,
    FeatureView,
    OnDemandFeatureView,
    derived_feature_view,
    on_demand_feature_view,
)
from shalf.data.offline import OfflineStore, PandasOfflineStore, offline_store_registry
from shalf.data.online import (
    InMemoryOnlineStore,
    OnlineStore,
    RedisOnlineStore,
    SQLiteOnlineStore,
    online_store_registry,
)
from shalf.data.registry import FeatureRef, FeatureRegistry, RegistryError
from shalf.data.sources import (
    DataFrameSource,
    DataSource,
    DbtModelSource,
    DuckDBSource,
    FileSource,
    PostgresSource,
    SQLDataSource,
    SQLiteSource,
    source_registry,
)
from shalf.data.store import FeatureStore, OnlineResponse
from shalf.data.transformations import (
    PandasTransformation,
    PythonTransformation,
    Transformation,
    transformation_registry,
)
from shalf.data.types import CREATED_TIMESTAMP, EVENT_TIMESTAMP, Field, ValueType

__all__ = [
    "CREATED_TIMESTAMP",
    "EVENT_TIMESTAMP",
    "Aggregate",
    "AggregationFeatureView",
    "BaseFeatureView",
    "DataFrameSource",
    "DataSource",
    "DbtModelSource",
    "DerivedFeatureView",
    "DuckDBSource",
    "Entity",
    "FeatureRef",
    "FeatureRegistry",
    "FeatureService",
    "FeatureStore",
    "FeatureStoreConfig",
    "FeatureView",
    "Field",
    "FileSource",
    "InMemoryOnlineStore",
    "OfflineStore",
    "OnDemandFeatureView",
    "OnlineResponse",
    "OnlineStore",
    "PandasOfflineStore",
    "PandasTransformation",
    "PostgresSource",
    "PythonTransformation",
    "RedisOnlineStore",
    "RegistryError",
    "SQLDataSource",
    "SQLiteOnlineStore",
    "SQLiteSource",
    "Transformation",
    "ValueType",
    "derived_feature_view",
    "offline_store_registry",
    "on_demand_feature_view",
    "online_store_registry",
    "source_registry",
    "transformation_registry",
]
