"""Inference runtime. Skeleton: a predictor contract + the glue that fetches
online features for a model's feature service before calling it."""

from shalf.serving.predictor import FeatureStorePredictor, Predictor, predictor_registry

__all__ = ["FeatureStorePredictor", "Predictor", "predictor_registry"]
