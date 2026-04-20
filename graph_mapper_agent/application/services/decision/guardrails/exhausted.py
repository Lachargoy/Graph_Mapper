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


def guard_exhausted_bridges(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    if ctx.action != "mark_exhausted":
        return None
    if not has_promising_bridge_candidates_for_pending_goals(ctx.node_view):
        return None

    fallback = choose_bridge_fallback_candidate(ctx.node_view)
    if fallback is None:
        return None

    return GraphMapperDecision(
        action="follow_edge",
        edge_id=fallback.edge_id,
        decision_rationale=ctx.suffixed(
            "redirected_to_bridge_candidate_for_pending_goal",
            "llm_requested_mark_exhausted_with_pending_bridge_progress",
        ),
        confidence=ctx.or_confidence(0.60),
        scratchpad_update=ctx.scratchpad,
    )
