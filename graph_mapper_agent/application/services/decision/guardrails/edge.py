from __future__ import annotations

from graph_mapper_agent.application.services.decision.constants import (
    EDGE_REQUIRING_ACTIONS,
    RESUME_MARKERS,
)
from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperDecision,
)
from graph_mapper_agent.application.services.decision.llm_context import (
    DecisionLlmContext,
)


def guard_edge_requirements(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    if ctx.action not in EDGE_REQUIRING_ACTIONS:
        return None

    if not ctx.edge_id:
        return handle_missing_edge(ctx)

    candidate_ids = {candidate.edge_id for candidate in ctx.node_view.candidates}
    if ctx.edge_id not in candidate_ids:
        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            decision_rationale=(
                f"llm_selected_non_visible_edge:{ctx.edge_id} | "
                "recover_using_current_node_only | "
                "the_model_mixed_choice_point_context_with_current_candidates | "
                "force_scope_resume_instead_of_fallback_candidate"
            ),
            confidence=0.35,
            scratchpad_update=ctx.scratchpad,
        )

    return None


def handle_missing_edge(ctx: DecisionLlmContext) -> GraphMapperDecision:
    resume_text = " ".join(
        filter(
            None,
            [
                ctx.rationale or "",
                ctx.working_plan or "",
                ctx.tactical_observations or "",
            ],
        )
    ).lower()

    if any(marker in resume_text for marker in RESUME_MARKERS):
        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            decision_rationale=(
                "llm_requested_action_without_edge_id_but_signaled_choice_point_pivot | "
                "converted_to_mark_exhausted_for_scope_resume"
            ),
            confidence=ctx.or_confidence(0.60),
            scratchpad_update=ctx.scratchpad,
        )

    if ctx.action == "open_artifact":
        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            decision_rationale=ctx.suffixed(
                "converted_to_mark_exhausted_missing_open_artifact_edge",
                "llm_requested_open_artifact_without_edge_id",
            ),
            confidence=ctx.or_confidence(0.55),
            scratchpad_update=ctx.scratchpad,
        )

    raise ValueError(f"{ctx.action} requiere edge_id")
