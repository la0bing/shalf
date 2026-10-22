"""The catalog of everything defined in a feature repository.

Definitions are code-first (Python modules), so the registry is rebuilt on
start-up from the same code in every process - training jobs, the
materialiser and the online feature server all see identical definitions.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias

from shalf.core import ShalfError
from shalf.data.entity import Entity
from shalf.data.feature_service import FeatureService
from shalf.data.feature_view import (
    BaseFeatureView,
    DerivedFeatureView,
    FeatureView,
    OnDemandFeatureView,
    _TransformedView,
)

Definition: TypeAlias = Entity | BaseFeatureView | FeatureService


class RegistryError(ShalfError):
    """Invalid or inconsistent feature definitions."""


@dataclass(frozen=True, order=True)
class FeatureRef:
    view: str
    feature: str

    @classmethod
    def parse(cls, ref: str) -> FeatureRef:
        view, sep, feature = ref.partition(":")
        if not sep or not view or not feature:
            raise ValueError(f"Invalid feature reference {ref!r}; expected 'view:feature'")
        return cls(view, feature)

    def __str__(self) -> str:
        return f"{self.view}:{self.feature}"


class FeatureRegistry:
    def __init__(self, project: str = "default") -> None:
        self.project = project
        self._entities: dict[str, Entity] = {}
        self._views: dict[str, BaseFeatureView] = {}
        self._services: dict[str, FeatureService] = {}

    # -- writing ---------------------------------------------------------------
    def apply(self, *objects: Definition | Iterable[Definition]) -> None:
        """Register (or replace) definitions, resolving and validating the whole graph.

        Upstream views and entities referenced by object are registered
        implicitly, so applying a derived view is enough to pull in its
        dependencies.
        """
        entities, views, services = dict(self._entities), dict(self._views), dict(self._services)

        def add_entity(entity: Entity) -> None:
            existing = entities.get(entity.name)
            if existing is not None and existing != entity:
                raise RegistryError(f"Conflicting definitions for entity {entity.name!r}")
            entities[entity.name] = entity

        def add_view(view: BaseFeatureView, explicit: bool) -> None:
            existing = views.get(view.name)
            if existing is not None and existing is not view and not explicit:
                return  # an upstream object reference; an explicit definition wins
            views[view.name] = view
            for entity in view.entities:
                add_entity(entity)
            for upstream in view.upstream:
                if isinstance(upstream, BaseFeatureView):
                    add_view(upstream, explicit=False)

        for obj in _flatten(objects):
            if isinstance(obj, Entity):
                add_entity(obj)
            elif isinstance(obj, BaseFeatureView):
                add_view(obj, explicit=True)
            elif isinstance(obj, FeatureService):
                services[obj.name] = obj
            else:
                raise TypeError(f"Cannot apply object of type {type(obj).__name__}")

        order = _topological_order(views)

        def lookup(name: str) -> BaseFeatureView:
            try:
                return views[name]
            except KeyError:
                raise RegistryError(f"Unknown upstream feature view {name!r}") from None

        for name in order:
            view = views[name]
            if isinstance(view, _TransformedView):
                view.bind(lookup)
                for entity in view.entities:
                    add_entity(entity)

        for name in order:
            _validate_view(views[name])

        self._entities, self._views, self._services = entities, views, services
        for service in services.values():
            self.resolve_features(service.feature_refs)

    # -- reading ---------------------------------------------------------------
    def get_entity(self, name: str) -> Entity:
        return _get(self._entities, name, "entity")

    def get_view(self, name: str) -> BaseFeatureView:
        return _get(self._views, name, "feature view")

    def get_service(self, name: str) -> FeatureService:
        return _get(self._services, name, "feature service")

    def list_entities(self) -> list[Entity]:
        return list(self._entities.values())

    def list_views(self) -> list[BaseFeatureView]:
        return [self._views[n] for n in _topological_order(self._views)]

    def list_services(self) -> list[FeatureService]:
        return list(self._services.values())

    def resolve_features(self, features: Sequence[str | Sequence[str]]) -> list[FeatureRef]:
        """Turn ``["view:a", "view:*", view[["b"]]]`` into concrete, de-duplicated refs."""
        refs: list[FeatureRef] = []
        for entry in features:
            for raw in [entry] if isinstance(entry, str) else entry:
                ref = FeatureRef.parse(raw)
                view = self.get_view(ref.view)
                names = view.feature_names if ref.feature == "*" else [ref.feature]
                for name in names:
                    view.field(name)  # raises a helpful KeyError for unknown features
                    resolved = FeatureRef(view.name, name)
                    if resolved not in refs:
                        refs.append(resolved)
        return refs

    def dependency_closure(self, view_names: Iterable[str]) -> list[BaseFeatureView]:
        """The given views plus everything upstream of them, dependencies first."""
        needed: set[str] = set()

        def visit(name: str) -> None:
            if name in needed:
                return
            needed.add(name)
            for upstream in self.get_view(name).upstream:
                visit(upstream if isinstance(upstream, str) else upstream.name)

        for name in view_names:
            visit(name)
        return [v for v in self.list_views() if v.name in needed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "entities": [e.to_dict() for e in self.list_entities()],
            "feature_views": [v.describe() for v in self.list_views()],
            "feature_services": [s.describe() for s in self.list_services()],
        }


def _flatten(objects: Iterable[Any]) -> Iterable[Any]:
    for obj in objects:
        if isinstance(obj, Entity | BaseFeatureView | FeatureService):
            yield obj
        elif isinstance(obj, Iterable) and not isinstance(obj, str | bytes):
            yield from _flatten(obj)
        else:
            yield obj


def _get(items: dict[str, Any], name: str, kind: str) -> Any:
    try:
        return items[name]
    except KeyError:
        raise KeyError(f"Unknown {kind} {name!r}. Known: {sorted(items)}") from None


def _topological_order(views: dict[str, BaseFeatureView]) -> list[str]:
    order: list[str] = []
    state: dict[str, str] = {}  # name -> "visiting" | "done"

    def visit(name: str, path: list[str]) -> None:
        if state.get(name) == "done":
            return
        if state.get(name) == "visiting":
            cycle = " -> ".join([*path[path.index(name) :], name])
            raise RegistryError(f"Feature views form a cycle: {cycle}")
        if name not in views:
            raise RegistryError(f"Feature view {path[-1]!r} depends on unknown view {name!r}")
        state[name] = "visiting"
        for upstream in views[name].upstream:
            visit(upstream if isinstance(upstream, str) else upstream.name, [*path, name])
        state[name] = "done"
        order.append(name)

    for name in sorted(views):
        visit(name, [])
    return order


def _validate_view(view: BaseFeatureView) -> None:
    if isinstance(view, FeatureView | DerivedFeatureView) and not view.entities:
        raise RegistryError(f"Feature view {view.name!r} has no entities")

    if isinstance(view, DerivedFeatureView):
        primary, *others = view.resolved_sources
        if isinstance(primary, OnDemandFeatureView) or any(
            isinstance(o, OnDemandFeatureView) for o in others
        ):
            raise RegistryError(
                f"Derived view {view.name!r} cannot depend on on-demand views; "
                "make it an on-demand view instead"
            )
        columns = {*primary.join_keys}
        _check_disjoint(view, columns, primary)
        columns |= set(primary.feature_names)
        for other in others:
            missing = [k for k in other.join_keys if k not in columns]
            if missing:
                raise RegistryError(
                    f"Derived view {view.name!r}: upstream {other.name!r} is joined on {missing}, "
                    f"which the spine built from {primary.name!r} does not provide"
                )
            _check_disjoint(view, columns, other)
            columns |= set(other.feature_names)

    if isinstance(view, OnDemandFeatureView):
        columns = {f.name for f in view.request_schema}
        for upstream in view.resolved_sources:
            _check_disjoint(view, columns, upstream)
            columns |= set(upstream.feature_names)


def _check_disjoint(view: BaseFeatureView, columns: set[str], upstream: BaseFeatureView) -> None:
    clash = columns & set(upstream.feature_names)
    if clash:
        raise RegistryError(
            f"View {view.name!r}: feature names {sorted(clash)} from upstream {upstream.name!r} "
            "collide with other inputs; rename them in one of the upstream views"
        )
