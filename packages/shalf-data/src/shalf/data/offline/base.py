from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field

import pandas as pd

from shalf.core import PluginRegistry
from shalf.data.feature_view import BaseFeatureView
from shalf.data.types import CREATED_TIMESTAMP, EVENT_TIMESTAMP


@dataclass
class ViewRequest:
    """Which features of one (materialisable) view to fetch, and the output column names."""

    view: BaseFeatureView
    features: list[str]
    output_names: dict[str, str] = field(default_factory=dict)

    def output_name(self, feature: str) -> str:
        return self.output_names.get(feature, feature)


class OfflineStore(ABC):
    """Historical feature computation: training sets and materialisation input.

    Implementations decide *where* the work happens - in-process pandas (the
    default), pushed down to a warehouse as SQL, on Spark, etc. They must
    honour the same semantics:

    * point-in-time correctness: a row at time ``t`` only sees feature values
      with ``event_timestamp <= t`` (and newer than ``t - ttl``);
    * derived views are computed from their upstream views with their
      transformation.
    """

    @abstractmethod
    def get_historical_features(
        self, entity_df: pd.DataFrame, requests: Sequence[ViewRequest]
    ) -> pd.DataFrame:
        """Join requested features onto ``entity_df`` (which has ``event_timestamp``)."""

    @abstractmethod
    def read_view(
        self,
        view: BaseFeatureView,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """All rows of a view with event time in ``[start, end)``: join keys,
        ``event_timestamp`` and every feature of the view."""

    def write_cache(  # noqa: B027 - optional hook
        self,
        view: BaseFeatureView,
        df: pd.DataFrame,
        start: pd.Timestamp | None,
        end: pd.Timestamp,
    ) -> None:
        """Persist rows computed for ``[start, end)`` (materialisation/backfill output)."""

    def pull_latest(
        self, view: BaseFeatureView, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> pd.DataFrame:
        """Latest row per entity in ``[start, end)``; the input of materialisation."""
        return latest_per_entity(view, self.read_view(view, start, end))


def latest_per_entity(view: BaseFeatureView, df: pd.DataFrame) -> pd.DataFrame:
    order = [EVENT_TIMESTAMP] + ([CREATED_TIMESTAMP] if CREATED_TIMESTAMP in df else [])
    df = df.sort_values(order, kind="stable")
    return df.drop_duplicates(subset=view.join_keys, keep="last").reset_index(drop=True)


offline_store_registry: PluginRegistry[OfflineStore] = PluginRegistry(
    "offline store", OfflineStore, entry_point_group="shalf.data.offline_stores"
)
