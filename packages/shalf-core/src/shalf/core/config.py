"""YAML config loading with ``${VAR}`` / ``${VAR:-default}`` env interpolation.

The same config file can therefore be used locally and in Kubernetes, where
secrets and endpoints arrive as environment variables.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from shalf.core.errors import ConfigError

_ENV_PATTERN = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::-(?P<default>[^}]*))?\}")


def interpolate_env(value: Any) -> Any:
    """Recursively replace ``${VAR}`` and ``${VAR:-default}`` in strings."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name, default = match.group("name"), match.group("default")
            if name in os.environ:
                return os.environ[name]
            if default is not None:
                return default
            raise ConfigError(f"Environment variable {name!r} is not set and has no default")

        return _ENV_PATTERN.sub(replace, value)
    if isinstance(value, dict):
        return {k: interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate_env(v) for v in value]
    return value


def load_yaml(path: str | Path, *, interpolate: bool = True) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must contain a mapping at the top level")
    return interpolate_env(data) if interpolate else data
