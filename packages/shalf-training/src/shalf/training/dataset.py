from __future__ import annotations

import pandas as pd

from shalf.data import FeatureStore


def build_training_frame(
    store: FeatureStore, spine: pd.DataFrame, feature_service: str, label: str
) -> tuple[pd.DataFrame, pd.Series]:
    """Point-in-time correct ``(X, y)`` for a model's feature service.

    ``spine`` holds entity keys, ``event_timestamp``, any request-time columns
    and the label column.
    """
    df = store.get_historical_features(spine, feature_service=feature_service)
    service = store.registry.get_service(feature_service)
    columns = [r.feature for r in store.registry.resolve_features(service.feature_refs)]
    return df[columns], df[label]
