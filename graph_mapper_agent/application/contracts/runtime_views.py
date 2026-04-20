from __future__ import annotations
#./application/contracts/runtime_views.py
from typing import Any, Protocol


class GraphAccessPort(Protocol):
    def get_edge(self, edge_id: str) -> Any | None:
        ...

    def get_node(self, node_id: str) -> Any | None:
        ...

    def get_node_by_url(self, canonical_url: str) -> Any | None:
        ...

    def pending_edges_from_node(self, node_id: str) -> tuple[Any, ...]:
        ...


class RuntimeGoalTracePort(Protocol):
    def evaluated_goal_trace(self) -> Any | None:
        ...


class RuntimeObservationPort(Protocol):
    graph: GraphAccessPort
    current_node_id: str | None
    last_download_result: dict[str, object] | None
    inspection_result_by_node: dict[str, dict[str, object]]
    download_result_by_node: dict[str, dict[str, object]]
    artifact_result_by_node: dict[str, dict[str, object]]
    search_result_by_node: dict[str, dict[str, object]]

    def has_frozen_dom_snapshot(self, node_id: str) -> bool:
        ...

    def resolve_node_observation_snapshot(
        self, node_id: str
    ) -> dict[str, object] | None:
        ...


class RuntimeExecutionPort(RuntimeGoalTracePort, RuntimeObservationPort, Protocol):
    pass


class RuntimeNavigationPerceptionPort(RuntimeExecutionPort, Protocol):
    step_count: int
    navigation_perception_by_node: dict[str, Any]
    navigation_perception_merge_by_node: dict[str, Any]
    navigation_perception_explicit_runs_by_node: dict[str, int]
    navigation_perception_current_node_finding_by_node: dict[str, str]
    goal_validation_payload_by_node: dict[str, dict[str, object]]
    goal_validation_state_by_node: dict[str, Any]

    def register_finding(self, finding: Any) -> None:
        ...


class RuntimeUpdaterPort(RuntimeNavigationPerceptionPort, Protocol):
    current_content_owner_node_id: str | None
    step_count: int
    navigation_perception_refine_state_by_node: dict[str, Any]
    active_path: Any | None
    last_node_view: Any | None

    def get_active_scope(self) -> Any | None:
        ...

    def get_arrival(self, arrival_context_id: str | None) -> Any | None:
        ...

    def register_arrival(self, arrival: Any) -> None:
        ...

    def mark_frozen_dom_snapshot(self, node_id: str) -> None:
        ...

    def register_search_query(self, node_id: str, query_text: str) -> None:
        ...

    def reprioritize_choice_points(self, goal_trace: Any | None) -> None:
        ...


class RuntimeChoicePointPort(Protocol):
    scope_id: str
    choice_point_id: str


class RuntimeStrategicAnchorPointPort(Protocol):
    scope_id: str
    node_id: str
    anchor_point_id: str


class RuntimeAnchorPort(Protocol):
    root_node_id: str


class RuntimeScopePort(Protocol):
    scope_id: str
    current_node_id: str | None

    def is_terminal(self) -> bool:
        ...


class RuntimeAdvancePolicyPort(Protocol):
    graph: GraphAccessPort
    anchor: RuntimeAnchorPort | None
    last_decision: dict[str, object] | None

    def get_active_scope(self) -> RuntimeScopePort | None:
        ...

    def best_strategic_anchor_point(
        self,
        *,
        scope_id: str | None = None,
        exclude_node_id: str | None = None,
    ) -> RuntimeStrategicAnchorPointPort | None:
        ...

    def next_choice_point(
        self,
        *,
        exclude_node_id: str | None = None,
    ) -> RuntimeChoicePointPort | None:
        ...

    def has_dynamic_goal_trace(self) -> bool:
        ...

    def dynamic_all_conditions_satisfied(self) -> bool:
        ...
