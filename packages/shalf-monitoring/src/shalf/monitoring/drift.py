from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from shalf.core import PluginRegistry


class DriftDetector(ABC):
    """Compares a reference (training) distribution with live traffic."""

    @abstractmethod
    def score(self, reference: pd.Series, current: pd.Series) -> float: ...


drift_detector_registry: PluginRegistry[DriftDetector] = PluginRegistry(
    "drift detector", DriftDetector, entry_point_group="shalf.monitoring.drift_detectors"
)


@drift_detector_registry.register("psi")
class PSIDriftDetector(DriftDetector):
    """Population stability index over reference-quantile bins."""

    def __init__(self, bins: int = 10) -> None:
        self.bins = bins

    def score(self, reference: pd.Series, current: pd.Series) -> float:
        edges = np.unique(np.quantile(reference.dropna(), np.linspace(0, 1, self.bins + 1)))
        edges[0], edges[-1] = -np.inf, np.inf
        ref = np.histogram(reference.dropna(), edges)[0] / max(reference.notna().sum(), 1)
        cur = np.histogram(current.dropna(), edges)[0] / max(current.notna().sum(), 1)
        ref, cur = np.clip(ref, 1e-6, None), np.clip(cur, 1e-6, None)
        return float(np.sum((cur - ref) * np.log(cur / ref)))
