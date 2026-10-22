import pytest

from shalf.core import ConfigError, PluginNotFoundError, PluginRegistry


class Base:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_register_and_create():
    registry = PluginRegistry("thing", Base)

    @registry.register("a")
    class A(Base):
        pass

    obj = registry.create({"type": "a", "x": 1}, y=2)
    assert isinstance(obj, A)
    assert obj.kwargs == {"x": 1, "y": 2}
    assert registry.names() == ["a"]


def test_from_config_hook_is_used():
    registry = PluginRegistry("thing", Base)

    @registry.register("b")
    class B(Base):
        @classmethod
        def from_config(cls, params):
            return cls(wrapped=params)

    assert registry.create("b").kwargs == {"wrapped": {}}


def test_errors():
    registry = PluginRegistry("thing", Base)
    with pytest.raises(PluginNotFoundError):
        registry.get("missing")
    with pytest.raises(ConfigError):
        registry.create({"x": 1})
    with pytest.raises(TypeError):
        registry.add("bad", int)  # type: ignore[arg-type]

    registry.add("a", Base)
    with pytest.raises(ValueError):
        registry.add("a", type("Other", (Base,), {}))
