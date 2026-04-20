from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from graph_mapper_agent.domain.graph import (
    EdgeState,
    GraphMemory,
    GraphNodeState,
    ObservedCandidate,
)


@dataclass(slots=True, frozen=True)
class MergeObservedCandidatesResult:
    edge_ids: tuple[str, ...]
    created_edge_ids: tuple[str, ...] = ()
    reused_edge_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class ObservedCandidateMergePolicy:
    id_prefix: str = "edge"
    id_factory: Callable[[], str] = field(default=lambda: uuid4().hex[:12])
    drop_same_document_anchors: bool = True

    def merge(
        self,
        *,
        graph: GraphMemory,
        node: GraphNodeState,
        observed_candidates: tuple[ObservedCandidate, ...],
        observed_step: int | None = None,
    ) -> MergeObservedCandidatesResult:
        edge_ids: list[str] = []
        created_edge_ids: list[str] = []
        reused_edge_ids: list[str] = []

        for index, observed in enumerate(observed_candidates, start=1):
            target_url = self._normalize_url(observed.target_url)
            if not target_url:
                continue

            if self.drop_same_document_anchors and self._is_same_document_anchor(
                node=node,
                target_url=target_url,
            ):
                continue

            existing = self._find_existing_edge(
                graph=graph,
                from_node_id=node.node_id,
                target_url=target_url,
            )
            if existing is None:
                edge = self._build_edge(
                    node=node,
                    target_url=target_url,
                    observed=observed,
                    discovered_order=index,
                    observed_step=observed_step,
                )
                graph.register_edge(edge)
                created_edge_ids.append(edge.edge_id)
            else:
                edge = existing
                self._enrich_edge(
                    edge=edge,
                    observed=observed,
                    discovered_order=index,
                    observed_step=observed_step,
                )
                reused_edge_ids.append(edge.edge_id)

            if edge.is_pending():
                node.add_pending_edge(edge.edge_id)
            edge_ids.append(edge.edge_id)

        return MergeObservedCandidatesResult(
            edge_ids=tuple(edge_ids),
            created_edge_ids=tuple(created_edge_ids),
            reused_edge_ids=tuple(reused_edge_ids),
        )

    def _build_edge(
        self,
        *,
        node: GraphNodeState,
        target_url: str,
        observed: ObservedCandidate,
        discovered_order: int,
        observed_step: int | None,
    ) -> EdgeState:
        label = self._choose_label(observed=observed, current_label="")
        candidate_type = observed.candidate_type

        if self._has_fragment(target_url):
            candidate_type = "intra_page_anchor"

        edge = EdgeState(
            edge_id=f"{self.id_prefix}_{self.id_factory()}",
            from_node_id=node.node_id,
            target_url=target_url,
            label=label,
            relation=observed.relation,
            candidate_type=candidate_type,
            resource_kind=observed.resource_kind,
            delivery_mode=observed.delivery_mode,
            semantic_label=observed.semantic_label,
            table_heading=observed.table_heading,
            adjacent_cell_text=observed.adjacent_cell_text,
            same_host=observed.same_host,
            discovered_order=discovered_order,
            base_score=observed.base_score,
        )
        edge.register_observation(
            label=label,
            source_channel=observed.source_channel,
            source_frame=observed.source_frame,
            observed_step=observed_step,
        )
        return edge

    def _enrich_edge(
        self,
        *,
        edge: EdgeState,
        observed: ObservedCandidate,
        discovered_order: int,
        observed_step: int | None,
    ) -> None:
        better_label = self._choose_label(observed=observed, current_label=edge.label)
        if better_label and better_label != edge.label:
            edge.label = better_label

        edge.relation = self._prefer_non_unknown(edge.relation, observed.relation)
        edge.candidate_type = self._prefer_non_unknown(
            edge.candidate_type, observed.candidate_type
        )
        edge.resource_kind = self._prefer_missing(edge.resource_kind, observed.resource_kind)
        edge.delivery_mode = self._prefer_missing(edge.delivery_mode, observed.delivery_mode)
        edge.semantic_label = self._prefer_missing(edge.semantic_label, observed.semantic_label)
        edge.table_heading = self._prefer_missing(edge.table_heading, observed.table_heading)
        edge.adjacent_cell_text = self._prefer_missing(
            edge.adjacent_cell_text, observed.adjacent_cell_text
        )

        if edge.same_host is None and observed.same_host is not None:
            edge.same_host = observed.same_host

        if observed.base_score is not None:
            edge.base_score = max(edge.base_score or observed.base_score, observed.base_score)

        if edge.discovered_order <= 0 or discovered_order < edge.discovered_order:
            edge.discovered_order = discovered_order

        edge.register_observation(
            label=better_label or observed.label,
            source_channel=observed.source_channel,
            source_frame=observed.source_frame,
            observed_step=observed_step,
        )

    def _is_same_document_anchor(
        self,
        *,
        node: GraphNodeState,
        target_url: str,
    ) -> bool:
        if not self._has_fragment(target_url):
            return False

        node_base = self._strip_fragment(getattr(node, "canonical_url", "") or "")
        target_base = self._strip_fragment(target_url)

        return bool(node_base and target_base and node_base == target_base)

    @staticmethod
    def _find_existing_edge(
        *,
        graph: GraphMemory,
        from_node_id: str,
        target_url: str,
    ) -> EdgeState | None:
        for edge in graph.edges_from_node(from_node_id):
            if ObservedCandidateMergePolicy._normalize_url(edge.target_url) == target_url:
                return edge
        return None

    @staticmethod
    def _normalize_url(value: str) -> str:
        return str(value or "").strip()

    @staticmethod
    def _strip_fragment(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        parts = urlsplit(raw)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))

    @staticmethod
    def _has_fragment(value: str) -> bool:
        raw = str(value or "").strip()
        if not raw:
            return False
        return bool(urlsplit(raw).fragment)

    @staticmethod
    def _choose_label(*, observed: ObservedCandidate, current_label: str) -> str:
        preferred = str(observed.semantic_label or observed.label or "").strip()
        current = str(current_label or "").strip()

        if not current:
            return preferred or observed.target_url

        if current == ObservedCandidateMergePolicy._normalize_url(current) and preferred:
            return preferred

        return current

    @staticmethod
    def _prefer_missing(current: str | None, candidate: str | None) -> str | None:
        return current if current else candidate

    @staticmethod
    def _prefer_non_unknown(current: str, candidate: str) -> str:
        normalized_current = str(current or "").strip() or "unknown"
        normalized_candidate = str(candidate or "").strip() or "unknown"

        if normalized_current == "unknown" and normalized_candidate != "unknown":
            return normalized_candidate

        return normalized_current
