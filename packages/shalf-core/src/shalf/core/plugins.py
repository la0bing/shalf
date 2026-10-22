"""A tiny, typed plugin registry.

Every extension point in shalf (data sources, online stores, offline stores,
transformations, model registries, ...) is a ``PluginRegistry``. Plugins can be
registered in two ways:

1. In code, with the decorator::

       @source_registry.register("bigquery")
       class BigQuerySource(DataSource): ...

2. From a separately installed package, via a Python entry point, so the
   framework picks it up without any code change::

       # pyproject.toml of the third-party package
       [project.entry-points."shalf.data.sources"]
       bigquery = "my_pkg.sources:BigQuerySource"

Entry points are loaded lazily, the first time a name is not found.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib.metadata import entry_points
from typing import Any, Generic, TypeVar

from shalf.core.errors import ConfigError, PluginNotFoundError

T = TypeVar("T")


class PluginRegistry(Generic[T]):
    def __init__(self, kind: str, base: type[T], entry_point_group: str | None = None) -> None:
        self.kind = kind
        self.base = base
        self.entry_point_group = entry_point_group
        self._plugins: dict[str, type[T]] = {}
        self._entry_points_loaded = False

    def register(self, name: str, *, override: bool = False) -> Callable[[type[T]], type[T]]:
        def decorator(cls: type[T]) -> type[T]:
            self.add(name, cls, override=override)
            return cls

        return decorator

    def add(self, name: str, cls: type[T], *, override: bool = False) -> None:
        if not (isinstance(cls, type) and issubclass(cls, self.base)):
            raise TypeError(f"{cls!r} is not a subclass of {self.base.__name__}")
        if name in self._plugins and not override and self._plugins[name] is not cls:
            raise ValueError(f"{self.kind} plugin {name!r} is already registered")
        self._plugins[name] = cls

    def get(self, name: str) -> type[T]:
        if name not in self._plugins:
            self._load_entry_points()
        try:
            return self._plugins[name]
        except KeyError:
            raise PluginNotFoundError(
                f"Unknown {self.kind} type {name!r}. Registered: {sorted(self._plugins)}"
            ) from None

    def create(self, config: Mapping[str, Any] | str, **overrides: Any) -> T:
        """Instantiate a plugin from ``{"type": name, **params}`` (or just a name).

        Classes may define ``from_config(cls, params)`` to customise construction;
        otherwise params are passed as keyword arguments.
        """
        if isinstance(config, str):
            config = {"type": config}
        params = dict(config)
        try:
            name = params.pop("type")
        except KeyError:
            raise ConfigError(f"{self.kind} config is missing a 'type' key: {config!r}") from None
        params.update(overrides)
        cls = self.get(name)
        factory = getattr(cls, "from_config", None)
        return factory(params) if callable(factory) else cls(**params)

    def names(self) -> list[str]:
        self._load_entry_points()
        return sorted(self._plugins)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self.names()

    def _load_entry_points(self) -> None:
        if self._entry_points_loaded or not self.entry_point_group:
            return
        self._entry_points_loaded = True
        for ep in entry_points(group=self.entry_point_group):
            if ep.name not in self._plugins:
                self.add(ep.name, ep.load())
