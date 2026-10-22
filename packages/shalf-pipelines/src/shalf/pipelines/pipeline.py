from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from graphlib import TopologicalSorter
from typing import Any


@dataclass
class Step:
    name: str
    fn: Callable[..., Any]
    depends_on: list[str] = field(default_factory=list)
    image: str | None = None  # container image when compiled for Kubernetes
    resources: dict[str, str] = field(default_factory=dict)


@dataclass
class Pipeline:
    name: str
    steps: list[Step] = field(default_factory=list)

    def step(self, name: str | None = None, depends_on: list[str] | None = None) -> Callable:
        def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.steps.append(Step(name or fn.__name__, fn, list(depends_on or [])))
            return fn

        return wrap

    def order(self) -> list[Step]:
        by_name = {s.name: s for s in self.steps}
        graph = {s.name: set(s.depends_on) for s in self.steps}
        return [by_name[n] for n in TopologicalSorter(graph).static_order()]


class LocalRunner:
    """Runs steps in-process in dependency order. Each step gets its deps' outputs as kwargs."""

    def run(self, pipeline: Pipeline) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        for step in pipeline.order():
            outputs[step.name] = step.fn(**{d: outputs[d] for d in step.depends_on})
        return outputs
