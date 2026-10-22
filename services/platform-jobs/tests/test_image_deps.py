def test_batch_image_has_dbt_and_pipelines():
    import dbt.adapters.duckdb  # noqa: F401

    import shalf.pipelines.cli  # noqa: F401
