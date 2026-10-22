from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from shalf.core import ShalfError, get_logger
from shalf.data.config import FeatureStoreConfig
from shalf.data.feature_service import FeatureService
from shalf.data.feature_view import BaseFeatureView, OnDemandFeatureView
from shalf.data.offline import (
    OfflineStore,
    ViewRequest,
    apply_transformation,
    offline_store_registry,
)
from shalf.data.online import OnlineStore, online_store_registry, serialize_entity_key
from shalf.data.registry import Definition, FeatureRef, FeatureRegistry
from shalf.data.repo import load_definitions
from shalf.data.types import EVENT_TIMESTAMP, as_utc_datetime, to_python, utcnow

log = get_logger(__name__)

FeatureList = Sequence[str | Sequence[str]]


def _internal(view: str, feature: str) -> str:
    return f"{view}__{feature}"


@dataclass
class _Plan:
    """How to produce a set of requested features."""

    requested: list[FeatureRef]
    fetch: list[ViewRequest]
    on_demand: list[OnDemandFeatureView]
    output_names: dict[FeatureRef, str] = field(default_factory=dict)


class OnlineResponse:
    def __init__(self, df: pd.DataFrame, feature_names: list[str]) -> None:
        self._df = df
        self.feature_names = feature_names

    def to_df(self) -> pd.DataFrame:
        return self._df.copy()

    def to_dict(self) -> dict[str, list[Any]]:
        """Column-oriented, JSON-safe output: ``{"customer_id": [...], "feature": [...]}``."""
        return {c: [to_python(v) for v in self._df[c].tolist()] for c in self._df.columns}

    def __len__(self) -> int:
        return len(self._df)


class FeatureStore:
    """Single entry point to the data layer.

    * ``apply`` - register definitions (entities, views, services);
    * ``get_historical_features`` - point-in-time correct training data (offline);
    * ``materialize`` / ``materialize_incremental`` - push latest values online;
    * ``get_online_features`` - low-latency lookup at inference time.

    Derived views are computed by the offline store and materialised; on-demand
    views are computed here, by the same function, for offline and online reads.
    """

    def __init__(
        self,
        config: FeatureStoreConfig | None = None,
        *,
        registry: FeatureRegistry | None = None,
        offline_store: OfflineStore | None = None,
        online_store: OnlineStore | None = None,
    ) -> None:
        self.config = config or FeatureStoreConfig()
        self.registry = registry or FeatureRegistry(self.config.project)
        self.offline_store = offline_store or offline_store_registry.create(
            self.config.offline_store
        )
        self.online_store = online_store or online_store_registry.create(
            self.config.online_store, project=self.config.project
        )

    @classmethod
    def from_repo(
        cls, repo_path: str | Path, config_path: str | Path | None = None
    ) -> FeatureStore:
        """Build a store from a feature repository directory.

        The config defaults to ``<repo>/shalf.yaml``; ``$SHALF_CONFIG`` or
        ``config_path`` override it (e.g. a Kubernetes ConfigMap mount).
        """
        repo = Path(repo_path).resolve()
        config_file = Path(config_path or os.environ.get("SHALF_CONFIG") or repo / "shalf.yaml")
        config = (
            FeatureStoreConfig.load(config_file) if config_file.is_file() else FeatureStoreConfig()
        )
        store = cls(config.resolve_paths(repo))
        store.apply(load_definitions(repo, config.definitions))
        return store

    # -- definitions -----------------------------------------------------------
    def apply(self, *objects: Definition | Sequence[Definition]) -> None:
        self.registry.apply(*objects)
        self.online_store.setup([v for v in self.registry.list_views() if v.materializable])

    def list_entities(self) -> list[Any]:
        return self.registry.list_entities()

    def list_feature_views(self) -> list[BaseFeatureView]:
        return self.registry.list_views()

    def list_feature_services(self) -> list[FeatureService]:
        return self.registry.list_services()

    # -- offline ---------------------------------------------------------------
    def get_historical_features(
        self,
        entity_df: pd.DataFrame,
        features: FeatureList | None = None,
        *,
        feature_service: str | FeatureService | None = None,
        full_feature_names: bool = False,
        timestamp_column: str = EVENT_TIMESTAMP,
    ) -> pd.DataFrame:
        """Return ``entity_df`` with point-in-time correct feature columns appended."""
        plan = self._plan(features, feature_service, full_feature_names)
        if timestamp_column not in entity_df:
            raise ShalfError(f"entity_df has no timestamp column {timestamp_column!r}")
        frame = entity_df.rename(columns={timestamp_column: EVENT_TIMESTAMP})
        base_columns = list(frame.columns)

        frame = self.offline_store.get_historical_features(frame, plan.fetch)
        frame = self._apply_on_demand(frame, plan, base_columns)
        out = self._select_outputs(frame, plan, base_columns)
        return out.rename(columns={EVENT_TIMESTAMP: timestamp_column})

    # -- materialisation -------------------------------------------------------
    def materialize(
        self,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
        views: Sequence[str] | None = None,
    ) -> dict[str, int]:
        """Write the latest value per entity with event time in ``[start, end)`` online."""
        end_ts = as_utc_datetime(end) or utcnow()
        start_ts = as_utc_datetime(start)
        written: dict[str, int] = {}
        for view in self._materializable(views):
            df = self.offline_store.pull_latest(view, start_ts, end_ts)
            written[view.name] = self.online_store.write_frame(view, df) if len(df) else 0
            self.online_store.set_watermark(view.name, end_ts)
            log.info(
                "materialized %s rows of %s [%s, %s)",
                written[view.name],
                view.name,
                start_ts,
                end_ts,
            )
        return written

    def materialize_incremental(
        self, end: datetime | str | None = None, views: Sequence[str] | None = None
    ) -> dict[str, int]:
        """Materialise each view from its last watermark (or its ttl window) up to ``end``."""
        end_ts = as_utc_datetime(end) or utcnow()
        written: dict[str, int] = {}
        for view in self._materializable(views):
            start = self.online_store.get_watermark(view.name)
            if start is None and view.ttl is not None:
                start = end_ts - view.ttl
            written.update(self.materialize(start, end_ts, [view.name]))
        return written

    # -- online ----------------------------------------------------------------
    def get_online_features(
        self,
        entity_rows: Mapping[str, Sequence[Any]] | Sequence[Mapping[str, Any]],
        features: FeatureList | None = None,
        *,
        feature_service: str | FeatureService | None = None,
        request_data: Mapping[str, Sequence[Any]] | Sequence[Mapping[str, Any]] | None = None,
        full_feature_names: bool = False,
    ) -> OnlineResponse:
        plan = self._plan(features, feature_service, full_feature_names)
        frame = _rows_to_frame(entity_rows)
        if request_data:
            extra = _rows_to_frame(request_data)
            if len(extra) != len(frame):
                raise ShalfError("request_data must have one row per entity row")
            frame = pd.concat([frame, extra.drop(columns=frame.columns, errors="ignore")], axis=1)
        base_columns = list(frame.columns)

        now = utcnow()
        frame[EVENT_TIMESTAMP] = now  # on-demand transformations see "now" online
        for request in plan.fetch:
            view = request.view
            missing = [k for k in view.join_keys if k not in frame]
            if missing:
                raise ShalfError(f"Feature view {view.name!r} needs join keys {missing}")
            coerce = {e.key: e.value_type.coerce for e in view.entities}
            keys = [
                serialize_entity_key(
                    {k: coerce[k](v) for k, v in zip(view.join_keys, row, strict=True)}
                )
                for row in frame[view.join_keys].itertuples(index=False, name=None)
            ]
            records = self.online_store.read_records(view, keys)
            oldest = None if view.ttl is None else now - view.ttl
            fresh = [
                r if r and (oldest is None or r.event_timestamp >= oldest) else None
                for r in records
            ]
            for feature in request.features:
                frame[request.output_name(feature)] = [
                    r.values.get(feature) if r else None for r in fresh
                ]

        frame = self._apply_on_demand(frame, plan, base_columns)
        out = self._select_outputs(frame, plan, base_columns)
        return OnlineResponse(out, [plan.output_names[r] for r in plan.requested])

    # -- internals -------------------------------------------------------------
    def _plan(
        self,
        features: FeatureList | None,
        feature_service: str | FeatureService | None,
        full_feature_names: bool,
    ) -> _Plan:
        if (features is None) == (feature_service is None):
            raise ShalfError("Pass exactly one of `features` or `feature_service`")
        if feature_service is not None:
            service = (
                feature_service
                if isinstance(feature_service, FeatureService)
                else self.registry.get_service(feature_service)
            )
            features = service.feature_refs
        requested = self.registry.resolve_features(features or [])

        needed: dict[str, set[str]] = {}

        def need(view: BaseFeatureView, names: Sequence[str]) -> None:
            needed.setdefault(view.name, set()).update(names)
            if isinstance(view, OnDemandFeatureView):
                for upstream in view.resolved_sources:
                    need(upstream, upstream.feature_names)

        for ref in requested:
            need(self.registry.get_view(ref.view), [ref.feature])

        fetch, on_demand = [], []
        for view in self.registry.list_views():  # dependency order
            if view.name not in needed:
                continue
            if isinstance(view, OnDemandFeatureView):
                on_demand.append(view)
                continue
            names = [f for f in view.feature_names if f in needed[view.name]]
            fetch.append(ViewRequest(view, names, {f: _internal(view.name, f) for f in names}))

        output_names = {
            ref: _internal(ref.view, ref.feature) if full_feature_names else ref.feature
            for ref in requested
        }
        dupes = {n for n in output_names.values() if list(output_names.values()).count(n) > 1}
        if dupes:
            raise ShalfError(
                f"Feature names {sorted(dupes)} are requested from several views; "
                "pass full_feature_names=True"
            )
        return _Plan(requested, fetch, on_demand, output_names)

    def _apply_on_demand(
        self, frame: pd.DataFrame, plan: _Plan, base_columns: list[str]
    ) -> pd.DataFrame:
        for view in plan.on_demand:
            inputs = frame[[c for c in [*base_columns, EVENT_TIMESTAMP] if c in frame]]
            inputs = inputs.loc[:, ~inputs.columns.duplicated()].reset_index(drop=True)
            missing = [f.name for f in view.request_schema if f.name not in inputs]
            if missing:
                raise ShalfError(f"On-demand view {view.name!r} needs request data {missing}")
            for upstream in view.resolved_sources:
                for feature in upstream.feature_names:
                    inputs[feature] = frame[_internal(upstream.name, feature)].to_numpy()
            out = apply_transformation(view, inputs)
            for feature in view.feature_names:
                frame[_internal(view.name, feature)] = out[feature].to_numpy()
        return frame

    @staticmethod
    def _select_outputs(frame: pd.DataFrame, plan: _Plan, base_columns: list[str]) -> pd.DataFrame:
        columns = {_internal(r.view, r.feature): plan.output_names[r] for r in plan.requested}
        return frame[[*base_columns, *columns]].rename(columns=columns).reset_index(drop=True)

    def _materializable(self, names: Sequence[str] | None) -> list[BaseFeatureView]:
        if names is None:
            return [v for v in self.registry.list_views() if v.materializable]
        views = [self.registry.get_view(n) for n in names]
        bad = [v.name for v in views if not v.materializable]
        if bad:
            raise ShalfError(f"Views {bad} are not materialisable (offline-only or on-demand)")
        return views


def _rows_to_frame(rows: Mapping[str, Sequence[Any]] | Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    if isinstance(rows, Mapping):
        return pd.DataFrame({k: list(v) for k, v in rows.items()})
    return pd.DataFrame.from_records(list(rows))
