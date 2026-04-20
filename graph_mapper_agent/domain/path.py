from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PathStep:
    path_step_id: str
    node_id: str
    canonical_url: str
    arrival_context_id: str
    depth: int = 0
    via_edge_id: str | None = None
    status: str = "active"


@dataclass(slots=True)
class ActivePathState:
    anchor_id: str
    steps: tuple[PathStep, ...] = ()

    def append_step(self, step: PathStep) -> None:
        self.steps = (*self.steps, step)

    def tip(self) -> PathStep | None:
        if not self.steps:
            return None
        return self.steps[-1]

    def close_suffix_from(self, path_step_id: str) -> None:
        closing = False
        updated: list[PathStep] = []
        for step in self.steps:
            if step.path_step_id == path_step_id:
                closing = True
            if closing:
                updated.append(
                    PathStep(
                        path_step_id=step.path_step_id,
                        node_id=step.node_id,
                        canonical_url=step.canonical_url,
                        arrival_context_id=step.arrival_context_id,
                        depth=step.depth,
                        via_edge_id=step.via_edge_id,
                        status="closed",
                    )
                )
            else:
                updated.append(step)
        self.steps = tuple(updated)

    def rebuild_from_prefix(self, path_step_id: str) -> "ActivePathState":
        rebuilt: list[PathStep] = []
        for step in self.steps:
            rebuilt.append(
                PathStep(
                    path_step_id=step.path_step_id,
                    node_id=step.node_id,
                    canonical_url=step.canonical_url,
                    arrival_context_id=step.arrival_context_id,
                    depth=step.depth,
                    via_edge_id=step.via_edge_id,
                    status="active",
                )
            )
            if step.path_step_id == path_step_id:
                break
        return ActivePathState(anchor_id=self.anchor_id, steps=tuple(rebuilt))


@dataclass(slots=True)
class ChoicePointState:
    choice_point_id: str
    scope_id: str
    origin_path_step_id: str
    from_node_id: str
    edge_id: str
    target_url: str
    label: str = ""
    priority: float = 0.0
    discovery_reason: str | None = None
    status: str = "open"


@dataclass(slots=True)
class StrategicAnchorPointState:
    anchor_point_id: str
    scope_id: str
    node_id: str
    canonical_url: str
    origin_path_step_id: str
    priority: float = 0.0
    reason: str | None = None
    source: str = "navigation_perception"
    status: str = "open"
