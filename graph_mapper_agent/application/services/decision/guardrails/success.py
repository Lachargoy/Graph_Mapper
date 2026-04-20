from __future__ import annotations
#graph_mapper_agent/application/services/decision/guardrails/success.py
from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperDecision,
)
from graph_mapper_agent.application.services.decision.fallback_selection import (
    choose_safe_fallback_candidate,
)
from graph_mapper_agent.application.services.decision.llm_context import (
    DecisionLlmContext,
)
from graph_mapper_agent.application.services.decision.normalization import (
    looks_like_direct_artifact,
)
from graph_mapper_agent.application.services.decision.condition_matching import (
    goal_progress_all_satisfied,
)


def guard_success(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    if ctx.action != "success":
        return None

    node_view = ctx.node_view

    if goal_progress_all_satisfied(node_view):
        return GraphMapperDecision(
            action="success",
            edge_id=None,
            decision_rationale=ctx.rationale or "goal_progress_satisfied",
            confidence=ctx.or_confidence(0.90),
            scratchpad_update=ctx.scratchpad,
        )

    if node_view.can_validate_current_content:
        return GraphMapperDecision(
            action="validate_current_content",
            edge_id=None,
            decision_rationale=ctx.suffixed(
                "redirected_to_validate_current_content_before_success",
                "llm_requested_success_before_goal_satisfaction",
            ),
            confidence=ctx.or_confidence(0.72),
            scratchpad_update=ctx.scratchpad,
        )

    fallback = choose_safe_fallback_candidate(node_view)
    if fallback is not None:
        fallback_action = (
            "download_artifact" if looks_like_direct_artifact(fallback) else "follow_edge"
        )
        return GraphMapperDecision(
            action=fallback_action,
            edge_id=fallback.edge_id,
            decision_rationale=ctx.suffixed(
                "redirected_to_best_available_candidate_before_success",
                "llm_requested_success_without_goal_satisfaction",
            ),
            confidence=ctx.or_confidence(0.60),
            scratchpad_update=ctx.scratchpad,
        )

    return GraphMapperDecision(
        action="mark_exhausted",
        edge_id=None,
        decision_rationale=ctx.suffixed(
            "converted_to_mark_exhausted_no_more_local_progress",
            "llm_requested_success_without_goal_satisfaction",
        ),
        confidence=ctx.or_confidence(0.70),
        scratchpad_update=ctx.scratchpad,
    )
