from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from graph_mapper_agent.application.contracts.runtime_views import (
        RuntimeAdvancePolicyPort,
    )


@dataclass(slots=True, frozen=True)
class ExplorationScopeAdvanceDecision:
    next_route: str
    next_scope_id: str | None = None
    choice_point_id: str | None = None
    strategic_anchor_point_id: str | None = None
    reason: str | None = None


@dataclass(slots=True, frozen=True)
class ExplorationScopePolicy:
    def decide_next(
        self, runtime: RuntimeAdvancePolicyPort
    ) -> ExplorationScopeAdvanceDecision:
        scope = runtime.get_active_scope()

        if scope is None:
            strategic_restart = self._strategic_restart_decision_if_available(runtime)
            if strategic_restart is not None:
                return strategic_restart
            next_item = self._next_viable_choice_point(runtime)
            if next_item is None:
                anchor_restart = self._anchor_restart_decision_if_available(runtime)
                if anchor_restart is not None:
                    return anchor_restart
                return self._terminal_decision_when_choice_points_empty(
                    runtime,
                    success_reason="no_active_scope_empty_choice_points_with_satisfied_goals",
                    fail_reason="no_active_scope_and_empty_choice_points",
                )
            return ExplorationScopeAdvanceDecision(
                next_route="inspect_node",
                next_scope_id=next_item.scope_id,
                choice_point_id=next_item.choice_point_id,
                reason="resume_choice_point_without_active_scope",
            )

        if scope.is_terminal():
            strategic_restart = self._strategic_restart_decision_if_available(
                runtime,
                scope_id=scope.scope_id,
                exclude_node_id=scope.current_node_id,
            )
            if strategic_restart is not None:
                return strategic_restart
            next_item = self._next_viable_choice_point(runtime)
            if next_item is None:
                anchor_restart = self._anchor_restart_decision_if_available(runtime)
                if anchor_restart is not None:
                    return anchor_restart
                return self._terminal_decision_when_choice_points_empty(
                    runtime,
                    success_reason="terminal_scope_empty_choice_points_with_satisfied_goals",
                    fail_reason="terminal_scope_and_empty_choice_points",
                )
            return ExplorationScopeAdvanceDecision(
                next_route="inspect_node",
                next_scope_id=next_item.scope_id,
                choice_point_id=next_item.choice_point_id,
                reason="terminal_scope_resume_choice_point",
            )

        current_node = None
        if scope.current_node_id:
            current_node = runtime.graph.get_node(scope.current_node_id)

        if current_node is None:
            return ExplorationScopeAdvanceDecision(
                next_route="fail",
                reason="active_scope_without_current_node",
            )

        last_action = None
        if runtime.last_decision:
            last_action = str(runtime.last_decision.get("action") or "").strip()

        if last_action == "open_artifact":
            if current_node.has_pending_edges():
                return ExplorationScopeAdvanceDecision(
                    next_route="inspect_node",
                    next_scope_id=scope.scope_id,
                    reason="open_artifact_continue_same_node",
                )

            current_node.mark_exhausted()
            strategic_restart = self._strategic_restart_decision_if_available(
                runtime,
                scope_id=scope.scope_id,
                exclude_node_id=current_node.node_id,
            )
            if strategic_restart is not None:
                return strategic_restart
            next_item = self._next_viable_choice_point(
                runtime,
                exclude_node_id=current_node.node_id,
            )
            if next_item is None:
                anchor_restart = self._anchor_restart_decision_if_available(runtime)
                if anchor_restart is not None:
                    return anchor_restart
                return self._terminal_decision_when_choice_points_empty(
                    runtime,
                    success_reason="open_artifact_empty_choice_points_with_satisfied_goals",
                    fail_reason="open_artifact_no_pending_edges_and_empty_choice_points",
                )
            return ExplorationScopeAdvanceDecision(
                next_route="inspect_node",
                next_scope_id=next_item.scope_id,
                choice_point_id=next_item.choice_point_id,
                reason="open_artifact_resume_choice_point",
            )

        if current_node.exhausted:
            strategic_restart = self._strategic_restart_decision_if_available(
                runtime,
                scope_id=scope.scope_id,
                exclude_node_id=current_node.node_id,
            )
            if strategic_restart is not None:
                return strategic_restart
            next_item = self._next_viable_choice_point(
                runtime,
                exclude_node_id=current_node.node_id,
            )
            if next_item is None:
                anchor_restart = self._anchor_restart_decision_if_available(
                    runtime,
                    exclude_node_id=current_node.node_id,
                )
                if anchor_restart is not None:
                    return anchor_restart
                return self._terminal_decision_when_choice_points_empty(
                    runtime,
                    success_reason="exhausted_graph_empty_choice_points_with_satisfied_goals",
                    fail_reason="exhausted_graph_without_satisfying_goal",
                )
            return ExplorationScopeAdvanceDecision(
                next_route="inspect_node",
                next_scope_id=next_item.scope_id,
                choice_point_id=next_item.choice_point_id,
                reason="exhausted_node_resume_choice_point",
            )

        return ExplorationScopeAdvanceDecision(
            next_route="inspect_node",
            next_scope_id=scope.scope_id,
            reason="continue_active_scope",
        )

    def _terminal_decision_when_choice_points_empty(
        self,
        runtime: RuntimeAdvancePolicyPort,
        *,
        success_reason: str,
        fail_reason: str,
    ) -> ExplorationScopeAdvanceDecision:
        if runtime.has_dynamic_goal_trace():
            if runtime.dynamic_all_conditions_satisfied():
                return ExplorationScopeAdvanceDecision(
                    next_route="success",
                    reason=success_reason,
                )
            return ExplorationScopeAdvanceDecision(
                next_route="fail",
                reason=fail_reason,
            )

        return ExplorationScopeAdvanceDecision(
            next_route="fail",
            reason=fail_reason,
        )

    def _strategic_restart_decision_if_available(
        self,
        runtime: RuntimeAdvancePolicyPort,
        *,
        scope_id: str | None = None,
        exclude_node_id: str | None = None,
    ) -> ExplorationScopeAdvanceDecision | None:
        item = runtime.best_strategic_anchor_point(
            scope_id=scope_id,
            exclude_node_id=exclude_node_id,
        )
        if item is None:
            return None

        node = runtime.graph.get_node(item.node_id)
        if node is None or node.exhausted or not node.has_pending_edges():
            return None

        return ExplorationScopeAdvanceDecision(
            next_route="inspect_node",
            next_scope_id=item.scope_id,
            strategic_anchor_point_id=item.anchor_point_id,
            reason="restart_from_strategic_anchor",
        )

    def _anchor_restart_decision_if_available(
        self,
        runtime: RuntimeAdvancePolicyPort,
        *,
        exclude_node_id: str | None = None,
    ) -> ExplorationScopeAdvanceDecision | None:
        anchor = runtime.anchor
        if anchor is None:
            return None

        root_node = runtime.graph.get_node(anchor.root_node_id)
        if root_node is None:
            return None

        if exclude_node_id and root_node.node_id == exclude_node_id:
            return None

        if root_node.exhausted:
            return None

        if not root_node.has_pending_edges():
            return None

        active_scope = runtime.get_active_scope()
        return ExplorationScopeAdvanceDecision(
            next_route="inspect_node",
            next_scope_id=None if active_scope is None else active_scope.scope_id,
            choice_point_id=None,
            reason="restart_from_anchor_root",
        )

    def _next_viable_choice_point(
        self,
        runtime: GraphMapperState,
        *,
        exclude_node_id: str | None = None,
    ):
        visible = runtime.visible_choice_points()
        if not visible:
            return None

        budget = min(12, len(visible))
        checked = 0

        for item in visible:
            checked += 1
            if checked > budget:
                break

            if exclude_node_id is not None and item.from_node_id == exclude_node_id:
                continue

            edge = runtime.graph.get_edge(item.edge_id)
            if edge is None:
                continue
            if edge.is_terminal_failure():
                continue

            parent_node = runtime.graph.get_node(item.from_node_id)
            if parent_node is None or parent_node.exhausted:
                continue

            return item

        return None
