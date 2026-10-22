from shalf.models import LocalModelRegistry, ModelArtifact


def test_register_get_promote(tmp_path):
    registry = LocalModelRegistry(tmp_path)
    registry.register(ModelArtifact("fraud", "1", "s3://m/1", feature_service="fraud_model_v1"))
    registry.promote("fraud", "1", "production")
    assert registry.get("fraud", stage="production").version == "1"
