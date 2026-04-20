from __future__ import annotations

from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperDecision,
)
from graph_mapper_agent.application.services.decision.fallback_selection import (
    choose_safe_fallback_candidate,
    choose_search_result_fallback_candidate,
)
from graph_mapper_agent.application.services.decision.llm_context import (
    DecisionLlmContext,
)
from graph_mapper_agent.application.services.decision.normalization import (
    looks_like_direct_artifact,
)
from graph_mapper_agent.application.services.decision.search_helpers import (
    is_authorized_search_host,
    node_view_search_targets,
    search_query_already_attempted,
)


def guard_search(ctx: DecisionLlmContext) -> GraphMapperDecision | None:
    if ctx.action != "search_with_text":
        return None

    node_view = ctx.node_view

    # RESTRICCIÓN DE HOST: Solo permitir búsqueda si estamos en DuckDuckGo o el host del Anchor
    anchor_url = node_view.anchor.anchor_url if node_view.anchor else None
    current_url = node_view.url

    if not is_authorized_search_host(current_url, anchor_url):
        return GraphMapperDecision(
            action="mark_exhausted",
            decision_rationale=ctx.suffixed(
                "search_restricted_to_search_engine_hosts",
                f"llm_attempted_search_on_unauthorized_host:{current_url}",
            ),
            confidence=ctx.or_confidence(0.40),
            scratchpad_update=ctx.scratchpad,
        )

    search_targets = node_view_search_targets(node_view)

    if not search_targets:
        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            search_target_id=None,
            query_text=None,
            decision_rationale=ctx.suffixed(
                "search_with_text_requested_but_no_search_targets_available",
                "llm_requested_search_with_text_without_available_search_targets",
            ),
            confidence=ctx.or_confidence(0.45),
            scratchpad_update=ctx.scratchpad,
        )

    if not ctx.search_target_id:
        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            search_target_id=None,
            query_text=None,
            decision_rationale=ctx.suffixed(
                "search_with_text_missing_search_target_id",
                "llm_requested_search_with_text_without_search_target_id",
            ),
            confidence=ctx.or_confidence(0.40),
            scratchpad_update=ctx.scratchpad,
        )

    if ctx.selected_search_target is None:
        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            search_target_id=None,
            query_text=None,
            decision_rationale=ctx.suffixed(
                f"search_target_not_visible:{ctx.search_target_id}",
                "llm_requested_search_with_text_with_non_visible_search_target",
            ),
            confidence=ctx.or_confidence(0.40),
            scratchpad_update=ctx.scratchpad,
        )

    if not ctx.query_text:
        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            search_target_id=None,
            query_text=None,
            decision_rationale=ctx.suffixed(
                "search_with_text_missing_query_text",
                "llm_requested_search_with_text_without_query_text",
            ),
            confidence=ctx.or_confidence(0.40),
            scratchpad_update=ctx.scratchpad,
        )

    if search_query_already_attempted(node_view, ctx.query_text):
        result_candidate = choose_search_result_fallback_candidate(node_view)
        if result_candidate is not None:
            return GraphMapperDecision(
                action="follow_edge",
                edge_id=result_candidate.edge_id,
                search_target_id=None,
                query_text=None,
                decision_rationale=ctx.suffixed(
                    "redirected_to_visible_search_result_after_repeated_search_query",
                    "search_query_already_attempted_in_current_node_and_results_exist",
                ),
                confidence=ctx.or_confidence(0.72),
                scratchpad_update=ctx.scratchpad,
            )

        return GraphMapperDecision(
            action="mark_exhausted",
            edge_id=None,
            search_target_id=None,
            query_text=None,
            decision_rationale=ctx.suffixed(
                "search_query_already_attempted_and_no_visible_results_exist",
                "repeated_search_without_new_local_delta_and_node_exhausted",
            ),
            confidence=ctx.or_confidence(0.52),
            scratchpad_update=ctx.scratchpad,
        )

    return GraphMapperDecision(
        action="search_with_text",
        edge_id=None,
        search_target_id=ctx.search_target_id,
        query_text=ctx.query_text,
        decision_rationale=ctx.rationale,
        confidence=ctx.confidence,
        scratchpad_update=ctx.scratchpad,
    )
