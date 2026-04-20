#graph_mapper_agent/runtime/state/models.py
from __future__ import annotations

from dataclasses import dataclass, field

from graph_mapper_agent.application.services.goals.models import (
    GoalTrace,
)
from graph_mapper_agent.application.services.goals.evaluator import (
    DynamicGoalEvaluator,
)
from graph_mapper_agent.application.services.goals.alignment import (
    goal_aligned_priority,
    pending_years_from_goal_trace,
)
from graph_mapper_agent.application.navigation_perception.models import (
    NavigationPerceptionResult,
)
from graph_mapper_agent.domain.anchor import AnchorState
from graph_mapper_agent.domain.exploration_scope import (
    ArrivalContext,
    ExplorationScopeState,
)
from graph_mapper_agent.domain.findings import FindingRecord
from graph_mapper_agent.domain.graph import GraphMemory
from graph_mapper_agent.domain.graph_merge import (
    MergeObservedCandidatesResult,
)
from graph_mapper_agent.domain.path import (
    ActivePathState,
    ChoicePointState,
    StrategicAnchorPointState,
)
from graph_mapper_agent.domain.scratchpad import (
    TraversalScratchpad,
)
from graph_mapper_agent.domain.view import NodeView
from .navigation import NavigationPerceptionRefineState
from .validation import DocumentValidationNodeState


@dataclass(slots=True)
class GraphMapperState:
    graph: GraphMemory = field(default_factory=GraphMemory)

    scopes: dict[str, ExplorationScopeState] = field(default_factory=dict)
    active_scope_id: str | None = None

    arrival_contexts: dict[str, ArrivalContext] = field(default_factory=dict)

    anchor: AnchorState | None = None
    active_path: ActivePathState | None = None
    choice_points: dict[str, ChoicePointState] = field(default_factory=dict)
    strategic_anchor_points: dict[str, StrategicAnchorPointState] = field(
        default_factory=dict
    )

    current_node_id: str | None = None
    last_node_view: NodeView | None = None
    last_decision: dict[str, object] | None = None

    last_inspection_result: dict[str, object] | None = None
    last_download_result: dict[str, object] | None = None
    last_artifact_result: dict[str, object] | None = None

    current_content_owner_node_id: str | None = None

    inspection_result_by_node: dict[str, dict[str, object]] = field(default_factory=dict)
    download_result_by_node: dict[str, dict[str, object]] = field(default_factory=dict)
    artifact_result_by_node: dict[str, dict[str, object]] = field(default_factory=dict)

    goal_validation_payload_by_node: dict[str, dict[str, object]] = field(
        default_factory=dict
    )
    goal_validation_state_by_node: dict[str, DocumentValidationNodeState] = field(
        default_factory=dict
    )
    navigation_perception_by_node: dict[str, NavigationPerceptionResult] = field(
        default_factory=dict
    )
    navigation_perception_merge_by_node: dict[
        str, MergeObservedCandidatesResult
    ] = field(default_factory=dict)
    navigation_perception_explicit_runs_by_node: dict[str, int] = field(
        default_factory=dict
    )
    navigation_perception_refine_state_by_node: dict[
        str, NavigationPerceptionRefineState
    ] = field(default_factory=dict)
    navigation_perception_current_node_finding_by_node: dict[str, str] = field(
        default_factory=dict
    )
    frozen_dom_snapshot_by_node: dict[str, bool] = field(default_factory=dict)
    goal_trace: GoalTrace | None = None
    findings: dict[str, FindingRecord] = field(default_factory=dict)
    tactical_scratchpad: TraversalScratchpad = field(
        default_factory=TraversalScratchpad
    )
    last_search_result: dict[str, object] | None = None
    search_result_by_node: dict[str, dict[str, object]] = field(default_factory=dict)
    search_history_by_node: dict[str, tuple[str, ...]] = field(default_factory=dict)
    step_count: int = 0
    max_steps: int = 256

    def mark_frozen_dom_snapshot(self, node_id: str) -> None:
        self.frozen_dom_snapshot_by_node[node_id] = True

    def clear_frozen_dom_snapshot(self, node_id: str) -> None:
        self.frozen_dom_snapshot_by_node.pop(node_id, None)

    def has_frozen_dom_snapshot(self, node_id: str) -> bool:
        return bool(self.frozen_dom_snapshot_by_node.get(node_id))

    def resolve_node_observation_snapshot(
        self, node_id: str
    ) -> dict[str, object] | None:
        search_snapshot = self.search_result_by_node.get(node_id)
        if isinstance(search_snapshot, dict) and search_snapshot:
            print(
                f"[debug.state.resolve] node_id={node_id!r} source='search' "
                f"candidates={len(list(search_snapshot.get('candidates') or []))}",
                flush=True,
            )
            return dict(search_snapshot)

        inspection_snapshot = self.inspection_result_by_node.get(node_id)
        if isinstance(inspection_snapshot, dict) and inspection_snapshot:
            print(
                f"[debug.state.resolve] node_id={node_id!r} source='inspection' "
                f"candidates={len(list(inspection_snapshot.get('candidates') or []))}",
                flush=True,
            )
            return dict(inspection_snapshot)

        print(f"[debug.state.resolve] node_id={node_id!r} source=None", flush=True)
        return None

    def register_search_query(self, node_id: str, query_text: str) -> None:
        q = str(query_text or "").strip()
        if not q:
            return
        prev = self.search_history_by_node.get(node_id, ())
        if q not in prev:
            self.search_history_by_node[node_id] = (*prev, q)

    def has_searched_query(self, node_id: str, query_text: str) -> bool:
        q = str(query_text or "").strip()
        if not q:
            return False
        return q in self.search_history_by_node.get(node_id, ())

    def get_active_scope(self) -> ExplorationScopeState | None:
        if self.active_scope_id is None:
            return None
        return self.scopes.get(self.active_scope_id)

    def set_active_scope(self, scope_id: str) -> None:
        self.active_scope_id = scope_id

    def register_scope(self, scope: ExplorationScopeState) -> None:
        self.scopes[scope.scope_id] = scope

    def get_scope(self, scope_id: str) -> ExplorationScopeState | None:
        return self.scopes.get(scope_id)

    def register_arrival(self, arrival: ArrivalContext) -> None:
        self.arrival_contexts[arrival.arrival_context_id] = arrival

    def get_arrival(self, arrival_context_id: str | None) -> ArrivalContext | None:
        if not arrival_context_id:
            return None
        return self.arrival_contexts.get(arrival_context_id)

    def register_choice_point(self, item: ChoicePointState) -> None:
        self.choice_points[item.choice_point_id] = item

    def get_choice_point(self, choice_point_id: str | None) -> ChoicePointState | None:
        if not choice_point_id:
            return None
        return self.choice_points.get(choice_point_id)

    def register_strategic_anchor_point(self, item: StrategicAnchorPointState) -> None:
        node = self.graph.get_node(item.node_id)
        if node is None or node.exhausted:
            return
        for existing in self.strategic_anchor_points.values():
            if existing.scope_id == item.scope_id and existing.node_id == item.node_id:
                if item.priority >= existing.priority:
                    existing.priority = item.priority
                    existing.reason = item.reason
                    existing.origin_path_step_id = item.origin_path_step_id
                    existing.canonical_url = item.canonical_url
                    existing.source = item.source
                    existing.status = "open"
                return
        self.strategic_anchor_points[item.anchor_point_id] = item

    def best_strategic_anchor_point(
        self,
        *,
        scope_id: str | None = None,
        exclude_node_id: str | None = None,
    ) -> StrategicAnchorPointState | None:
        items = []
        for item in self.strategic_anchor_points.values():
            if item.status != "open":
                continue
            if item.node_id == self.current_node_id:
                continue
            node = self.graph.get_node(item.node_id)
            if node is None or node.exhausted:
                continue
            items.append(item)
        if scope_id is not None:
            items = [item for item in items if item.scope_id == scope_id]
        if exclude_node_id is not None:
            items = [item for item in items if item.node_id != exclude_node_id]
        if not items:
            return None
        items.sort(key=lambda item: (-item.priority, item.anchor_point_id))
        return items[0]

    def visible_choice_points(
        self, scope_id: str | None = None
    ) -> tuple[ChoicePointState, ...]:
        items = [item for item in self.choice_points.values() if item.status == "open"]
        if scope_id is not None:
            items = [item for item in items if item.scope_id == scope_id]
        items.sort(key=lambda item: (-item.priority, item.choice_point_id))
        return tuple(items)

    def next_choice_point(
        self,
        *,
        exclude_from_node_id: str | None = None,
        exclude_node_id: str | None = None,
    ) -> ChoicePointState | None:
        visible = self.visible_choice_points()
        if not visible:
            return None
        excluded_node_id = exclude_from_node_id or exclude_node_id
        if excluded_node_id is not None:
            for item in visible:
                if item.from_node_id != excluded_node_id:
                    return item
        return visible[0]

    def consume_choice_point(self, choice_point_id: str) -> ChoicePointState | None:
        choice_point = self.get_choice_point(choice_point_id)
        if choice_point is None or choice_point.status != "open":
            return None
        choice_point.status = "consumed"
        return choice_point

    def has_choice_points(self) -> bool:
        return any(item.status == "open" for item in self.choice_points.values())

    def increment_step(self) -> None:
        self.step_count += 1

    def reached_step_limit(self) -> bool:
        return self.step_count >= self.max_steps

    def has_active_work(self) -> bool:
        if self.get_active_scope() is not None:
            return True
        if self.has_choice_points():
            return True
        return False

    @property
    def document_validation_payload_by_node(self) -> dict[str, dict[str, object]]:
        return self.goal_validation_payload_by_node

    @property
    def document_validation_state_by_node(self) -> dict[str, DocumentValidationNodeState]:
        return self.goal_validation_state_by_node

    def clear_last_outputs(self) -> None:
        self.last_node_view = None
        self.last_decision = None
        self.last_inspection_result = None
        self.last_download_result = None
        self.last_artifact_result = None
        self.last_search_result = None
        self.current_content_owner_node_id = None

    def register_finding(self, finding: FindingRecord) -> None:
        self.findings[finding.finding_id] = finding

    def reprioritize_choice_points(self, goal_trace: GoalTrace | None) -> None:
        pending_years = pending_years_from_goal_trace(goal_trace)
        if not pending_years:
            return

        for choice_point in self.choice_points.values():
            if choice_point.status != "open":
                continue

            edge = self.graph.get_edge(choice_point.edge_id)
            if edge is None:
                continue

            choice_point.priority = goal_aligned_priority(
                base_score=float(edge.base_score or 0.0),
                target_url=choice_point.target_url,
                label=edge.label or choice_point.label or "",
                pending_years=pending_years,
            )

    def evaluated_goal_trace(self) -> GoalTrace | None:
        if self.goal_trace is None:
            return None
        return DynamicGoalEvaluator().evaluate(
            self.goal_trace,
            tuple(self.findings.values()),
        )

    def has_dynamic_goal_trace(self) -> bool:
        evaluated = self.evaluated_goal_trace()
        return evaluated is not None and evaluated.active_proposal() is not None

    def dynamic_satisfied_conditions_count(self) -> int:
        evaluated = self.evaluated_goal_trace()
        active = None if evaluated is None else evaluated.active_proposal()
        if active is None:
            return 0
        return sum(
            1 for condition in active.conditions if condition.status == "satisfied"
        )

    def dynamic_pending_conditions_count(self) -> int:
        evaluated = self.evaluated_goal_trace()
        active = None if evaluated is None else evaluated.active_proposal()
        if active is None:
            return 0
        return sum(
            1 for condition in active.conditions if condition.status != "satisfied"
        )

    def dynamic_all_conditions_satisfied(self) -> bool:
        evaluated = self.evaluated_goal_trace()
        active = None if evaluated is None else evaluated.active_proposal()
        if active is None or not active.conditions:
            return False
        return all(condition.status == "satisfied" for condition in active.conditions)
__all__ = [
    "GraphMapperState",
]
