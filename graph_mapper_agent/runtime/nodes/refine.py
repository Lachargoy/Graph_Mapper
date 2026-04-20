from __future__ import annotations

from graph_mapper_agent.runtime.state import (
    GraphMapperState,
    NavigationPerceptionRefineState,
)
from graph_mapper_agent.runtime.state.access import (
    require_active_scope,
    require_current_node,
)
from graph_mapper_agent.application.services.navigation_perception import (
    navigation_perception_context_signature,
    navigation_perception_result_signature,
)


def execute_refine_navigation_perception(
    *,
    runtime: GraphMapperState,
    navigation_perception_coordinator,
) -> dict[str, object]:
    if navigation_perception_coordinator is None:
        raise RuntimeError(
            "refine_navigation_perception requires navigation_perception_coordinator"
        )

    scope = require_active_scope(runtime)
    node = require_current_node(runtime)
    evaluated_goal_trace = runtime.evaluated_goal_trace()

    all_edges_before = runtime.graph.edges_from_node(node.node_id)
    context_signature = navigation_perception_context_signature(
        node=node,
        goal_trace=evaluated_goal_trace,
        all_edges_from_node=all_edges_before,
    )

    previous_result = runtime.navigation_perception_by_node.get(node.node_id)
    previous_signature = navigation_perception_result_signature(previous_result)
    explicit_runs_before = runtime.navigation_perception_explicit_runs_by_node.get(
        node.node_id, 0
    )

    result = navigation_perception_coordinator.run_explicit(
        runtime=runtime,
        node=node,
        goal_context=scope.goal_context,
        goal_trace=evaluated_goal_trace,
        findings=tuple(runtime.findings.values()),
    )
    if result is None:
        result = previous_result

    explicit_runs_after = runtime.navigation_perception_explicit_runs_by_node.get(
        node.node_id, 0
    )
    merge_result = runtime.navigation_perception_merge_by_node.get(node.node_id)
    result_signature = navigation_perception_result_signature(result)

    executed_new_refine = explicit_runs_after > explicit_runs_before
    produced_new_delta = (
        executed_new_refine
        and (
            previous_signature != result_signature
            or bool(getattr(merge_result, "created_edge_ids", ()))
        )
    )

    refine_state = runtime.navigation_perception_refine_state_by_node.get(node.node_id)
    if refine_state is None:
        refine_state = NavigationPerceptionRefineState(node_id=node.node_id)
        runtime.navigation_perception_refine_state_by_node[node.node_id] = refine_state

    refine_state.explicit_runs = explicit_runs_after
    refine_state.last_context_signature = context_signature
    refine_state.last_result_signature = result_signature
    refine_state.last_explicit_refine_useful = produced_new_delta

    if produced_new_delta:
        refine_state.can_refine = True
        refine_state.reason = "ultimo_refine_explicito_si_aporto_delta_local"
    elif executed_new_refine:
        refine_state.can_refine = False
        refine_state.reason = "ultimo_refine_explicito_no_aporto_delta_nuevo_en_este_nodo"
    else:
        refine_state.can_refine = False
        refine_state.reason = "refine_navigation_perception_ya_no_aporta_valor_en_este_contexto"

    runtime.last_inspection_result = None
    runtime.last_download_result = None
    runtime.last_artifact_result = None

    layout_kind = getattr(result, "layout_kind", None)
    visible_candidate_count = getattr(result, "visible_candidate_count", None)
    print(
        "[refine_navigation_helpers] explicit navigation perception "
        f"node_id={node.node_id!r} "
        f"layout_kind={layout_kind!r} "
        f"visible_candidate_count={visible_candidate_count!r} "
        f"executed_new_refine={executed_new_refine!r} "
        f"produced_new_delta={produced_new_delta!r}",
        flush=True,
    )

    return {
        "runtime": runtime,
        "_action_result": {
            "action": "refine_navigation_perception",
            "status": "ok",
            "edge_id": None,
            "child_node_id": None,
            "inspection_result": None,
            "download_result": None,
            "artifact_result": None,
            "execution_reason": "navigation_perception_refined",
        },
        "route_hint": "build_node_view",
    }


__all__ = ["execute_refine_navigation_perception"]
