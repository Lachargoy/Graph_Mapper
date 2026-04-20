from __future__ import annotations
#graph_mapper_agent/runtime/nodes/build_view_helpers.py
from graph_mapper_agent.runtime.nodes.choice_points import (
    strategic_anchor_point_from_navigation_perception,
)
from graph_mapper_agent.runtime.state import GraphMapperState
from graph_mapper_agent.runtime.state.navigation import (
    ensure_navigation_perception_refine_state,
)
from graph_mapper_agent.runtime.state.validation import (
    current_node_validation_capability,
    ensure_document_validation_node_state,
)
from graph_mapper_agent.runtime.state.validation_target import (
    build_validation_target_for_node,
)
from graph_mapper_agent.application.services.navigation_perception import (
    navigation_perception_context_signature,
)


def run_navigation_perception_if_needed(
    *,
    navigation_perception_coordinator,
    runtime: GraphMapperState,
    node,
    scope,
    evaluated_goal_trace,
) -> object | None:
    if navigation_perception_coordinator is None:
        return None

    return navigation_perception_coordinator.run_if_needed(
        runtime=runtime,
        node=node,
        goal_context=scope.goal_context,
        goal_trace=evaluated_goal_trace,
        findings=tuple(runtime.findings.values()),
    )


def resolve_arrival_context(
    *,
    runtime: GraphMapperState,
    scope,
    node,
):
    arrival = None
    arrival_context_id = scope.current_arrival_context_id or node.last_arrival_context_id
    if arrival_context_id:
        arrival = runtime.arrival_contexts.get(arrival_context_id)
    return arrival


def maybe_register_strategic_anchor_from_navigation_perception(
    *,
    runtime: GraphMapperState,
    scope,
    node,
    navigation_perception_result,
) -> None:
    if navigation_perception_result is None:
        return

    strategic_point = strategic_anchor_point_from_navigation_perception(
        runtime=runtime,
        scope=scope,
        node=node,
        navigation_perception=navigation_perception_result,
    )
    if strategic_point is not None:
        runtime.register_strategic_anchor_point(strategic_point)


def resolve_node_view_capabilities(
    *,
    runtime: GraphMapperState,
    node,
    all_edges_from_node,
    evaluated_goal_trace,
    can_validate: bool,
) -> tuple[object, object, bool, str | None]:
    current_context_signature = navigation_perception_context_signature(
        node=node,
        goal_trace=evaluated_goal_trace,
        all_edges_from_node=all_edges_from_node,
    )

    refine_state = ensure_navigation_perception_refine_state(
        runtime=runtime,
        node_id=node.node_id,
        current_context_signature=current_context_signature,
    )

    document_validation_state = ensure_document_validation_node_state(
        runtime=runtime,
        node_id=node.node_id,
    )

    can_validate_current_content, validate_current_content_reason = (
        current_node_validation_capability(
            runtime=runtime,
            node_id=node.node_id,
            document_validation_state=document_validation_state,
            can_validate=can_validate,
            build_validation_target_for_node=build_validation_target_for_node,
        )
    )

    return (
        refine_state,
        document_validation_state,
        can_validate_current_content,
        validate_current_content_reason,
    )


def build_current_node_view(
    *,
    node_view_builder,
    runtime: GraphMapperState,
    node,
    scope,
    arrival,
    pending_edges,
    all_edges_from_node,
    evaluated_goal_trace,
    navigation_perception_result,
    document_validation_state,
    refine_state,
    can_validate_current_content: bool,
    validate_current_content_reason: str | None,
):
    choice_points = runtime.visible_choice_points(scope.scope_id)
    strategic_return_point = runtime.best_strategic_anchor_point(scope_id=scope.scope_id)

    node_view = node_view_builder.build(
        node=node,
        scope=scope,
        pending_edges=pending_edges,
        all_edges_from_node=all_edges_from_node,
        arrival=arrival,
        choice_points=choice_points,
        goal_trace=evaluated_goal_trace,
        anchor=runtime.anchor,
        active_path=runtime.active_path,
        findings=tuple(runtime.findings.values()),
        tactical_scratchpad=runtime.tactical_scratchpad,
        choice_points_count=len(runtime.choice_points),
        navigation_perception=navigation_perception_result,
        last_artifact_result=runtime.last_artifact_result,
        last_inspection_result=runtime.last_inspection_result,
        current_node_goal_validation=runtime.goal_validation_payload_by_node.get(node.node_id),
        current_node_goal_validation_state=document_validation_state,
        strategic_return_point=strategic_return_point,
        can_refine_navigation_perception=refine_state.can_refine,
        refine_navigation_perception_reason=refine_state.reason,
        can_validate_current_content=can_validate_current_content,
        validate_current_content_reason=validate_current_content_reason,
        current_inspection_result=runtime.inspection_result_by_node.get(node.node_id),
        current_search_history=runtime.search_history_by_node.get(node.node_id, ()),
    )

    runtime.last_node_view = node_view
    return node_view


__all__ = [
    "build_current_node_view",
    "maybe_register_strategic_anchor_from_navigation_perception",
    "resolve_arrival_context",
    "resolve_node_view_capabilities",
    "run_navigation_perception_if_needed",
]
