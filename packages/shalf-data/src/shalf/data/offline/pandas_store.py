from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

import numpy as np
import pandas as pd

from shalf.core import ShalfError
from shalf.data.feature_view import BaseFeatureView, DerivedFeatureView, FeatureView
from shalf.data.offline.base import OfflineStore, ViewRequest, offline_store_registry
from shalf.data.types import CREATED_TIMESTAMP, EVENT_TIMESTAMP, cast_series, to_utc

# Upper read bound past the newest entity timestamp. The point-in-time join
# filters exactly, so this only needs to survive backends that truncate
# timestamps (SQLite: ms, some warehouses: s).
_READ_MARGIN = pd.Timedelta(seconds=1)


@offline_store_registry.register("pandas")
class PandasOfflineStore(OfflineStore):
    """Pulls rows from each view's source and does all joins in-process with pandas.

    Simple and dependency-free; fine up to a few million rows. For larger data,
    register an offline store that pushes the same work down to the warehouse.
    """

    def get_historical_features(
        self, entity_df: pd.DataFrame, requests: Sequence[ViewRequest]
    ) -> pd.DataFrame:
        if EVENT_TIMESTAMP not in entity_df:
            raise ShalfError(f"entity_df needs an {EVENT_TIMESTAMP!r} column")
        result = entity_df.copy()
        result[EVENT_TIMESTAMP] = to_utc(result[EVENT_TIMESTAMP])
        if result.empty:
            for request in requests:
                for feature in request.features:
                    result[request.output_name(feature)] = pd.Series(dtype=object)
            return result

        earliest, latest = result[EVENT_TIMESTAMP].min(), result[EVENT_TIMESTAMP].max()
        for request in requests:
            view = request.view
            start = None if view.ttl is None else earliest - view.ttl
            frame = self.read_view(view, start, latest + _READ_MARGIN)
            result = point_in_time_join(
                result,
                frame,
                join_keys=view.join_keys,
                features=request.features,
                ttl=view.ttl,
                rename={f: request.output_name(f) for f in request.features},
            )
        return result

    def read_view(
        self,
        view: BaseFeatureView,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        if isinstance(view, FeatureView):
            df = view.source.read(
                columns=[*view.join_keys, *view.feature_names], start=start, end=end
            )
            for f in view.schema:
                try:
                    df[f.name] = cast_series(df[f.name], f.dtype)
                except (TypeError, ValueError) as exc:
                    raise ShalfError(
                        f"{view.name}:{f.name} is not castable to {f.dtype.value}: {exc}"
                    ) from exc
        elif isinstance(view, DerivedFeatureView):
            df = self._compute_derived(view, start, end)
        else:
            raise ShalfError(f"{type(view).__name__} {view.name!r} cannot be read as a batch view")

        missing = [c for c in [*view.join_keys, *view.feature_names] if c not in df]
        if missing:
            raise ShalfError(f"View {view.name!r} is missing columns {missing}")
        extra = [CREATED_TIMESTAMP] if CREATED_TIMESTAMP in df else []
        return df[[*view.join_keys, EVENT_TIMESTAMP, *extra, *view.feature_names]]

    def _compute_derived(
        self, view: DerivedFeatureView, start: pd.Timestamp | None, end: pd.Timestamp | None
    ) -> pd.DataFrame:
        upstream_start = None if start is None or view.lookback is None else start - view.lookback
        primary, *others = view.resolved_sources

        spine = self.read_view(primary, upstream_start, end)
        for other in others:
            other_start = (
                None if upstream_start is None or other.ttl is None else upstream_start - other.ttl
            )
            spine = point_in_time_join(
                spine,
                self.read_view(other, other_start, end),
                join_keys=other.join_keys,
                features=other.feature_names,
                ttl=other.ttl,
            )

        spine = spine.drop(columns=[CREATED_TIMESTAMP], errors="ignore").reset_index(drop=True)
        out = apply_transformation(view, spine, allow_reshape=True)
        mask = pd.Series(True, index=out.index)
        if start is not None:
            mask &= out[EVENT_TIMESTAMP] >= start
        if end is not None:
            mask &= out[EVENT_TIMESTAMP] < end
        return out[mask].reset_index(drop=True)


def apply_transformation(
    view: BaseFeatureView, inputs: pd.DataFrame, *, allow_reshape: bool = False
) -> pd.DataFrame:
    """Run a view's transformation and return ``keys + event_timestamp + outputs``.

    Used by both the offline store and the online path, so derived and
    on-demand features are computed by identical code in training and serving.
    """
    out = view.transformation.transform(inputs.copy())  # type: ignore[attr-defined]
    missing = [f for f in view.feature_names if f not in out]
    if missing:
        raise ShalfError(f"Transformation of {view.name!r} did not produce {missing}")

    passthrough = [c for c in [*view.join_keys, EVENT_TIMESTAMP] if c in inputs]
    if allow_reshape and all(c in out for c in passthrough):
        result = out[[*passthrough, *view.feature_names]].copy()
        result[EVENT_TIMESTAMP] = to_utc(result[EVENT_TIMESTAMP])
        return result.reset_index(drop=True)

    if len(out) != len(inputs):
        raise ShalfError(
            f"Transformation of {view.name!r} returned {len(out)} rows for {len(inputs)} inputs; "
            "return one row per input, or include the join keys and event_timestamp"
        )
    result = inputs[passthrough].reset_index(drop=True)
    for feature in view.feature_names:
        result[feature] = out[feature].to_numpy()
    return result


def point_in_time_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    join_keys: Sequence[str],
    features: Sequence[str],
    ttl: timedelta | None,
    rename: dict[str, str] | None = None,
) -> pd.DataFrame:
    """For every row of ``left``, attach the latest ``right`` row of the same
    entity with ``event_timestamp <= left.event_timestamp`` (and within ``ttl``).

    ``left`` keeps its row order, index and columns.
    """
    rename = rename or {}
    outputs = [rename.get(f, f) for f in features]
    clash = [c for c in outputs if c in left]
    if clash:
        raise ShalfError(f"Feature columns {clash} already exist in the entity frame")
    missing = [k for k in join_keys if k not in left]
    if missing:
        raise ShalfError(f"Entity frame is missing join keys {missing}")

    right = right[
        [
            *join_keys,
            EVENT_TIMESTAMP,
            *([CREATED_TIMESTAMP] if CREATED_TIMESTAMP in right else []),
            *features,
        ]
    ]
    order = [EVENT_TIMESTAMP, *([CREATED_TIMESTAMP] if CREATED_TIMESTAMP in right else [])]
    right = (
        right.sort_values(order, kind="stable")
        .drop_duplicates(subset=[*join_keys, EVENT_TIMESTAMP], keep="last")
        .drop(columns=[CREATED_TIMESTAMP], errors="ignore")
        .rename(columns={EVENT_TIMESTAMP: "__feature_ts", **rename})
    )
    for key in join_keys:
        if right[key].dtype != left[key].dtype:
            right[key] = right[key].astype(left[key].dtype)

    row_id = "__row_id"
    keyed = left[[*join_keys, EVENT_TIMESTAMP]].assign(**{row_id: np.arange(len(left))})
    keyed[EVENT_TIMESTAMP] = to_utc(keyed[EVENT_TIMESTAMP])
    keyed = keyed.dropna(subset=list(join_keys))

    merged = pd.merge_asof(
        keyed.sort_values(EVENT_TIMESTAMP, kind="stable"),
        right.sort_values("__feature_ts", kind="stable"),
        left_on=EVENT_TIMESTAMP,
        right_on="__feature_ts",
        by=list(join_keys),
        direction="backward",
        tolerance=pd.Timedelta(ttl) if ttl is not None else None,
    ).set_index(row_id)

    result = left.copy()
    positions = np.arange(len(left))
    for column in outputs:
        result[column] = merged[column].reindex(positions).to_numpy()
    return result
