from __future__ import annotations
#./application/services/decision/guardrails/validation.py
from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperDecision,
)
from graph_mapper_agent.application.services.decision.llm_context import (
    DecisionLlmContext,
)


def guard_validate(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    if ctx.action != "validate_current_content":
        return None

    if not ctx.node_view.can_validate_current_content:
        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            decision_rationale=ctx.suffixed(
                "validate_current_content_disabled_for_current_node",
                "llm_requested_validate_current_content_when_unavailable",
            ),
            confidence=ctx.or_confidence(0.70),
            scratchpad_update=ctx.scratchpad,
        )

    return GraphMapperDecision(
        action="validate_current_content",
        edge_id=None,
        decision_rationale=ctx.rationale,
        confidence=ctx.confidence,
        scratchpad_update=ctx.scratchpad,
    )
