from datetime import timedelta

import pandas as pd
from fastapi.testclient import TestClient

from feature_server.app import create_app
from shalf.data import (
    DataFrameSource,
    Entity,
    FeatureStore,
    FeatureView,
    Field,
    InMemoryOnlineStore,
    ValueType,
)
from shalf.data.types import utcnow


def make_store() -> FeatureStore:
    now = utcnow()
    customer = Entity(name="customer", join_key="customer_id")
    source = DataFrameSource(
        name="stats",
        df=pd.DataFrame(
            {"customer_id": [1, 2], "score": [0.5, 0.9], "ts": [now - timedelta(hours=1)] * 2}
        ),
        timestamp_field="ts",
    )
    view = FeatureView(
        name="stats", entities=[customer], source=source, schema=[Field("score", ValueType.FLOAT64)]
    )
    store = FeatureStore()
    store.apply(view)
    store.materialize(end=now)
    return store


def test_online_features_endpoint():
    with TestClient(create_app(make_store())) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/readyz").status_code == 200
        assert client.get("/v1/registry").json()["feature_views"][0]["name"] == "stats"

        response = client.post(
            "/v1/features/online",
            json={"entities": {"customer_id": ["1", 3]}, "features": ["stats:score"]},
        )
        assert response.status_code == 200
        assert response.json()["results"] == {"customer_id": ["1", 3], "score": [0.5, None]}

        bad = client.post(
            "/v1/features/online", json={"entities": {"customer_id": [1]}, "features": ["nope:x"]}
        )
        assert bad.status_code == 400


def test_readiness_fails_when_online_store_is_down():
    class Down(InMemoryOnlineStore):
        def ping(self):
            raise ConnectionError("redis is down")

    store = FeatureStore(online_store=Down())
    with TestClient(create_app(store)) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 503
