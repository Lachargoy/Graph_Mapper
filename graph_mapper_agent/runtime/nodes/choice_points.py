from __future__ import annotations
#graph_mapper_agent/runtime/nodes/choice_points.py
from uuid import uuid4

from graph_mapper_agent.domain.exploration_scope import (
    ExplorationScopeState,
)
from graph_mapper_agent.application.services.goals.alignment import (
    goal_aligned_priority,
    pending_years_from_goal_trace,
    year_alignment_score,
)
from graph_mapper_agent.domain.path import (
    ChoicePointState,
    StrategicAnchorPointState,
)
from graph_mapper_agent.runtime.state import GraphMapperState


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def choice_point_already_contains(
    runtime: GraphMapperState,
    scope_id: str,
    target_url: str,
) -> bool:
    for item in runtime.visible_choice_points():
        if item.scope_id == scope_id and item.target_url == target_url:
            return True
    return False


def safe_rebuild_path(runtime: GraphMapperState, origin_step_id: str) -> None:
    if runtime.active_path is None:
        return

    step_ids = {s.path_step_id for s in runtime.active_path.steps}
    if origin_step_id not in step_ids:
        print(
            f"[choice_point_helpers.safe_rebuild_path] WARN "
            f"origin_step_id={origin_step_id!r} not found in "
            f"active_path ({len(runtime.active_path.steps)} steps) - "
            "keeping path intact",
            flush=True,
        )
        return

    runtime.active_path = runtime.active_path.rebuild_from_prefix(origin_step_id)


def strategic_anchor_point_from_navigation_perception(
    *,
    runtime: GraphMapperState,
    scope: ExplorationScopeState,
    node,
    navigation_perception,
) -> StrategicAnchorPointState | None:
    if navigation_perception is None:
        return None
    if navigation_perception.strategic_return_suggested is not True:
        return None
    if node is None or node.exhausted:
        return None
    if not node.has_pending_edges() and node.visited_count <= 0:
        return None

    path_tip = runtime.active_path.tip() if runtime.active_path is not None else None
    if path_tip is None:
        return None

    priority = navigation_perception.strategic_return_priority
    if priority is None:
        priority = 0.0

    return StrategicAnchorPointState(
        anchor_point_id=_new_id("sap"),
        scope_id=scope.scope_id,
        node_id=node.node_id,
        canonical_url=node.canonical_url,
        origin_path_step_id=path_tip.path_step_id,
        priority=float(priority),
        reason=optional_str(navigation_perception.strategic_return_reason),
        source="navigation_perception",
    )


def seed_choice_points_from_non_selected_candidates(
    *,
    runtime: GraphMapperState,
    node_view,
    decision: dict[str, object],
    branching_factor: int = 3,
) -> None:
    action = str(decision.get("action") or "").strip()
    chosen_edge_id = optional_str(decision.get("edge_id"))

    if action not in {"follow_edge", "download_artifact", "open_artifact"}:
        return
    if not chosen_edge_id:
        return

    active_scope = runtime.get_active_scope()
    if active_scope is None or not active_scope.current_node_id:
        return

    parent_node_id = active_scope.current_node_id

    path_tip = runtime.active_path.tip() if runtime.active_path is not None else None
    if path_tip is None:
        print(
            "[nodes.choice_points] WARN path_tip is None - cannot seed any choice points",
            flush=True,
        )
        return

    alternatives = [
        c
        for c in node_view.candidates
        if c.edge_id != chosen_edge_id
        and c.status not in {"failed", "blocked", "rejected"}
        and c.attempt_count < 2
    ]

    if not alternatives:
        print(
            "[nodes.choice_points] no alternatives to seed",
            flush=True,
        )
        return

    pending_years = pending_years_from_goal_trace(runtime.evaluated_goal_trace())

    alternatives.sort(
        key=lambda c: (
            year_alignment_score(
                str(getattr(c, "target_url", "") or ""),
                str(getattr(c, "label", "") or ""),
                pending_years,
            ),
            c.base_score if c.base_score is not None else 0.0,
            -c.attempt_count,
        ),
        reverse=True,
    )

    seeded = 0
    for candidate in alternatives:
        if seeded >= branching_factor:
            break

        edge = runtime.graph.get_edge(candidate.edge_id)
        if edge is None:
            continue

        if choice_point_already_contains(runtime, active_scope.scope_id, edge.target_url):
            continue

        priority = goal_aligned_priority(
            base_score=float(candidate.base_score or 0.0),
            target_url=edge.target_url,
            label=edge.label or "",
            pending_years=pending_years,
        )

        choice_point = ChoicePointState(
            choice_point_id=_new_id("cp"),
            scope_id=active_scope.scope_id,
            origin_path_step_id=path_tip.path_step_id,
            from_node_id=parent_node_id,
            edge_id=edge.edge_id,
            target_url=edge.target_url,
            label=edge.label or "",
            priority=priority,
            discovery_reason=(
                f"non_selected_candidate:{candidate.reason or 'alternative_path'}"
            ),
        )

        print(
            f"[nodes.choice_points] seeded choice_point={choice_point.choice_point_id} "
            f"edge_id={edge.edge_id} target_url={edge.target_url} "
            f"priority={choice_point.priority} pending_years={pending_years}",
            flush=True,
        )

        runtime.register_choice_point(choice_point)
        seeded += 1


__all__ = [
    "choice_point_already_contains",
    "optional_str",
    "safe_rebuild_path",
    "seed_choice_points_from_non_selected_candidates",
    "strategic_anchor_point_from_navigation_perception",
]
