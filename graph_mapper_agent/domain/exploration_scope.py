from __future__ import annotations

from dataclasses import dataclass


ExplorationScopeStatus = str
ArrivalMode = str


@dataclass(slots=True)
class ArrivalContext:
    """
    Describes how the exploration arrived at the current node.

    This is not structural node state.
    It is the arrival semantics for a specific scope.
    """

    arrival_context_id: str
    node_id: str
    from_node_id: str | None = None
    via_edge_id: str | None = None

    arrival_depth: int = 0
    arrival_mode: ArrivalMode = 'follow'

    parent_scope_id: str | None = None
    discovery_reason: str | None = None

    is_reentry: bool = False
    step_index: int | None = None


@dataclass(slots=True)
class ExplorationScopeState:
    """
    State of an active or pending exploration scope.

    A scope represents a local operational context of exploration within a goal.
    """

    scope_id: str
    goal_id: str

    status: ExplorationScopeStatus = 'active'

    current_node_id: str | None = None
    current_arrival_context_id: str | None = None

    parent_scope_id: str | None = None
    spawned_from_edge_id: str | None = None

    goal_context: str = ''
    scope_strategy: str | None = None

    recent_trace: tuple[str, ...] = ()
    opened_artifact_urls: tuple[str, ...] = ()
    rejected_edge_ids: tuple[str, ...] = ()

    step_count: int = 0
    progress_events: int = 0

    def is_active(self) -> bool:
        return self.status == 'active'

    def is_terminal(self) -> bool:
        return self.status in {'completed', 'failed', 'abandoned', 'exhausted'}

    def register_node(self, node_id: str, *, arrival_context_id: str | None = None) -> None:
        self.current_node_id = node_id
        if arrival_context_id is not None:
            self.current_arrival_context_id = arrival_context_id
        self.step_count += 1
        self._append_trace(f'node:{node_id}')

    def register_progress(self, label: str) -> None:
        self.progress_events += 1
        self._append_trace(f'progress:{label}')

    def add_opened_artifact(self, artifact_url: str) -> None:
        if artifact_url and artifact_url not in self.opened_artifact_urls:
            self.opened_artifact_urls = (*self.opened_artifact_urls, artifact_url)

    def reject_edge(self, edge_id: str) -> None:
        if edge_id not in self.rejected_edge_ids:
            self.rejected_edge_ids = (*self.rejected_edge_ids, edge_id)

    def mark_exhausted(self) -> None:
        self.status = 'exhausted'

    def mark_completed(self) -> None:
        self.status = 'completed'

    def mark_failed(self) -> None:
        self.status = 'failed'

    def mark_abandoned(self) -> None:
        self.status = 'abandoned'

    def _append_trace(self, entry: str, *, max_items: int = 12) -> None:
        updated = (*self.recent_trace, entry)
        if len(updated) > max_items:
            updated = updated[-max_items:]
        self.recent_trace = updated