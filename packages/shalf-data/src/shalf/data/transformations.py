"""Transformations turn upstream feature values into new features.

The *same* transformation object is executed by the offline store (on large
historical frames) and by the online path (on a handful of rows at request
time). Running identical code in both places is what prevents training/serving
skew.

Add a new engine (polars, SQL, Spark, ...) by subclassing
:class:`Transformation` and registering it::

    @transformation_registry.register("polars")
    class PolarsTransformation(Transformation): ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

import pandas as pd

from shalf.core import PluginRegistry


class Transformation(ABC):
    mode: ClassVar[str] = "abstract"

    def __init__(self, fn: Callable[..., Any]) -> None:
        self.fn = fn

    @abstractmethod
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a frame containing (at least) the output feature columns."""

    @property
    def name(self) -> str:
        return getattr(self.fn, "__name__", type(self).__name__)

    def describe(self) -> dict[str, Any]:
        return {"mode": self.mode, "function": f"{self.fn.__module__}.{self.name}"}


transformation_registry: PluginRegistry[Transformation] = PluginRegistry(
    "transformation", Transformation, entry_point_group="shalf.data.transformations"
)


@transformation_registry.register("pandas")
class PandasTransformation(Transformation):
    """``fn(df: pd.DataFrame) -> pd.DataFrame`` - vectorised, best for batch."""

    mode: ClassVar[str] = "pandas"

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        out = self.fn(df)
        if not isinstance(out, pd.DataFrame):
            raise TypeError(
                f"Transformation {self.name!r} must return a DataFrame, got {type(out)}"
            )
        return out


@transformation_registry.register("python")
class PythonTransformation(Transformation):
    """``fn(row: dict) -> dict`` - per row, cheapest for single-entity online lookups."""

    mode: ClassVar[str] = "python"

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        rows = [self.fn(row) for row in df.to_dict(orient="records")]
        return pd.DataFrame.from_records(rows, index=df.index)
