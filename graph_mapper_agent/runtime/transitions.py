from __future__ import annotations
#graph_mapper_agent/runtime/transitions.py
from graph_mapper_agent.navigation.runtime.engine import (
    TransitionDefinition,
)


def route_after_execute_action(state: dict[str, object]) -> str:
    """
    Router after execute_action.

    Priority:
    1. use route_hint if the step made it explicit
    2. follow to update_graph by default
    """
    route_hint = str(state.get("route_hint") or "").strip()
    if route_hint:
        return route_hint
    return "update_graph"


def route_after_advance_branch(state: dict[str, object]) -> str:
    """
    Router after advance_branch.

    Expects the step to be able to decide:
    - success
    - fail
    - inspect_node
    """
    route_hint = str(state.get("route_hint") or "").strip()
    if route_hint:
        return route_hint
    return "inspect_node"


def build_transitions(nodes: object) -> dict[str, TransitionDefinition]:
    """
    Builds the state machine for the graph_mapper track.

    It is expected that `nodes` exposes callable methods with a compatible signature:
      step(state) -> Mapping[str, object] | None
    """

    return {
        "bootstrap": TransitionDefinition(
            step=nodes.bootstrap,
            next_step="inspect_node",
        ),
        "inspect_node": TransitionDefinition(
            step=nodes.inspect_node,
            next_step="classify_node",
        ),
        "classify_node": TransitionDefinition(
            step=nodes.classify_node,
            next_step="build_node_view",
        ),
        "build_node_view": TransitionDefinition(
            step=nodes.build_node_view,
            next_step="decide_action",
        ),
        "decide_action": TransitionDefinition(
            step=nodes.decide_action,
            next_step="execute_action",
        ),
        "execute_action": TransitionDefinition(
            step=nodes.execute_action,
            router=route_after_execute_action,
        ),
        "update_graph": TransitionDefinition(
            step=nodes.update_graph,
            next_step="advance_branch",
        ),
        "advance_branch": TransitionDefinition(
            step=nodes.advance_branch,
            router=route_after_advance_branch,
        ),
        "success": TransitionDefinition(
            step=nodes.success,
        ),
        "fail": TransitionDefinition(
            step=nodes.fail,
        ),
    }


TERMINAL_STATES: set[str] = {"success", "fail"}
START_STATE = "bootstrap"
