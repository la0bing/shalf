from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from shalf.core import PluginRegistry
from shalf.data import FeatureStore


class Predictor(ABC):
    """Turns a feature frame into predictions. One implementation per framework."""

    @abstractmethod
    def load(self, uri: str) -> None: ...

    @abstractmethod
    def predict(self, features: pd.DataFrame) -> list[Any]: ...


predictor_registry: PluginRegistry[Predictor] = PluginRegistry(
    "predictor", Predictor, entry_point_group="shalf.serving.predictors"
)


class FeatureStorePredictor:
    """Online features (by feature service) -> model -> predictions."""

    def __init__(self, store: FeatureStore, predictor: Predictor, feature_service: str) -> None:
        self.store = store
        self.predictor = predictor
        self.feature_service = feature_service

    def predict(
        self,
        entities: Mapping[str, Sequence[Any]],
        request_data: Mapping[str, Sequence[Any]] | None = None,
    ) -> list[Any]:
        response = self.store.get_online_features(
            entities, feature_service=self.feature_service, request_data=request_data
        )
        return self.predictor.predict(response.to_df()[response.feature_names])
