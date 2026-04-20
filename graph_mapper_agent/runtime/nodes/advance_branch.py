from __future__ import annotations
#graph_mapper_agent/runtime/nodes/advance_branch.py
from typing import Any

from graph_mapper_agent.domain.exploration_scope import (
    ExplorationScopeState,
)
from graph_mapper_agent.domain.path import (
    ChoicePointState,
    StrategicAnchorPointState,
)
from graph_mapper_agent.runtime.nodes.choice_points import (
    safe_rebuild_path,
)
from graph_mapper_agent.runtime.state import GraphMapperState


def log_after(runtime: GraphMapperState, *, route_hint: str) -> None:
    current_node = (
        runtime.graph.get_node(runtime.current_node_id)
        if runtime.current_node_id
        else None
    )
    print(
        "[advance_branch_helpers] AFTER "
        f"active_scope_id={runtime.active_scope_id!r} "
        f"current_node_id={runtime.current_node_id!r} "
        f"current_node_exhausted={current_node.exhausted if current_node is not None else None!r} "
        f"choice_points_count={len(runtime.visible_choice_points())} "
        f"route_hint={route_hint!r}",
        flush=True,
    )


def resume_via_strategic_anchor(
    *,
    runtime: GraphMapperState,
    scope: ExplorationScopeState,
    anchor_point: StrategicAnchorPointState,
) -> None:
    scope.current_node_id = anchor_point.node_id
    runtime.current_node_id = anchor_point.node_id

    safe_rebuild_path(runtime, anchor_point.origin_path_step_id)

    anchor_point.status = "resumed"
    runtime.tactical_scratchpad.add_note(
        "Backjump: resumed strategic anchor point to pivot into a different branch."
    )
    scope.register_progress(
        f"resume_strategic_anchor:{anchor_point.anchor_point_id}"
    )

    print(
        "[advance_branch_helpers] RESUME STRATEGIC ANCHOR "
        f"scope_id={scope.scope_id!r} "
        f"node_id={runtime.current_node_id!r} "
        f"anchor_point_id={anchor_point.anchor_point_id!r}",
        flush=True,
    )


def resume_via_choice_point(
    *,
    runtime: GraphMapperState,
    scope: ExplorationScopeState,
    choice_point: ChoicePointState,
) -> dict[str, object] | None:
    scope.current_node_id = choice_point.from_node_id
    runtime.current_node_id = choice_point.from_node_id
    safe_rebuild_path(runtime, choice_point.origin_path_step_id)

    edge = runtime.graph.get_edge(choice_point.edge_id)
    fallback_reason: str | None = None

    if edge is None:
        fallback_reason = f"EDGE MISSING edge_id={choice_point.edge_id!r}"
    elif edge.from_node_id != choice_point.from_node_id:
        fallback_reason = (
            f"EDGE/ORIGIN MISMATCH edge.from={edge.from_node_id!r} "
            f"cp.from={choice_point.from_node_id!r}"
        )
    elif edge.status in {"failed", "blocked", "rejected"}:
        fallback_reason = f"EDGE NOT EXECUTABLE status={edge.status!r}"

    choice_point.status = "resumed"

    if fallback_reason is not None:
        print(
            f"[advance_branch_helpers] CHOICE POINT {fallback_reason} "
            f"choice_point_id={choice_point.choice_point_id!r} - "
            "falling back to inspect_node",
            flush=True,
        )
        target_node = runtime.graph.get_node(choice_point.from_node_id)
        if target_node is not None:
            runtime.tactical_scratchpad.add_note(
                "Backtracking: resumed recoverable choice point after local exhaustion "
                "(edge not directly executable)."
            )
        scope.register_progress(
            f"resume_choice_point:{choice_point.choice_point_id}"
        )
        print(
            "[advance_branch_helpers] RESUME CHOICE POINT (fallback) "
            f"scope_id={scope.scope_id!r} "
            f"current_node_id={runtime.current_node_id!r}",
            flush=True,
        )
        return None

    runtime.tactical_scratchpad.add_note(
        "Backtracking: resumed recoverable choice point and executing saved edge directly."
    )
    scope.register_progress(
        f"resume_choice_point:{choice_point.choice_point_id}"
    )

    runtime.last_decision = {
        "action": "follow_edge",
        "edge_id": choice_point.edge_id,
        "decision_rationale": f"resume_choice_point:{choice_point.choice_point_id}",
        "confidence": 0.90,
        "scratchpad_update": None,
    }

    print(
        "[advance_branch_helpers] RESUME CHOICE POINT DIRECT EXECUTION "
        f"scope_id={scope.scope_id!r} "
        f"current_node_id={runtime.current_node_id!r} "
        f"edge_id={choice_point.edge_id!r} "
        f"target_url={choice_point.target_url!r}",
        flush=True,
    )

    log_after(runtime, route_hint="execute_action")

    return {
        "runtime": runtime,
        "route_hint": "execute_action",
    }


def restart_from_anchor_root(
    *,
    runtime: GraphMapperState,
    scope: ExplorationScopeState,
) -> None:
    if runtime.anchor is None:
        return

    scope.current_node_id = runtime.anchor.root_node_id
    runtime.current_node_id = runtime.anchor.root_node_id

    if runtime.active_path is not None and runtime.active_path.steps:
        safe_rebuild_path(runtime, runtime.active_path.steps[0].path_step_id)

    runtime.tactical_scratchpad.add_note(
        "Restarted exploration from anchor root after exhausting current branch."
    )
    print(
        "[advance_branch_helpers] RESTART ANCHOR ROOT "
        f"scope_id={scope.scope_id!r} "
        f"root_node_id={runtime.current_node_id!r}",
        flush=True,
    )


def apply_branch_resumption(
    *,
    runtime: GraphMapperState,
    scope: ExplorationScopeState,
    decision: Any,
    choice_point: ChoicePointState | None,
    strategic_anchor_point: StrategicAnchorPointState | None,
) -> dict[str, object] | None:
    if strategic_anchor_point is not None:
        resume_via_strategic_anchor(
            runtime=runtime,
            scope=scope,
            anchor_point=strategic_anchor_point,
        )
        return None

    if choice_point is not None:
        return resume_via_choice_point(
            runtime=runtime,
            scope=scope,
            choice_point=choice_point,
        )

    if scope.current_node_id:
        if decision.reason == "restart_from_anchor_root" and runtime.anchor is not None:
            restart_from_anchor_root(runtime=runtime, scope=scope)
        else:
            runtime.current_node_id = scope.current_node_id
            print(
                "[advance_branch_helpers] REUSE BRANCH CURRENT NODE "
                f"scope_id={scope.scope_id!r} "
                f"current_node_id={runtime.current_node_id!r}",
                flush=True,
            )

    return None


def finalize_advance_branch(
    runtime: GraphMapperState,
    decision: Any,
) -> dict[str, object]:
    log_after(runtime, route_hint=decision.next_route)

    current_node = (
        runtime.graph.get_node(runtime.current_node_id)
        if runtime.current_node_id
        else None
    )

    if decision.next_route == "inspect_node":
        scope = runtime.get_active_scope()
        if (
            scope is not None
            and current_node is not None
            and current_node.exhausted
            and scope.current_node_id == runtime.current_node_id
        ):
            print(
                "[advance_branch_helpers] GUARDRAIL "
                "refusing inspect_node on same exhausted node; forcing fail-safe",
                flush=True,
            )
            return {
                "runtime": runtime,
                "route_hint": "fail",
            }

    return {
        "runtime": runtime,
        "route_hint": decision.next_route,
    }


__all__ = [
    "apply_branch_resumption",
    "finalize_advance_branch",
    "log_after",
    "restart_from_anchor_root",
    "resume_via_choice_point",
    "resume_via_strategic_anchor",
]
