from __future__ import annotations
#graph_mapper_agent/application/services/decision/fallback_selection.py
from typing import Any

from graph_mapper_agent.application.services.decision.condition_matching import (
    matches_only_satisfied_conditions,
    matches_pending_conditions,
)
from graph_mapper_agent.application.services.decision.normalization import (
    looks_like_bridge,
    looks_like_direct_artifact,
)
from graph_mapper_agent.application.services.decision.search_helpers import (
    is_same_page_self_loop_candidate,
    looks_external_to_current_node,
    looks_like_search_engine_boilerplate,
)
from graph_mapper_agent.domain.view import NodeView


def choose_safe_fallback_candidate(
    node_view: NodeView,
    *,
    exclude_edge_id: str | None = None,
) -> Any | None:
    if not node_view.candidates:
        return None

    candidates = [
        candidate
        for candidate in node_view.candidates
        if candidate.edge_id != exclude_edge_id
        and candidate.status not in {"failed", "blocked", "rejected"}
        and candidate.attempt_count < 2
    ]

    if not candidates:
        candidates = [
            candidate
            for candidate in node_view.candidates
            if candidate.edge_id != exclude_edge_id
        ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda candidate: (
            1 if matches_pending_conditions(candidate, node_view) else 0,
            0 if matches_only_satisfied_conditions(candidate, node_view) else 1,
            1 if looks_like_direct_artifact(candidate) else 0,
            candidate.base_score if candidate.base_score is not None else 0.0,
            -candidate.attempt_count,
        ),
        reverse=True,
    )

    return candidates[0]


def choose_bridge_fallback_candidate(
    node_view: NodeView,
    *,
    exclude_edge_id: str | None = None,
) -> Any | None:
    candidates = [
        candidate
        for candidate in node_view.candidates
        if candidate.edge_id != exclude_edge_id
        and looks_like_bridge(candidate)
        and candidate.status not in {"failed", "blocked", "rejected"}
        and candidate.attempt_count < 2
    ]

    if not candidates:
        candidates = [
            candidate
            for candidate in node_view.candidates
            if candidate.edge_id != exclude_edge_id and looks_like_bridge(candidate)
        ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda candidate: (
            1 if matches_pending_conditions(candidate, node_view) else 0,
            candidate.base_score if candidate.base_score is not None else 0.0,
            -candidate.attempt_count,
        ),
        reverse=True,
    )

    return candidates[0]


def choose_search_result_fallback_candidate(
    node_view: NodeView,
    *,
    exclude_edge_id: str | None = None,
) -> Any | None:
    candidates = [
        candidate
        for candidate in node_view.candidates
        if candidate.edge_id != exclude_edge_id
        and candidate.status not in {"failed", "blocked", "rejected"}
        and candidate.attempt_count < 2
        and not looks_like_search_engine_boilerplate(candidate)
        and not is_same_page_self_loop_candidate(candidate, node_view)
    ]

    if not candidates:
        candidates = [
            candidate
            for candidate in node_view.candidates
            if candidate.edge_id != exclude_edge_id
            and not looks_like_search_engine_boilerplate(candidate)
            and not is_same_page_self_loop_candidate(candidate, node_view)
        ]

    if not candidates:
        return None

    candidates.sort(
        key=lambda candidate: (
            1 if looks_like_bridge(candidate) else 0,
            0 if looks_like_direct_artifact(candidate) else 1,
            1 if looks_external_to_current_node(candidate, node_view) else 0,
            candidate.base_score if candidate.base_score is not None else 0.0,
            -candidate.attempt_count,
        ),
        reverse=True,
    )

    return candidates[0]


__all__ = [
    "choose_bridge_fallback_candidate",
    "choose_safe_fallback_candidate",
    "choose_search_result_fallback_candidate",
]
