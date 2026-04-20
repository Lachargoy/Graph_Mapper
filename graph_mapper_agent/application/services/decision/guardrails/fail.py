from __future__ import annotations

from graph_mapper_agent.application.services.decision.constants import (
    EDGE_REQUIRING_ACTIONS,
)
from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperDecision,
)
from graph_mapper_agent.application.services.decision.heuristic import (
    current_node_looks_like_pdf_leaf,
)
from graph_mapper_agent.application.services.decision.llm_context import (
    DecisionLlmContext,
)


def guard_fail(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    if ctx.action != "fail":
        return None

    return GraphMapperDecision(
        action="mark_exhausted",
        edge_id=None,
        decision_rationale=(
            "llm_requested_fail_but_local_decider_cannot_close_run | "
            "converted_to_mark_exhausted_for_policy_level_resolution"
        ),
        confidence=ctx.or_confidence(0.60),
        scratchpad_update=ctx.scratchpad,
    )


def guard_pdf_leaf(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    node_view = ctx.node_view

    if node_view.candidates or node_view.can_validate_current_content:
        return None
    if not current_node_looks_like_pdf_leaf(node_view):
        return None
    if ctx.arrival_edge_id is None:
        return None

    return GraphMapperDecision(
        action="open_artifact",
        edge_id=ctx.arrival_edge_id,
        decision_rationale=ctx.suffixed(
            "redirected_to_open_artifact_from_pdf_leaf",
            "pdf_leaf_requires_open_before_validation",
        ),
        confidence=ctx.or_confidence(0.86),
        scratchpad_update=ctx.scratchpad,
    )


def guard_no_candidates(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    node_view = ctx.node_view

    if node_view.candidates:
        return None
    if ctx.action not in EDGE_REQUIRING_ACTIONS:
        return None

    if ctx.action == "open_artifact" and ctx.edge_id is not None:
        return GraphMapperDecision(
            action="open_artifact",
            edge_id=ctx.edge_id,
            decision_rationale=(
                ctx.rationale or "open_current_artifact_leaf_without_visible_candidates"
            ),
            confidence=ctx.confidence,
            scratchpad_update=ctx.scratchpad,
        )

    return GraphMapperDecision(
        action="mark_exhausted",
        edge_id=None,
        decision_rationale="no_candidates_force_mark_exhausted",
        confidence=ctx.or_confidence(0.95),
        scratchpad_update=ctx.scratchpad,
    )
