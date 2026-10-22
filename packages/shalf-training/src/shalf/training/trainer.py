from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class TrainResult:
    model: Any
    metrics: dict[str, float] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)


class Trainer(ABC):
    """Wraps one modelling approach (sklearn, xgboost, torch, ...).

    TODO: hyper-parameter search hooks, distributed training launchers.
    """

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series, **params: Any) -> TrainResult: ...

    @abstractmethod
    def evaluate(self, model: Any, X: pd.DataFrame, y: pd.Series) -> dict[str, float]: ...

    @abstractmethod
    def save(self, model: Any, uri: str) -> str: ...
