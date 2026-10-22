"""The framework's extension points: plug in a new source, online store and transformation."""

from collections.abc import Sequence

import pandas as pd

from shalf.data import (
    DataSource,
    Entity,
    FeatureStore,
    FeatureStoreConfig,
    FeatureView,
    Field,
    InMemoryOnlineStore,
    Transformation,
    derived_feature_view,
    online_store_registry,
    source_registry,
    transformation_registry,
)
from shalf.data.sources import filter_time_range
from shalf.data.types import utcnow


@source_registry.register("http_json_test")
class FakeHttpSource(DataSource):
    """Stands in for e.g. a REST API or a warehouse a user wants to plug in."""

    def __init__(self, *, rows: Sequence[dict], **kwargs):
        super().__init__(**kwargs)
        self.rows = rows

    def _read(self, columns, start, end):
        df = pd.DataFrame(self.rows)
        return filter_time_range(df, self.timestamp_field, start, end)[columns or df.columns]


@online_store_registry.register("counting_test")
class CountingStore(InMemoryOnlineStore):
    reads = 0

    def read_records(self, view, entity_keys):
        type(self).reads += 1
        return super().read_records(view, entity_keys)


@transformation_registry.register("upper_test")
class UpperCaseColumns(Transformation):
    """A custom engine: fn receives a dict of columns."""

    def transform(self, df):
        return pd.DataFrame(self.fn({c: df[c] for c in df.columns}))


def test_custom_plugins_from_config():
    now = utcnow()
    source = source_registry.create(
        {
            "type": "http_json_test",
            "name": "api",
            "timestamp_field": "at",
            "rows": [{"user": 1, "clicks": 3, "at": now.isoformat()}],
        }
    )
    user = Entity(name="user", join_key="user")
    clicks = FeatureView(name="clicks", entities=[user], source=source, schema=[Field("clicks")])

    @derived_feature_view(sources=[clicks], schema=[Field("clicks_sq")], mode="upper_test")
    def squared(cols):
        return {"clicks_sq": cols["clicks"] ** 2}

    store = FeatureStore(FeatureStoreConfig(online_store={"type": "counting_test"}))
    store.apply(squared)
    store.materialize(end=now + pd.Timedelta(seconds=1))
    assert store.get_online_features({"user": [1]}, ["squared:clicks_sq"]).to_dict()[
        "clicks_sq"
    ] == [9]
    assert CountingStore.reads == 1
