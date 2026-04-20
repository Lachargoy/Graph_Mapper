from __future__ import annotations

from graph_mapper_agent.application.services.decision.condition_matching import (
    has_promising_bridge_candidates_for_pending_goals,
)
from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperDecision,
)
from graph_mapper_agent.application.services.decision.fallback_selection import (
    choose_bridge_fallback_candidate,
)
from graph_mapper_agent.application.services.decision.llm_context import (
    DecisionLlmContext,
)


def guard_refine(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    if ctx.action != "refine_navigation_perception":
        return None

    node_view = ctx.node_view

    if nav_prefers_direct_local_validation(node_view):
        return GraphMapperDecision(
            action="validate_current_content",
            edge_id=None,
            decision_rationale=ctx.suffixed(
                "redirected_to_validate_current_content_from_navigation_perception",
                "llm_requested_refine_but_local_terminal_match_exists",
            ),
            confidence=ctx.or_confidence(0.88),
            scratchpad_update=ctx.scratchpad,
        )

    should_block, block_reason = evaluate_refine_block(ctx)

    if not should_block:
        return GraphMapperDecision(
            action="refine_navigation_perception",
            edge_id=None,
            decision_rationale=ctx.rationale,
            confidence=ctx.confidence,
            scratchpad_update=ctx.scratchpad,
        )

    return handle_blocked_refine(ctx, block_reason)


def evaluate_refine_block(ctx: DecisionLlmContext) -> tuple[bool, str]:
    node_view = ctx.node_view
    navigation = node_view.navigation_perception

    if not node_view.can_refine_navigation_perception:
        return True, "refine_navigation_perception_disabled_for_current_node_context"

    if navigation_perception_exhausted(node_view):
        return True, "navigation_perception_goal_slice_exhausted"

    if (
        node_view.goal_validation is None
        and navigation is not None
        and nav_current_node_match_confidence(navigation) is not None
        and nav_current_node_match_confidence(navigation) >= 0.9
        and nav_current_node_document_family(navigation) is not None
        and str(getattr(navigation, "layout_kind", None) or "").strip() == "content_only"
        and not node_view.candidates
    ):
        return True, "current_node_match_requires_document_validation_not_refine"

    if navigation is not None and (
        getattr(navigation, "recommended_next_step", None)
        == "backtrack_or_use_recoverable_choice_points"
        or getattr(navigation, "goal_slice_exhausted", None) is True
    ):
        if not has_promising_bridge_candidates_for_pending_goals(node_view):
            return True, "navigation_perception_recommends_backtrack"

    if not node_view.candidates and navigation is not None:
        return True, "no_candidates_after_navigation_perception"

    return False, ""


def handle_blocked_refine(
    ctx: DecisionLlmContext,
    block_reason: str,
) -> GraphMapperDecision:
    node_view = ctx.node_view

    if (
        block_reason == "current_node_match_requires_document_validation_not_refine"
        and node_view.can_validate_current_content
    ):
        return GraphMapperDecision(
            action="validate_current_content",
            edge_id=None,
            decision_rationale=ctx.suffixed(
                "redirected_to_validate_current_content_after_refine_block",
                block_reason,
            ),
            confidence=ctx.or_confidence(0.86),
            scratchpad_update=ctx.scratchpad,
        )

    if has_promising_bridge_candidates_for_pending_goals(node_view):
        fallback = choose_bridge_fallback_candidate(node_view)
        if fallback is not None:
            return GraphMapperDecision(
                action="follow_edge",
                edge_id=fallback.edge_id,
                decision_rationale=ctx.suffixed(
                    "redirected_to_bridge_candidate_after_refine_block",
                    block_reason,
                ),
                confidence=ctx.or_confidence(0.72),
                scratchpad_update=ctx.scratchpad,
            )

    return GraphMapperDecision(
        action="mark_exhausted",
        edge_id=None,
        decision_rationale=ctx.suffixed(
            block_reason,
            "llm_requested_redundant_navigation_perception",
        ),
        confidence=ctx.or_confidence(0.85),
        scratchpad_update=ctx.scratchpad,
    )


def navigation_perception_exhausted(node_view) -> bool:
    navigation = node_view.navigation_perception
    if navigation is None:
        return False

    if navigation.goal_slice_exhausted is True:
        return not has_promising_bridge_candidates_for_pending_goals(node_view)

    if (
        navigation.produced_meaningful_delta is False
        and navigation.recommended_next_step
        in {
            "retry_or_expand_navigation_probe",
            "backtrack_or_use_recoverable_choice_points",
        }
    ):
        return not has_promising_bridge_candidates_for_pending_goals(node_view)

    return False


def nav_prefers_direct_local_validation(node_view) -> bool:
    navigation = node_view.navigation_perception
    if navigation is None or not node_view.can_validate_current_content:
        return False

    step = _safe_optional_str(getattr(navigation, "recommended_next_step", None))
    layout = _safe_optional_str(getattr(navigation, "layout_kind", None))
    match_conf = nav_current_node_match_confidence(navigation)
    doc_family = nav_current_node_document_family(navigation)

    try:
        gain = float(getattr(navigation, "immediate_condition_gain", None) or 0)
    except (TypeError, ValueError):
        gain = 0.0

    if step == "validate_current_content" and layout == "content_only" and gain > 0:
        return True

    if (
        match_conf is not None
        and match_conf >= 0.9
        and doc_family is not None
        and layout == "content_only"
    ):
        return True

    return False


def nav_current_node_match_confidence(navigation: object) -> float | None:
    direct = getattr(navigation, "current_node_match_confidence", None)
    if isinstance(direct, (int, float)):
        return float(direct)

    nested = getattr(navigation, "current_node_goal_match", None)
    if isinstance(nested, dict):
        value = nested.get("confidence")
    else:
        value = getattr(nested, "confidence", None)

    return float(value) if isinstance(value, (int, float)) else None


def nav_current_node_document_family(navigation: object) -> str | None:
    direct = _safe_optional_str(getattr(navigation, "current_node_document_family", None))
    if direct:
        return direct

    nested = getattr(navigation, "current_node_goal_match", None)
    if isinstance(nested, dict):
        return _safe_optional_str(nested.get("document_family"))
    return _safe_optional_str(getattr(nested, "document_family", None))


def _safe_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
