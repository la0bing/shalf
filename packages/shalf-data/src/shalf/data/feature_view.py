"""Feature definitions.

Three kinds of views, all sharing :class:`BaseFeatureView`:

* :class:`FeatureView` - features read straight from a :class:`DataSource`.
* :class:`DerivedFeatureView` - batch features computed from one or more other
  views (base or derived, so they chain into a DAG). Computed by the offline
  store and materialised to the online store like any other view.
* :class:`OnDemandFeatureView` - features computed at retrieval time from other
  views plus request-time data (e.g. the amount of the transaction being
  scored). Never materialised.

(:class:`~shalf.data.aggregations.AggregationFeatureView` is a derived view
whose logic is declared as windowed aggregates instead of code.)

Every view has a ``version``: a fingerprint of the logic that produces its
values (source/query, transformation code, schema and upstream versions).
Changing the logic changes the version, which is what drives backfills.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from typing import Any

from shalf.data.entity import Entity
from shalf.data.sources.base import DataSource
from shalf.data.transformations import Transformation, transformation_registry
from shalf.data.types import Field, SchemaLike, normalize_schema, parse_duration


class BaseFeatureView:
    kind: str = "base"

    def __init__(
        self,
        *,
        name: str,
        schema: SchemaLike,
        entities: Sequence[Entity] | None = None,
        ttl: timedelta | str | None = None,
        online: bool = True,
        version: str | None = None,
        description: str = "",
        owner: str = "",
        tags: Mapping[str, str] | None = None,
    ) -> None:
        schema = normalize_schema(schema)
        if not schema:
            raise ValueError(f"Feature view {name!r} must declare at least one feature")
        names = [f.name for f in schema]
        if len(set(names)) != len(names):
            raise ValueError(f"Feature view {name!r} declares duplicate features: {names}")
        self.name = name
        self.schema = list(schema)
        self.entities: list[Entity] = list(entities or [])
        self.ttl = parse_duration(ttl)
        self.online = online
        self.explicit_version = version
        self.description = description
        self.owner = owner
        self.tags = dict(tags or {})

    # -- introspection -------------------------------------------------------
    @property
    def join_keys(self) -> list[str]:
        return [e.key for e in self.entities]

    @property
    def feature_names(self) -> list[str]:
        return [f.name for f in self.schema]

    @property
    def upstream(self) -> list[BaseFeatureView | str]:
        return []

    @property
    def materializable(self) -> bool:
        return self.online

    def field(self, name: str) -> Field:
        for f in self.schema:
            if f.name == name:
                return f
        raise KeyError(f"Feature view {self.name!r} has no feature {name!r}")

    # -- versioning ----------------------------------------------------------
    @property
    def version(self) -> str:
        """Fingerprint of the logic producing this view's values.

        Pass ``version="..."`` explicitly when the logic depends on something
        the fingerprint cannot see (e.g. a helper function the transformation
        calls); bump it to force a backfill.
        """
        if self.explicit_version is not None:
            return str(self.explicit_version)
        logic = {
            "kind": self.kind,
            "keys": self.join_keys,
            "schema": [(f.name, f.dtype.value) for f in self.schema],
            **self._logic(),
        }
        digest = hashlib.sha256(json.dumps(logic, sort_keys=True, default=str).encode())
        return digest.hexdigest()[:10]

    def _logic(self) -> dict[str, Any]:
        return {}

    # -- references ----------------------------------------------------------
    def ref(self, feature: str) -> str:
        self.field(feature)
        return f"{self.name}:{feature}"

    def __getitem__(self, features: str | Sequence[str]) -> list[str]:
        """``view["a"]`` or ``view[["a", "b"]]`` -> feature references."""
        if isinstance(features, str):
            features = [features]
        return [self.ref(f) for f in features]

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "entities": [e.name for e in self.entities],
            "join_keys": self.join_keys,
            "features": [f.to_dict() for f in self.schema],
            "ttl_seconds": self.ttl.total_seconds() if self.ttl else None,
            "online": self.online,
            "version": self.version,
            "upstream": [u if isinstance(u, str) else u.name for u in self.upstream],
            "description": self.description,
            "owner": self.owner,
            "tags": self.tags,
        }

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


class FeatureView(BaseFeatureView):
    kind = "batch"

    def __init__(self, *, source: DataSource, entities: Sequence[Entity], **kwargs: Any) -> None:
        if not entities:
            raise ValueError("A FeatureView needs at least one entity")
        super().__init__(entities=entities, **kwargs)
        self.source = source

    def _logic(self) -> dict[str, Any]:
        return {"source": self.source.fingerprint()}

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "source": self.source.describe()}


class _TransformedView(BaseFeatureView):
    """Common bits of views computed from other views."""

    def __init__(
        self,
        *,
        sources: Sequence[BaseFeatureView | str],
        transformation: Transformation,
        **kwargs: Any,
    ) -> None:
        if not sources:
            raise ValueError("A transformed view needs at least one upstream view")
        super().__init__(**kwargs)
        self.sources: list[BaseFeatureView | str] = list(sources)
        self.transformation = transformation

    @property
    def upstream(self) -> list[BaseFeatureView | str]:
        return self.sources

    def bind(self, lookup: Callable[[str], BaseFeatureView]) -> None:
        """Replace upstream references given by name with the view objects."""
        self.sources = [lookup(s) if isinstance(s, str) else s for s in self.sources]

    @property
    def resolved_sources(self) -> list[BaseFeatureView]:
        unresolved = [s for s in self.sources if isinstance(s, str)]
        if unresolved:
            raise RuntimeError(
                f"View {self.name!r} references {unresolved} by name; apply it to a "
                "FeatureRegistry/FeatureStore first so references are resolved"
            )
        return self.sources  # type: ignore[return-value]

    def _logic(self) -> dict[str, Any]:
        return {
            "transformation": self.transformation.fingerprint(),
            "upstream": [
                u if isinstance(u, str) else f"{u.name}@{u.version}" for u in self.sources
            ],
        }

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "transformation": self.transformation.describe()}


class DerivedFeatureView(_TransformedView):
    """Batch features built on top of existing feature views.

    The first entry of ``sources`` is the *primary* upstream: its rows (entity
    keys + event timestamps) form the spine. Every other upstream is joined
    onto that spine point-in-time correctly, using its own join keys (which
    must be columns of the spine, e.g. ``merchant_id`` on a transactions
    spine). The transformation then receives one frame with all upstream
    features and returns the derived features.

    If the transformation returns the entity keys and ``event_timestamp``
    itself it may change the number of rows (e.g. aggregate to daily rows);
    otherwise it must return one row per input row.

    ``lookback`` bounds how much upstream history is read when materialising
    an incremental window (e.g. ``timedelta(days=30)`` for a 30-day rolling
    aggregate). ``None`` reads the full history - always correct, sometimes slow.
    """

    kind = "derived"

    def __init__(
        self,
        *,
        name: str,
        sources: Sequence[BaseFeatureView | str],
        schema: SchemaLike,
        transformation: Transformation,
        entities: Sequence[Entity] | None = None,
        ttl: timedelta | str | None = None,
        lookback: timedelta | str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            sources=sources,
            schema=schema,
            transformation=transformation,
            entities=entities,
            ttl=ttl,
            **kwargs,
        )
        self.lookback = parse_duration(lookback)
        # Unless given explicitly, entities and ttl follow the primary upstream.
        self._inherit_entities = entities is None
        self._inherit_ttl = ttl is None
        self._inherit_from_primary()

    def bind(self, lookup: Callable[[str], BaseFeatureView]) -> None:
        super().bind(lookup)
        self._inherit_from_primary()

    def _inherit_from_primary(self) -> None:
        primary = self.sources[0]
        if isinstance(primary, BaseFeatureView):
            if self._inherit_entities:
                self.entities = list(primary.entities)
            if self._inherit_ttl:
                self.ttl = primary.ttl

    @property
    def primary(self) -> BaseFeatureView:
        return self.resolved_sources[0]


class OnDemandFeatureView(_TransformedView):
    """Features computed at retrieval time, optionally from request data.

    The transformation receives one row per requested entity row containing
    the upstream features, the entity join keys and the ``request_schema``
    fields, and must return the same number of rows.
    """

    kind = "on_demand"

    def __init__(
        self,
        *,
        name: str,
        sources: Sequence[BaseFeatureView | str],
        schema: SchemaLike,
        transformation: Transformation,
        request_schema: SchemaLike = (),
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("online", False)
        super().__init__(
            name=name, sources=sources, schema=schema, transformation=transformation, **kwargs
        )
        self.request_schema = normalize_schema(request_schema)
        self._inherit_entities = not self.entities
        self._collect_entities()

    def bind(self, lookup: Callable[[str], BaseFeatureView]) -> None:
        super().bind(lookup)
        self._collect_entities()

    def _collect_entities(self) -> None:
        """Entities default to the union of the upstream views' entities."""
        if not self._inherit_entities:
            return
        entities: dict[str, Entity] = {}
        for upstream in self.sources:
            if isinstance(upstream, BaseFeatureView):
                entities.update({e.name: e for e in upstream.entities})
        self.entities = list(entities.values())

    @property
    def materializable(self) -> bool:
        return False

    def _logic(self) -> dict[str, Any]:
        return {
            **super()._logic(),
            "request": [(f.name, f.dtype.value) for f in self.request_schema],
        }

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "request_schema": [f.to_dict() for f in self.request_schema]}


def _make_transformation(fn: Callable[..., Any], mode: str) -> Transformation:
    return transformation_registry.create({"type": mode, "fn": fn})


def derived_feature_view(
    *,
    sources: Sequence[BaseFeatureView | str],
    schema: SchemaLike,
    name: str | None = None,
    mode: str = "pandas",
    **kwargs: Any,
) -> Callable[[Callable[..., Any]], DerivedFeatureView]:
    """Decorator form of :class:`DerivedFeatureView`::

    @derived_feature_view(sources=[txn_stats], schema={"avg_amount": float})
    def customer_avg(df):
        return df.assign(avg_amount=df.total_amount / df.txn_count)
    """

    def wrap(fn: Callable[..., Any]) -> DerivedFeatureView:
        return DerivedFeatureView(
            name=name or fn.__name__,
            sources=sources,
            schema=schema,
            transformation=_make_transformation(fn, mode),
            description=kwargs.pop("description", None) or (fn.__doc__ or "").strip(),
            **kwargs,
        )

    return wrap


def on_demand_feature_view(
    *,
    sources: Sequence[BaseFeatureView | str],
    schema: SchemaLike,
    request_schema: SchemaLike = (),
    name: str | None = None,
    mode: str = "pandas",
    **kwargs: Any,
) -> Callable[[Callable[..., Any]], OnDemandFeatureView]:
    """Decorator form of :class:`OnDemandFeatureView`."""

    def wrap(fn: Callable[..., Any]) -> OnDemandFeatureView:
        return OnDemandFeatureView(
            name=name or fn.__name__,
            sources=sources,
            schema=schema,
            request_schema=request_schema,
            transformation=_make_transformation(fn, mode),
            description=kwargs.pop("description", None) or (fn.__doc__ or "").strip(),
            **kwargs,
        )

    return wrap
