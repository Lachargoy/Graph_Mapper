from __future__ import annotations
#graph_mapper_agent/runtime/nodes/decide_helpers.py
from graph_mapper_agent.runtime.state import (
    GraphMapperState,
    ValidationTargetRef,
)
from graph_mapper_agent.runtime.state.validation_target import (
    build_validation_target_for_node,
)


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_scratchpad_update(
    *,
    working_plan: str | None,
    tactical_observations: str | None,
) -> dict[str, str] | None:
    if not working_plan and not tactical_observations:
        return None
    return {
        "working_plan": working_plan,
        "tactical_observations": tactical_observations,
    }


def build_mark_exhausted_decision(
    *,
    reason: str,
    confidence: float,
    scratchpad_update: dict[str, str] | None,
) -> dict[str, object]:
    return {
        "action": "mark_exhausted",
        "edge_id": None,
        "search_target_id": None,
        "query_text": None,
        "decision_rationale": reason,
        "confidence": confidence,
        "validation_target": None,
        "scratchpad_update": scratchpad_update,
    }


def resolve_validation_target_guardrail(
    *,
    runtime: GraphMapperState,
    node_id: str,
    action: str,
    scratchpad_update: dict[str, str] | None,
) -> tuple[ValidationTargetRef | None, dict[str, object] | None]:
    if action != "validate_current_content":
        return None, None

    validation_target = build_validation_target_for_node(
        runtime=runtime,
        node_id=node_id,
    )

    if validation_target is None:
        decision = build_mark_exhausted_decision(
            reason=(
                "validate_current_content_requested_but_no_frozen_validation_target_available"
            ),
            confidence=0.40,
            scratchpad_update=scratchpad_update,
        )
        return None, decision

    return validation_target, None


def resolve_edge_guardrail(
    *,
    runtime: GraphMapperState,
    action: str,
    raw_edge_id: str | None,
    scratchpad_update: dict[str, str] | None,
) -> dict[str, object] | None:
    if not raw_edge_id:
        return None

    if action not in {"follow_edge", "download_artifact", "open_artifact"}:
        return None

    edge = runtime.graph.get_edge(raw_edge_id)
    if edge is not None:
        return None

    return build_mark_exhausted_decision(
        reason=(
            "llm_referenced_non_existent_edge_id | "
            "converted_to_mark_exhausted_for_scope_resolution"
        ),
        confidence=0.35,
        scratchpad_update=scratchpad_update,
    )


def resolve_search_guardrail(
    *,
    node_view,
    action: str,
    raw_search_target_id: str | None,
    raw_query_text: str | None,
    scratchpad_update: dict[str, str] | None,
) -> dict[str, object] | None:
    if action != "search_with_text":
        return None

    available_search_target_ids = {
        str(getattr(t, "search_target_id", "")).strip()
        for t in (getattr(node_view, "search_targets", ()) or ())
        if str(getattr(t, "search_target_id", "")).strip()
    }

    if not raw_search_target_id or raw_search_target_id not in available_search_target_ids:
        return build_mark_exhausted_decision(
            reason="invalid_or_missing_search_target_id",
            confidence=0.35,
            scratchpad_update=scratchpad_update,
        )

    if not raw_query_text:
        return build_mark_exhausted_decision(
            reason="missing_query_text_for_search_with_text",
            confidence=0.35,
            scratchpad_update=scratchpad_update,
        )

    return None


def finalize_decision_payload(
    *,
    action: str,
    raw_edge_id: str | None,
    raw_search_target_id: str | None,
    raw_query_text: str | None,
    decision_rationale: object,
    confidence: object,
    validation_target: ValidationTargetRef | None,
    scratchpad_update: dict[str, str] | None,
) -> dict[str, object]:
    return {
        "action": action,
        "edge_id": raw_edge_id,
        "search_target_id": raw_search_target_id,
        "query_text": raw_query_text,
        "decision_rationale": decision_rationale,
        "confidence": confidence,
        "validation_target": validation_target,
        "scratchpad_update": scratchpad_update,
    }


__all__ = [
    "build_mark_exhausted_decision",
    "build_scratchpad_update",
    "finalize_decision_payload",
    "optional_str",
    "resolve_edge_guardrail",
    "resolve_search_guardrail",
    "resolve_validation_target_guardrail",
]
