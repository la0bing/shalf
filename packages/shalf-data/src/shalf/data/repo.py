"""Load feature definitions from a *feature repository* directory.

A feature repo is a directory with a ``shalf.yaml`` and one or more Python
modules declaring entities, views and services at module level. The repo
directory is put on ``sys.path`` so modules can import each other
(``from entities import customer``).
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence
from pathlib import Path

from shalf.data.entity import Entity
from shalf.data.feature_service import FeatureService
from shalf.data.feature_view import BaseFeatureView
from shalf.data.registry import Definition


def load_definitions(repo_path: str | Path, modules: Sequence[str]) -> list[Definition]:
    repo = Path(repo_path).resolve()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    files: list[Path] = []
    for entry in modules:
        path = (repo / entry).resolve()
        if path.is_dir():
            files.extend(sorted(p for p in path.rglob("*.py") if p.name != "__init__.py"))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"Definitions path {entry!r} not found in {repo}")

    seen: set[int] = set()
    objects: list[Definition] = []
    for file in files:
        module_name = ".".join(file.relative_to(repo).with_suffix("").parts)
        cached = sys.modules.get(module_name)
        if cached is not None and Path(getattr(cached, "__file__", "") or "").resolve() != file:
            del sys.modules[module_name]  # same name, different repo: don't reuse it
        module = importlib.import_module(module_name)
        for value in vars(module).values():
            if (
                isinstance(value, Entity | BaseFeatureView | FeatureService)
                and id(value) not in seen
            ):
                seen.add(id(value))
                objects.append(value)
    return objects
