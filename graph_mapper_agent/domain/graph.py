from __future__ import annotations
#graph_mapper_agent/domain/graph.py
from dataclasses import dataclass, field

from graph_mapper_agent.domain.page_type import PageType


EdgeStatus = str
NodeStatus = str


@dataclass(slots=True, frozen=True)
class ObservedCandidate:
    target_url: str
    label: str

    relation: str = "unknown"
    candidate_type: str = "unknown"

    resource_kind: str | None = None
    delivery_mode: str | None = None

    semantic_label: str | None = None
    table_heading: str | None = None
    adjacent_cell_text: str | None = None

    same_host: bool | None = None
    base_score: float | None = None

    source_channel: str = "unknown"
    source_frame: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class NodeWorkingMemory:
    local_summary: str = ""
    active_hypothesis: str | None = None
    next_hints: tuple[str, ...] = ()
    avoid_hints: tuple[str, ...] = ()
    pending_questions: tuple[str, ...] = ()
    confidence: float | None = None
    revision_count: int = 0

    def is_empty(self) -> bool:
        return not (
            self.local_summary
            or self.active_hypothesis
            or self.next_hints
            or self.avoid_hints
            or self.pending_questions
        )


@dataclass(slots=True)
class EdgeState:
    edge_id: str
    from_node_id: str
    target_url: str
    label: str

    relation: str = "unknown"
    candidate_type: str = "unknown"
    status: EdgeStatus = "discovered"

    resource_kind: str | None = None
    delivery_mode: str | None = None

    semantic_label: str | None = None
    table_heading: str | None = None
    adjacent_cell_text: str | None = None

    same_host: bool | None = None
    child_node_id: str | None = None

    attempt_count: int = 0
    last_outcome: str | None = None
    last_error: str | None = None

    discovered_order: int = 0
    base_score: float | None = None
    observed_count: int = 0
    last_observed_step: int | None = None
    source_channels: tuple[str, ...] = ()
    source_frames: tuple[str, ...] = ()
    labels_seen: tuple[str, ...] = ()

    def is_pending(self) -> bool:
        return self.status in {"discovered", "queued"}

    def is_terminal_failure(self) -> bool:
        return self.status in {"failed", "blocked", "rejected"}

    def mark_attempt(
        self,
        *,
        outcome: str | None = None,
        error: str | None = None,
        next_status: EdgeStatus | None = None,
    ) -> None:
        self.attempt_count += 1
        if outcome is not None:
            self.last_outcome = outcome
        if error is not None:
            self.last_error = error
        if next_status is not None:
            self.status = next_status

    def register_observation(
        self,
        *,
        label: str | None = None,
        source_channel: str | None = None,
        source_frame: str | None = None,
        observed_step: int | None = None,
    ) -> None:
        self.observed_count += 1
        if observed_step is not None:
            self.last_observed_step = observed_step
        normalized_label = str(label or "").strip()
        if normalized_label and normalized_label not in self.labels_seen:
            self.labels_seen = (*self.labels_seen, normalized_label)
        normalized_channel = str(source_channel or "").strip()
        if normalized_channel and normalized_channel not in self.source_channels:
            self.source_channels = (*self.source_channels, normalized_channel)
        normalized_frame = str(source_frame or "").strip()
        if normalized_frame and normalized_frame not in self.source_frames:
            self.source_frames = (*self.source_frames, normalized_frame)


@dataclass(slots=True)
class GraphNodeState:
    node_id: str
    canonical_url: str

    title: str | None = None

    page_type: PageType = PageType.UNKNOWN
    page_type_confidence: float | None = None
    page_diagnostics: dict[str, object] = field(default_factory=dict)

    status: NodeStatus = "fresh"

    visited_count: int = 0
    inspected: bool = False
    expanded: bool = False
    exhausted: bool = False

    pending_edge_ids: tuple[str, ...] = ()
    explored_edge_ids: tuple[str, ...] = ()
    useful_edge_ids: tuple[str, ...] = ()

    artifact_urls: tuple[str, ...] = ()
    last_arrival_context_id: str | None = None
    last_progress_step: int | None = None

    working_memory: NodeWorkingMemory = field(default_factory=NodeWorkingMemory)

    def has_pending_edges(self) -> bool:
        return len(self.pending_edge_ids) > 0

    def exploration_ratio(self) -> float:
        total = len(self.pending_edge_ids) + len(self.explored_edge_ids)
        if total == 0:
            return 0.0
        return len(self.explored_edge_ids) / total

    def useful_ratio(self) -> float:
        total = len(self.explored_edge_ids)
        if total == 0:
            return 0.0
        return len(self.useful_edge_ids) / total

    def register_visit(self, *, arrival_context_id: str | None = None) -> None:
        self.visited_count += 1
        if arrival_context_id is not None:
            self.last_arrival_context_id = arrival_context_id

    def set_page_classification(
        self,
        *,
        page_type: PageType,
        confidence: float | None,
        diagnostics: dict[str, object] | None = None,
    ) -> None:
        self.page_type = page_type
        self.page_type_confidence = confidence
        self.page_diagnostics = dict(diagnostics or {})

    def mark_inspected(self) -> None:
        self.inspected = True
        if self.status == "fresh":
            self.status = "inspected"

    def mark_expanded(self) -> None:
        self.expanded = True
        if self.status in {"fresh", "inspected"}:
            self.status = "expanded"

    def mark_partially_exhausted(self) -> None:
        self.status = "partially_exhausted"

    def mark_exhausted(self) -> None:
        self.exhausted = True
        self.status = "exhausted"

    def add_pending_edge(self, edge_id: str) -> None:
        if edge_id not in self.pending_edge_ids:
            self.pending_edge_ids = (*self.pending_edge_ids, edge_id)

    def remove_pending_edge(self, edge_id: str) -> None:
        if edge_id in self.pending_edge_ids:
            self.pending_edge_ids = tuple(
                x for x in self.pending_edge_ids if x != edge_id
            )

    def add_explored_edge(self, edge_id: str) -> None:
        if edge_id not in self.explored_edge_ids:
            self.explored_edge_ids = (*self.explored_edge_ids, edge_id)
        self.remove_pending_edge(edge_id)

    def add_useful_edge(self, edge_id: str) -> None:
        if edge_id not in self.useful_edge_ids:
            self.useful_edge_ids = (*self.useful_edge_ids, edge_id)

    def add_artifact_url(self, artifact_url: str) -> None:
        if artifact_url and artifact_url not in self.artifact_urls:
            self.artifact_urls = (*self.artifact_urls, artifact_url)


@dataclass(slots=True)
class GraphMemory:
    nodes_by_id: dict[str, GraphNodeState] = field(default_factory=dict)
    edges_by_id: dict[str, EdgeState] = field(default_factory=dict)
    url_to_node_id: dict[str, str] = field(default_factory=dict)
    root_node_ids: tuple[str, ...] = ()

    def get_node(self, node_id: str) -> GraphNodeState | None:
        return self.nodes_by_id.get(node_id)

    def get_edge(self, edge_id: str) -> EdgeState | None:
        return self.edges_by_id.get(edge_id)

    def get_node_by_url(self, canonical_url: str) -> GraphNodeState | None:
        node_id = self.url_to_node_id.get(canonical_url)
        if node_id is None:
            return None
        return self.nodes_by_id.get(node_id)

    def register_node(self, node: GraphNodeState, *, is_root: bool = False) -> None:
        self.nodes_by_id[node.node_id] = node
        self.url_to_node_id[node.canonical_url] = node.node_id

        if is_root and node.node_id not in self.root_node_ids:
            self.root_node_ids = (*self.root_node_ids, node.node_id)

    def register_edge(self, edge: EdgeState) -> None:
        self.edges_by_id[edge.edge_id] = edge

    def ensure_node(
        self,
        *,
        node_id: str,
        canonical_url: str,
        title: str | None = None,
        is_root: bool = False,
    ) -> GraphNodeState:
        existing = self.get_node_by_url(canonical_url)
        if existing is not None:
            if title and not existing.title:
                existing.title = title
            if is_root and existing.node_id not in self.root_node_ids:
                self.root_node_ids = (*self.root_node_ids, existing.node_id)
            return existing

        node = GraphNodeState(
            node_id=node_id,
            canonical_url=canonical_url,
            title=title,
        )
        self.register_node(node, is_root=is_root)
        return node

    def edges_from_node(self, node_id: str) -> tuple[EdgeState, ...]:
        return tuple(
            edge for edge in self.edges_by_id.values() if edge.from_node_id == node_id
        )

    def pending_edges_from_node(self, node_id: str) -> tuple[EdgeState, ...]:
        return tuple(edge for edge in self.edges_from_node(node_id) if edge.is_pending())
