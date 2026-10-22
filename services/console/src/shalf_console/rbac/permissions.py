"""Permissions are ``<module>.<action>`` strings declared by console modules.

Roles hold permission *patterns*: exact keys, ``<module>.*`` or ``*``.
Patterns are expanded against the catalog when evaluated, so a custom role
granted ``features.*`` automatically covers permissions a future version of
the features module adds.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

GLOBAL_SCOPE = "*"


@dataclass(frozen=True)
class Permission:
    key: str
    description: str
    module: str
    # Admin-type permissions only make sense globally; project-scoped bindings
    # never grant them.
    global_only: bool = False


class PermissionCatalog:
    def __init__(self) -> None:
        self._permissions: dict[str, Permission] = {}

    def add(self, *permissions: Permission) -> None:
        for permission in permissions:
            if not permission.key.startswith(permission.module + "."):
                raise ValueError(f"{permission.key!r} must start with {permission.module!r}.")
            self._permissions[permission.key] = permission

    def __contains__(self, key: object) -> bool:
        return key in self._permissions

    def __iter__(self):
        return iter(self._permissions.values())

    def get(self, key: str) -> Permission:
        return self._permissions[key]

    def validate_patterns(self, patterns: Iterable[str]) -> list[str]:
        """Return the patterns, or raise ValueError for ones matching nothing."""
        patterns = list(dict.fromkeys(patterns))
        unknown = [p for p in patterns if not any(matches(p, k) for k in self._permissions)]
        if unknown:
            raise ValueError(f"Unknown permissions: {unknown}")
        return patterns

    def by_module(self) -> dict[str, list[Permission]]:
        grouped: dict[str, list[Permission]] = {}
        for permission in self._permissions.values():
            grouped.setdefault(permission.module, []).append(permission)
        return grouped


def matches(pattern: str, key: str) -> bool:
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        return key.startswith(pattern[:-1])
    return pattern == key


def expand(patterns: Iterable[str], catalog: PermissionCatalog) -> set[str]:
    patterns = list(patterns)
    return {p.key for p in catalog if any(matches(pattern, p.key) for pattern in patterns)}


# Built-in roles: seeded on start-up, cannot be edited or deleted.
BUILTIN_ROLES: dict[str, tuple[str, list[str]]] = {
    "admin": ("Everything, including users, roles and access.", ["*"]),
    "ml-engineer": (
        "Operate features, pipelines, models and serving; read everything else.",
        ["features.*", "pipelines.*", "models.*", "serving.*", "training.*", "monitoring.*"],
    ),
    "data-scientist": (
        "Explore features and models, query serving; no rollouts.",
        [
            "features.read",
            "features.preview",
            "pipelines.read",
            "models.read",
            "serving.read",
            "serving.query",
            "training.read",
            "monitoring.read",
        ],
    ),
    "viewer": (
        "Read-only access to all modules.",
        [
            "features.read",
            "pipelines.read",
            "models.read",
            "serving.read",
            "training.read",
            "monitoring.read",
        ],
    ),
}
