from fastapi.testclient import TestClient

from inference_api.app import app


def test_health_and_stub():
    client = TestClient(app)
    assert client.get("/healthz").status_code == 200
    assert (
        client.post("/v1/models/fraud/predict", json={"entities": {"customer_id": [1]}}).status_code
        == 501
    )
