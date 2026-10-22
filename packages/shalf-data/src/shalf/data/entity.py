from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shalf.data.types import ValueType


@dataclass(frozen=True)
class Entity:
    """The "who/what" features describe (a customer, a merchant, ...).

    Each entity has exactly one join key. Feature views keyed on several
    entities (e.g. customer x merchant) simply list several entities, which
    yields a composite key.
    """

    name: str
    join_key: str | None = None
    value_type: ValueType = ValueType.INT64
    description: str = ""
    tags: dict[str, str] = field(default_factory=dict, hash=False, compare=False)

    @property
    def key(self) -> str:
        return self.join_key or self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "join_key": self.key,
            "value_type": self.value_type.value,
            "description": self.description,
            "tags": dict(self.tags),
        }
