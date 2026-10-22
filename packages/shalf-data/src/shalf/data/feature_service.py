from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from shalf.data.feature_view import BaseFeatureView


class FeatureService:
    """A named, versionable set of features consumed by one model.

    Training reads it offline and the model server reads it online, so both
    always agree on exactly which features (and in which order) a model uses.
    Entries may be feature refs (``"view:feature"``), lists of refs
    (``view[["a", "b"]]``) or whole views.
    """

    def __init__(
        self,
        *,
        name: str,
        features: Sequence[str | BaseFeatureView | Sequence[str]],
        description: str = "",
        owner: str = "",
        tags: Mapping[str, str] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.owner = owner
        self.tags = dict(tags or {})
        self.feature_refs: list[str] = []
        for entry in features:
            if isinstance(entry, BaseFeatureView):
                self.feature_refs.append(f"{entry.name}:*")
            elif isinstance(entry, str):
                self.feature_refs.append(entry)
            else:
                self.feature_refs.extend(entry)

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "features": self.feature_refs,
            "description": self.description,
            "owner": self.owner,
            "tags": self.tags,
        }

    def __repr__(self) -> str:
        return f"FeatureService(name={self.name!r})"
