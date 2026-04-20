from __future__ import annotations
# graph_mapper_agent/runtime/nodes/graph_mapper_nodes.py

from dataclasses import dataclass, field
from uuid import uuid4

from graph_mapper_agent.application.services.execution.action_executor import (
    GraphMapperActionExecutor,
)
from graph_mapper_agent.application.services.decision.decider import (
    GraphMapperDecider,
)
from graph_mapper_agent.application.services.graph_updater import (
    GraphUpdater,
)
from graph_mapper_agent.application.services.exploration_scope_policy import (
    ExplorationScopePolicy,
)
from graph_mapper_agent.application.services.node_view_builder import (
    NodeViewBuilder,
)
from graph_mapper_agent.application.services.page_classifier import (
    PageClassifier,
)
from graph_mapper_agent.domain.anchor import AnchorState
from graph_mapper_agent.domain.exploration_scope import (
    ArrivalContext,
    ExplorationScopeState,
)
from graph_mapper_agent.domain.graph_merge import (
    ObservedCandidateMergePolicy,
)
from graph_mapper_agent.domain.path import (
    ActivePathState,
    ChoicePointState,
    PathStep,
    StrategicAnchorPointState,
)
from graph_mapper_agent.domain.view import NodeView

from graph_mapper_agent.runtime.nodes.advance_branch import (
    apply_branch_resumption,
    finalize_advance_branch,
    log_after,
    restart_from_anchor_root,
    resume_via_choice_point,
    resume_via_strategic_anchor,
)
from graph_mapper_agent.runtime.nodes.build_view_helpers import (
    build_current_node_view,
    maybe_register_strategic_anchor_from_navigation_perception,
    resolve_arrival_context,
    resolve_node_view_capabilities,
    run_navigation_perception_if_needed,
)
from graph_mapper_agent.runtime.nodes.choice_points import (
    seed_choice_points_from_non_selected_candidates,
)
from graph_mapper_agent.runtime.nodes.classify_helpers import (
    apply_node_classification,
    classify_current_node,
    log_node_classification,
    unpack_classification_payload,
)
from graph_mapper_agent.runtime.nodes.decide_helpers import (
    build_scratchpad_update,
    finalize_decision_payload,
    resolve_edge_guardrail,
    resolve_search_guardrail,
    resolve_validation_target_guardrail,
)
from graph_mapper_agent.runtime.nodes.decision_helpers import (
    build_goal_trace_from_state,
    decision_metadata_from_state,
    sanitize_llm_text,
)
from graph_mapper_agent.runtime.nodes.inspect_helpers import (
    build_empty_inspection_payload,
    build_inspection_payload,
    merge_observed_candidates,
    resolve_node_observation,
    unpack_inspection_payload,
)
from graph_mapper_agent.runtime.nodes.refine import (
    execute_refine_navigation_perception,
)
from graph_mapper_agent.runtime.evidence_logging import (
    record_action_evidence,
)
from graph_mapper_agent.runtime.state.access import (
    get_runtime_state,
    require_active_scope,
    require_current_node,
)
from graph_mapper_agent.runtime.state import (
    GraphMapperState,
)


@dataclass(slots=True)
class GraphMapperNodes:
    """
    Implementation of the graph_mapper track.

    Objectives of this version:
    - do not recreate duplicate edges by target_url within the same node
    - preserve unchosen candidates as recoverable choice points
    - allow real backtracking/continuation between branches
    - persist the decider's scratchpad (working plan + tactical observations)
    - sanitize LLM memory before persisting it
    - robust validation of edges in choice points before direct execution
    - protection against edge_id hallucinations by the LLM
    - avoid depending on route_hint in states that use a fixed next_step
    """

    page_classifier: PageClassifier
    node_view_builder: NodeViewBuilder
    exploration_scope_policy: ExplorationScopePolicy
    graph_updater: GraphUpdater
    decider: GraphMapperDecider
    action_executor: GraphMapperActionExecutor
    candidate_merge_policy: ObservedCandidateMergePolicy = field(
        default_factory=ObservedCandidateMergePolicy
    )
    navigation_perception_coordinator: object | None = None

    # ------------------------------------------------------------------
    # bootstrap
    # ------------------------------------------------------------------

    def bootstrap(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)

        print(f"[nodes] runtime type: {type(runtime).__name__}", flush=True)
        print(f"[nodes] runtime module: {type(runtime).__module__}", flush=True)

        entry_url = str(state.get("entry_url") or "").strip()
        if not entry_url:
            raise ValueError("graph_mapper requires 'entry_url' in the initial state")

        goal_id = str(state.get("goal_id") or "goal-root").strip()
        root_node_id = _new_id("node")
        root_scope_id = _new_id("scope")
        root_arrival_id = _new_id("arrival")

        node = runtime.graph.ensure_node(
            node_id=root_node_id,
            canonical_url=entry_url,
            title=None,
            is_root=True,
        )

        arrival = ArrivalContext(
            arrival_context_id=root_arrival_id,
            node_id=node.node_id,
            from_node_id=None,
            via_edge_id=None,
            arrival_depth=0,
            arrival_mode="entry",
            parent_scope_id=None,
            discovery_reason="initial_entry",
            is_reentry=False,
            step_index=runtime.step_count,
        )

        scope = ExplorationScopeState(
            scope_id=root_scope_id,
            goal_id=goal_id,
            status="active",
            current_node_id=node.node_id,
            current_arrival_context_id=arrival.arrival_context_id,
            parent_scope_id=None,
            spawned_from_edge_id=None,
            goal_context=str(state.get("goal_context") or "").strip(),
        )

        scope.register_node(node.node_id, arrival_context_id=arrival.arrival_context_id)

        runtime.goal_trace = build_goal_trace_from_state(state)

        runtime.register_arrival(arrival)
        runtime.register_scope(scope)
        runtime.set_active_scope(scope.scope_id)
        runtime.current_node_id = node.node_id
        node.register_visit(arrival_context_id=arrival.arrival_context_id)

        runtime.anchor = AnchorState(
            anchor_id=f"anchor_{node.node_id}",
            anchor_url=entry_url,
            root_node_id=node.node_id,
            label=node.title,
        )

        runtime.active_path = ActivePathState(
            anchor_id=runtime.anchor.anchor_id,
            steps=(
                PathStep(
                    path_step_id=f"path_step_{node.node_id}",
                    node_id=node.node_id,
                    canonical_url=node.canonical_url,
                    arrival_context_id=arrival.arrival_context_id,
                    depth=arrival.arrival_depth,
                ),
            ),
        )

        print(
            "[nodes.bootstrap] "
            f"entry_url={entry_url!r} "
            f"root_node_id={root_node_id!r} "
            f"root_scope_id={root_scope_id!r} "
            f"goal_trace_loaded={runtime.goal_trace is not None}",
            flush=True,
        )

        return {
            "runtime": runtime,
            "route_hint": "",
        }

    # ------------------------------------------------------------------
    # inspect_node
    # ------------------------------------------------------------------

    def inspect_node(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)
        scope = require_active_scope(runtime)
        node = require_current_node(runtime)

        snapshot = runtime.resolve_node_observation_snapshot(node.node_id)
        has_snapshot = isinstance(snapshot, dict) and bool(snapshot)

        print(
            "[nodes.inspect_node] "
            f"scope_id={scope.scope_id!r} "
            f"node_id={node.node_id!r} "
            f"url={node.canonical_url!r} "
            f"inspected={node.inspected} "
            f"exhausted={node.exhausted} "
            f"has_snapshot={has_snapshot} "
            f"snapshot_candidate_count={len((snapshot or {}).get('candidates') or []) if has_snapshot else 0} "
            f"pending_edges={len(runtime.graph.pending_edges_from_node(node.node_id))} "
            f"choice_points_count={len(runtime.visible_choice_points())}",
            flush=True,
        )

        observation, should_process = resolve_node_observation(
            state=state,
            runtime=runtime,
            node=node,
            navigation_actions=self.action_executor.navigation_actions,
            jurisdiction_code=self.action_executor.jurisdiction_code,
            document_key=self.action_executor.document_key,
            timeout_seconds=self.action_executor.timeout_seconds,
            include_screenshot=self.action_executor.capture_screenshot_for_observations,
        )

        if not should_process or observation is None:
            print(
                "[nodes.inspect_node] skip tool call because node already inspected and no snapshot is available",
                flush=True,
            )
            state["_inspection_payload"] = build_empty_inspection_payload()
            return {
                "runtime": runtime,
                "route_hint": "",
            }

        runtime.increment_step()

        candidates_raw, inspection_metadata, frame_summaries = unpack_inspection_payload(
            observation
        )

        edge_ids, observed_count = merge_observed_candidates(
            runtime=runtime,
            node=node,
            candidate_merge_policy=self.candidate_merge_policy,
            candidates_raw=candidates_raw,
        )

        print(
            "[nodes.inspect_node] "
            f"registered_candidates={len(edge_ids)} "
            f"observed_candidates={observed_count} "
            f"frame_summaries={len(frame_summaries)} "
            f"inspection_metadata_keys={sorted(inspection_metadata.keys())}",
            flush=True,
        )

        state["_inspection_payload"] = build_inspection_payload(
            candidates_raw=candidates_raw,
            inspection_metadata=inspection_metadata,
            frame_summaries=frame_summaries,
            edge_ids=edge_ids,
        )

        return {
            "runtime": runtime,
            "route_hint": "",
        }

    # ------------------------------------------------------------------
    # classify_node
    # ------------------------------------------------------------------

    def classify_node(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)
        node = require_current_node(runtime)

        candidates, inspection_metadata, frame_summaries = unpack_classification_payload(
            state
        )

        classification = classify_current_node(
            page_classifier=self.page_classifier,
            node=node,
            candidates=candidates,
            inspection_metadata=inspection_metadata,
            frame_summaries=frame_summaries,
        )

        apply_node_classification(
            node=node,
            classification=classification,
        )

        log_node_classification(
            node=node,
            classification=classification,
        )

        return {
            "runtime": runtime,
            "route_hint": "",
        }

    # ------------------------------------------------------------------
    # build_node_view
    # ------------------------------------------------------------------

    def build_node_view(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)
        scope = require_active_scope(runtime)
        node = require_current_node(runtime)
        evaluated_goal_trace = runtime.evaluated_goal_trace()

        navigation_perception_result = run_navigation_perception_if_needed(
            navigation_perception_coordinator=self.navigation_perception_coordinator,
            runtime=runtime,
            node=node,
            scope=scope,
            evaluated_goal_trace=evaluated_goal_trace,
        )

        arrival = resolve_arrival_context(
            runtime=runtime,
            scope=scope,
            node=node,
        )

        pending_edges = runtime.graph.pending_edges_from_node(node.node_id)
        all_edges_from_node = runtime.graph.edges_from_node(node.node_id)

        maybe_register_strategic_anchor_from_navigation_perception(
            runtime=runtime,
            scope=scope,
            node=node,
            navigation_perception_result=navigation_perception_result,
        )

        (
            refine_state,
            document_validation_state,
            can_validate_current_content,
            validate_current_content_reason,
        ) = resolve_node_view_capabilities(
            runtime=runtime,
            node=node,
            all_edges_from_node=all_edges_from_node,
            evaluated_goal_trace=evaluated_goal_trace,
            can_validate=(
                self.action_executor is not None
                and getattr(
                    self.action_executor, "local_perception_service", None
                ) is not None
            ),
        )

        node_view = build_current_node_view(
            node_view_builder=self.node_view_builder,
            runtime=runtime,
            node=node,
            scope=scope,
            arrival=arrival,
            pending_edges=pending_edges,
            all_edges_from_node=all_edges_from_node,
            evaluated_goal_trace=evaluated_goal_trace,
            navigation_perception_result=navigation_perception_result,
            document_validation_state=document_validation_state,
            refine_state=refine_state,
            can_validate_current_content=can_validate_current_content,
            validate_current_content_reason=validate_current_content_reason,
        )

        return {
            "runtime": runtime,
            "last_node_view": node_view,
            "route_hint": "",
        }

    # ------------------------------------------------------------------
    # decide_action
    # ------------------------------------------------------------------

    def decide_action(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)
        node_view = runtime.last_node_view

        if node_view is None:
            raise ValueError("decide_action requires last_node_view")

        print(
            "[debug.decide.before] "
            f"node_id={node_view.node_id!r} "
            f"candidate_count={len(node_view.candidates or [])} "
            f"search_target_count={len(getattr(node_view, 'search_targets', ()) or ())} "
            f"can_validate={getattr(node_view, 'can_validate_current_content', None)!r} "
            f"can_refine={getattr(node_view, 'can_refine_navigation_perception', None)!r}",
            flush=True,
        )

        np = getattr(node_view, "navigation_perception", None)
        if np is not None:
            print(
                "[debug.decide.before.np] "
                f"recommended_next_step={getattr(np, 'recommended_next_step', None)!r} "
                f"layout_kind={getattr(np, 'layout_kind', None)!r} "
                f"visible_candidate_count={getattr(np, 'visible_candidate_count', None)!r} "
                f"summary={getattr(np, 'summary', None)!r}",
                flush=True,
            )

        decision_obj = self.decider.decide(
            node_view,
            run=state.get("ledger_run"),
            actor=state.get("ledger_actor"),
            target=state.get("ledger_target"),
            metadata={
                **decision_metadata_from_state(state),
                "goal_id": state.get("goal_id"),
                "goal_context": state.get("goal_context"),
                "node_id": node_view.node_id,
                "page_type": node_view.page_type,
            },
        )

        print(
            "[debug.decide.raw] "
            f"action={getattr(decision_obj, 'action', None)!r} "
            f"edge_id={getattr(decision_obj, 'edge_id', None)!r} "
            f"search_target_id={getattr(decision_obj, 'search_target_id', None)!r} "
            f"query_text={getattr(decision_obj, 'query_text', None)!r} "
            f"confidence={getattr(decision_obj, 'confidence', None)!r} "
            f"rationale={getattr(decision_obj, 'decision_rationale', None)!r}",
            flush=True,
        )

        scratchpad_update_obj = getattr(decision_obj, "scratchpad_update", None)
        working_plan = sanitize_llm_text(
            getattr(scratchpad_update_obj, "working_plan", None)
        )
        tactical_observations = sanitize_llm_text(
            getattr(scratchpad_update_obj, "tactical_observations", None)
        )

        if working_plan:
            runtime.tactical_scratchpad.working_plan = working_plan
        if tactical_observations:
            runtime.tactical_scratchpad.tactical_observations = tactical_observations

        scratchpad_update = build_scratchpad_update(
            working_plan=working_plan,
            tactical_observations=tactical_observations,
        )

        raw_edge_id = _optional_str(getattr(decision_obj, "edge_id", None))
        action = str(getattr(decision_obj, "action", "") or "").strip()

        validation_target, decision_override = self._resolve_validation_target_guardrail(
            runtime=runtime,
            node_id=node_view.node_id,
            action=action,
            scratchpad_update=scratchpad_update,
        )
        if decision_override is not None:
            print(
                "[nodes.decide_action] GUARDRAIL "
                "validate_current_content requested but no frozen validation target is available; "
                "degrading to mark_exhausted",
                flush=True,
            )
            runtime.last_decision = decision_override
            return {
                "runtime": runtime,
                "last_decision": decision_override,
                "route_hint": "",
            }

        decision_override = self._resolve_edge_guardrail(
            runtime=runtime,
            action=action,
            raw_edge_id=raw_edge_id,
            scratchpad_update=scratchpad_update,
        )
        if decision_override is not None:
            print(
                "[nodes.decide_action] GUARDRAIL "
                f"LLM referenced non-existent edge_id={raw_edge_id!r}; "
                "degrading to mark_exhausted",
                flush=True,
            )
            runtime.last_decision = decision_override
            return {
                "runtime": runtime,
                "last_decision": decision_override,
                "route_hint": "",
            }

        raw_search_target_id = _optional_str(
            getattr(decision_obj, "search_target_id", None)
        )
        raw_query_text = sanitize_llm_text(
            getattr(decision_obj, "query_text", None),
            max_len=500,
        )

        decision_override = self._resolve_search_guardrail(
            node_view=node_view,
            action=action,
            raw_search_target_id=raw_search_target_id,
            raw_query_text=raw_query_text,
            scratchpad_update=scratchpad_update,
        )
        if decision_override is not None:
            if not raw_search_target_id:
                print(
                    "[nodes.decide_action] GUARDRAIL invalid search_target_id; degrading to mark_exhausted",
                    flush=True,
                )
            elif not raw_query_text:
                print(
                    "[nodes.decide_action] GUARDRAIL missing query_text for search_with_text; degrading to mark_exhausted",
                    flush=True,
                )
            else:
                print(
                    "[nodes.decide_action] GUARDRAIL invalid_or_missing_search_target_id/query_text; degrading to mark_exhausted",
                    flush=True,
                )
            runtime.last_decision = decision_override
            return {
                "runtime": runtime,
                "last_decision": decision_override,
                "route_hint": "",
            }

        decision = finalize_decision_payload(
            action=action,
            raw_edge_id=raw_edge_id,
            raw_search_target_id=raw_search_target_id,
            raw_query_text=raw_query_text,
            decision_rationale=getattr(decision_obj, "decision_rationale", None),
            confidence=getattr(decision_obj, "confidence", None),
            validation_target=validation_target,
            scratchpad_update=scratchpad_update,
        )

        runtime.last_decision = decision

        print(
            "[nodes.decide_action] "
            f"node_id={node_view.node_id!r} "
            f"action={decision['action']!r} "
            f"edge_id={decision['edge_id']!r} "
            f"search_target_id={decision.get('search_target_id')!r} "
            f"query_text={decision.get('query_text')!r} "
            f"confidence={decision['confidence']!r} "
            f"validation_target={getattr(validation_target, 'source_kind', None)!r} "
            f"decision_rationale={_optional_str(decision['decision_rationale'])!r}",
            flush=True,
        )

        self._seed_choice_points_from_non_selected_candidates(runtime, node_view, decision)

        return {
            "runtime": runtime,
            "last_decision": decision,
            "route_hint": "",
        }

    def _resolve_validation_target_guardrail(
        self,
        *,
        runtime: GraphMapperState,
        node_id: str,
        action: str,
        scratchpad_update: dict[str, str] | None,
    ) -> tuple[ValidationTargetRef | None, dict[str, object] | None]:
        return resolve_validation_target_guardrail(
            runtime=runtime,
            node_id=node_id,
            action=action,
            scratchpad_update=scratchpad_update,
        )

    def _resolve_edge_guardrail(
        self,
        *,
        runtime: GraphMapperState,
        action: str,
        raw_edge_id: str | None,
        scratchpad_update: dict[str, str] | None,
    ) -> dict[str, object] | None:
        return resolve_edge_guardrail(
            runtime=runtime,
            action=action,
            raw_edge_id=raw_edge_id,
            scratchpad_update=scratchpad_update,
        )

    def _resolve_search_guardrail(
        self,
        *,
        node_view,
        action: str,
        raw_search_target_id: str | None,
        raw_query_text: str | None,
        scratchpad_update: dict[str, str] | None,
    ) -> dict[str, object] | None:
        return resolve_search_guardrail(
            node_view=node_view,
            action=action,
            raw_search_target_id=raw_search_target_id,
            raw_query_text=raw_query_text,
            scratchpad_update=scratchpad_update,
        )

    # ------------------------------------------------------------------
    # execute_action
    # ------------------------------------------------------------------

    def execute_action(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)
        decision = dict(runtime.last_decision or {})

        print(
            "[nodes.execute_action] "
            f"decision_action={decision.get('action')!r} "
            f"decision_edge_id={decision.get('edge_id')!r} "
            f"current_node_id={runtime.current_node_id!r}",
            flush=True,
        )

        if str(decision.get("action") or "").strip() == "refine_navigation_perception":
            return self._execute_refine_navigation_perception(runtime=runtime)

        result = self.action_executor.execute(
            runtime=runtime,
            decision=decision,
        )

        runtime.last_inspection_result = result.inspection_result
        runtime.last_download_result = result.download_result
        runtime.last_artifact_result = result.artifact_result

        if result.action == "search_with_text":
            runtime.last_search_result = result.inspection_result

        route_hint = "update_graph"
        if result.action == "success":
            route_hint = "success"
        elif result.action == "fail":
            route_hint = "fail"

        action_result_payload = {
            "action": result.action,
            "status": result.status,
            "edge_id": result.edge_id,
            "child_node_id": result.child_node_id,
            "inspection_result": result.inspection_result,
            "download_result": result.download_result,
            "artifact_result": result.artifact_result,
            "execution_reason": result.reason,
            "validation_target": decision.get("validation_target"),
            "search_target_id": decision.get("search_target_id"),
            "query_text": decision.get("query_text"),
        }

        ledger_run = state.get("ledger_run")
        run_id = getattr(ledger_run, "run_id", None)
        record_action_evidence(
            ledger=self.action_executor.ledger,
            run_id=str(run_id).strip() if run_id is not None else None,
            action_result=action_result_payload,
        )

        print(
            "[nodes.execute_action] "
            f"result_action={result.action!r} "
            f"status={result.status!r} "
            f"child_node_id={result.child_node_id!r} "
            f"route_hint={route_hint!r}",
            flush=True,
        )

        return {
            "runtime": runtime,
            "_action_result": action_result_payload,
            "route_hint": route_hint,
        }

    def _execute_refine_navigation_perception(
        self,
        *,
        runtime: GraphMapperState,
    ) -> dict[str, object]:
        return execute_refine_navigation_perception(
            runtime=runtime,
            navigation_perception_coordinator=self.navigation_perception_coordinator,
        )

    # ------------------------------------------------------------------
    # update_graph
    # ------------------------------------------------------------------

    def update_graph(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)
        action_result = dict(state.get("_action_result") or {})

        before_node_id = runtime.current_node_id
        before_choice_points = len(runtime.visible_choice_points())

        self.graph_updater.apply_action_result(runtime, action_result)

        after_node_id = runtime.current_node_id
        after_choice_points = len(runtime.visible_choice_points())

        print(
            "[nodes.update_graph] "
            f"action={action_result.get('action')!r} "
            f"before_node_id={before_node_id!r} "
            f"after_node_id={after_node_id!r} "
            f"before_choice_points={before_choice_points} "
            f"after_choice_points={after_choice_points}",
            flush=True,
        )

        return {
            "runtime": runtime,
            "route_hint": "",
        }

    # ------------------------------------------------------------------
    # advance_branch
    # ------------------------------------------------------------------

    def advance_branch(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)

        before_active_scope_id = runtime.active_scope_id
        before_current_node_id = runtime.current_node_id
        before_choice_points_count = len(runtime.visible_choice_points())

        print(
            "[nodes.advance_branch] BEFORE "
            f"active_scope_id={before_active_scope_id!r} "
            f"current_node_id={before_current_node_id!r} "
            f"choice_points_count={before_choice_points_count}",
            flush=True,
        )

        decision = self.exploration_scope_policy.decide_next(runtime)

        print(
            "[nodes.advance_branch] POLICY "
            f"next_route={decision.next_route!r} "
            f"next_scope_id={decision.next_scope_id!r} "
            f"choice_point_id={decision.choice_point_id!r} "
            f"strategic_anchor_point_id={decision.strategic_anchor_point_id!r} "
            f"reason={decision.reason!r}",
            flush=True,
        )

        choice_point = None
        strategic_anchor_point = None

        if decision.choice_point_id:
            choice_point = runtime.consume_choice_point(decision.choice_point_id)

            print(
                "[nodes.advance_branch] POP "
                f"choice_point_found={choice_point is not None} "
                f"choice_points_remaining={len(runtime.visible_choice_points())}",
                flush=True,
            )

            if choice_point is not None:
                print(
                    "[nodes.advance_branch] POP DETAIL "
                    f"id={choice_point.choice_point_id!r} "
                    f"scope_id={choice_point.scope_id!r} "
                    f"from_node_id={choice_point.from_node_id!r} "
                    f"edge_id={choice_point.edge_id!r} "
                    f"target_url={choice_point.target_url!r}",
                    flush=True,
                )

        if decision.strategic_anchor_point_id:
            strategic_anchor_point = runtime.strategic_anchor_points.get(
                decision.strategic_anchor_point_id
            )

        if decision.next_scope_id:
            runtime.set_active_scope(decision.next_scope_id)
            scope = runtime.get_active_scope()

            print(
                "[nodes.advance_branch] SET ACTIVE "
                f"active_scope_id_now={runtime.active_scope_id!r} "
                f"scope_exists={scope is not None}",
                flush=True,
            )

            if scope is not None:
                result = self._apply_branch_resumption(
                    runtime=runtime,
                    scope=scope,
                    decision=decision,
                    choice_point=choice_point,
                    strategic_anchor_point=strategic_anchor_point,
                )
                if result is not None:
                    return result

        return self._finalize_advance_branch(runtime, decision)

    # ------------------------------------------------------------------
    # advance_branch helpers
    # ------------------------------------------------------------------

    def _apply_branch_resumption(
        self,
        *,
        runtime: GraphMapperState,
        scope: ExplorationScopeState,
        decision,
        choice_point: ChoicePointState | None,
        strategic_anchor_point: StrategicAnchorPointState | None,
    ) -> dict[str, object] | None:
        return apply_branch_resumption(
            runtime=runtime,
            scope=scope,
            decision=decision,
            choice_point=choice_point,
            strategic_anchor_point=strategic_anchor_point,
        )

    def _resume_via_strategic_anchor(
        self,
        *,
        runtime: GraphMapperState,
        scope: ExplorationScopeState,
        anchor_point: StrategicAnchorPointState,
    ) -> None:
        resume_via_strategic_anchor(
            runtime=runtime,
            scope=scope,
            anchor_point=anchor_point,
        )

    def _resume_via_choice_point(
        self,
        *,
        runtime: GraphMapperState,
        scope: ExplorationScopeState,
        choice_point: ChoicePointState,
    ) -> dict[str, object] | None:
        return resume_via_choice_point(
            runtime=runtime,
            scope=scope,
            choice_point=choice_point,
        )

    def _restart_from_anchor_root(
        self,
        *,
        runtime: GraphMapperState,
        scope: ExplorationScopeState,
    ) -> None:
        restart_from_anchor_root(
            runtime=runtime,
            scope=scope,
        )

    def _finalize_advance_branch(
        self,
        runtime: GraphMapperState,
        decision,
    ) -> dict[str, object]:
        return finalize_advance_branch(runtime, decision)

    def _log_after(self, runtime: GraphMapperState, *, route_hint: str) -> None:
        log_after(runtime, route_hint=route_hint)

    # ------------------------------------------------------------------
    # success / fail
    # ------------------------------------------------------------------

    def success(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)

        if runtime.has_dynamic_goal_trace():
            final_status = (
                "success" if runtime.dynamic_all_conditions_satisfied() else "fail"
            )
            return {
                "final_status": final_status,
                "conditions_satisfied": runtime.dynamic_satisfied_conditions_count(),
                "conditions_pending": runtime.dynamic_pending_conditions_count(),
            }

        return {
            "final_status": "success",
        }

    def fail(self, state: dict[str, object]) -> dict[str, object]:
        runtime = get_runtime_state(state)

        payload: dict[str, object] = {
            "final_status": "fail",
        }

        if runtime.has_dynamic_goal_trace():
            payload["conditions_satisfied"] = runtime.dynamic_satisfied_conditions_count()
            payload["conditions_pending"] = runtime.dynamic_pending_conditions_count()

        return payload

    # ------------------------------------------------------------------
    # internals: choice point seeding
    # ------------------------------------------------------------------

    def _seed_choice_points_from_non_selected_candidates(
        self,
        runtime: GraphMapperState,
        node_view: NodeView,
        decision: dict[str, object],
        *,
        branching_factor: int = 3,
    ) -> None:
        seed_choice_points_from_non_selected_candidates(
            runtime=runtime,
            node_view=node_view,
            decision=decision,
            branching_factor=branching_factor,
        )


# =====================================================================
# Module helpers
# =====================================================================

def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# Temporal compatibility for old imports within the workspace.
GraphMapperNodesV2 = GraphMapperNodes
