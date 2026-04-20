from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.application.services.candidate_ranker import (
    CandidateRanker,
)
from graph_mapper_agent.application.services.candidate_selector import (
    CandidateSelector,
)
from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperDecision,
)
from graph_mapper_agent.application.services.decision.normalization import (
    looks_like_bridge,
    looks_like_direct_artifact,
)
from graph_mapper_agent.domain.view import NodeView


@dataclass(slots=True, frozen=True)
class HeuristicDecisionEngine:
    candidate_selector: CandidateSelector
    candidate_ranker: CandidateRanker

    def decide(self, node_view: NodeView) -> GraphMapperDecision:
        selected = self.candidate_selector.select(node_view.candidates)
        ranked = self.candidate_ranker.rank(selected)

        if not ranked:
            return heuristic_no_candidates(node_view)

        best = ranked[0].candidate

        if looks_like_direct_artifact(best):
            return GraphMapperDecision(
                action="download_artifact",
                edge_id=best.edge_id,
                decision_rationale="best_direct_artifact_candidate",
                confidence=0.80,
                scratchpad_update=None,
            )

        if looks_like_bridge(best):
            return GraphMapperDecision(
                action="follow_edge",
                edge_id=best.edge_id,
                decision_rationale="best_bridge_candidate",
                confidence=0.72,
                scratchpad_update=None,
            )

        return GraphMapperDecision(
            action="follow_edge",
            edge_id=best.edge_id,
            decision_rationale="fallback_follow_edge",
            confidence=0.60,
            scratchpad_update=None,
        )


def heuristic_no_candidates(node_view: NodeView) -> GraphMapperDecision:
    if node_view.can_validate_current_content:
        return GraphMapperDecision(
            action="validate_current_content",
            edge_id=None,
            decision_rationale="validate_current_local_evidence",
            confidence=0.84,
            scratchpad_update=None,
        )

    arrival_edge_id = artifact_arrival_edge_id(node_view)
    if arrival_edge_id is not None:
        return GraphMapperDecision(
            action="open_artifact",
            edge_id=arrival_edge_id,
            decision_rationale="open_current_artifact_leaf_from_arrival_edge",
            confidence=0.78,
            scratchpad_update=None,
        )

    navigation = node_view.navigation_perception
    if (
        navigation is None
        or navigation.visible_candidate_count is None
        or navigation.visible_candidate_count == 0
    ):
        return GraphMapperDecision(
            action="refine_navigation_perception",
            edge_id=None,
            decision_rationale="need_local_navigation_refinement",
            confidence=0.70,
            scratchpad_update=None,
        )

    return GraphMapperDecision(
        action="mark_exhausted",
        edge_id=None,
        decision_rationale="no_candidates",
        confidence=0.95,
        scratchpad_update=None,
    )


def artifact_arrival_edge_id(node_view: NodeView) -> str | None:
    arrival = node_view.arrival
    if arrival is None or not arrival.via_edge_id:
        return None
    if str(node_view.url or "").strip().lower().endswith(".pdf"):
        return arrival.via_edge_id
    return None


def current_node_looks_like_pdf_leaf(node_view: NodeView) -> bool:
    if not str(node_view.url or "").strip().lower().endswith(".pdf"):
        return False
    if node_view.candidates:
        return False
    return artifact_arrival_edge_id(node_view) is not None
__all__ = [
    "HeuristicDecisionEngine",
    "artifact_arrival_edge_id",
    "current_node_looks_like_pdf_leaf",
    "heuristic_no_candidates",
]
