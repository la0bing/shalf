import pytest

from shalf.core import ConfigError, interpolate_env, load_yaml


def test_interpolation(monkeypatch):
    monkeypatch.setenv("HOST", "db.internal")
    monkeypatch.delenv("PORT", raising=False)
    value = {"dsn": "postgresql://${HOST}:${PORT:-5432}/x", "list": ["${HOST}"]}
    assert interpolate_env(value) == {
        "dsn": "postgresql://db.internal:5432/x",
        "list": ["db.internal"],
    }


def test_missing_variable(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    with pytest.raises(ConfigError):
        interpolate_env("${NOPE}")


def test_load_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT", "demo")
    path = tmp_path / "c.yaml"
    path.write_text("project: ${PROJECT}\n")
    assert load_yaml(path) == {"project": "demo"}
    with pytest.raises(ConfigError):
        load_yaml(tmp_path / "missing.yaml")
