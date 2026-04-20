from __future__ import annotations
#graph_mapper_agent/application/services/node_view_builder.py
from dataclasses import dataclass
import re

from graph_mapper_agent.application.services.goals.alignment import (
    pending_years_from_goal_trace,
    year_alignment_score,
)
from graph_mapper_agent.application.services.goals.models import (
    GoalTrace,
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
from graph_mapper_agent.domain.graph import (
    EdgeState,
    GraphNodeState,
)
from graph_mapper_agent.domain.path import ActivePathState
from graph_mapper_agent.domain.scratchpad import TraversalScratchpad
from graph_mapper_agent.domain.view import (
    ActivePathView,
    AnchorView,
    ChoicePointsView,
    ChoicePointViewItem,
    GoalValidationView,
    GoalProgressConditionView,
    GoalProgressView,
    NavigationPerceptionCandidateView,
    NavigationPerceptionView,
    NodeView,
    NodeViewArrival,
    NodeViewCandidate,
    NodeViewMemory,
    PathContextView,
    RelevantFindingsView,
    RelevantFindingViewItem,
    SearchTargetView,
    StrategicReturnPointView,
    TacticalScratchpadView,
)
from graph_mapper_agent.application.contracts.validation_state import (
    DocumentValidationNodeState,
)


@dataclass(slots=True, frozen=True)
class NodeViewBuilder:
    def build(
        self,
        *,
        node: GraphNodeState,
        scope: ExplorationScopeState,
        pending_edges: tuple[EdgeState, ...],
        all_edges_from_node: tuple[EdgeState, ...] = (),
        arrival: ArrivalContext | None,
        choice_points: tuple[object, ...] = (),
        goal_trace: GoalTrace | None = None,
        anchor: AnchorState | None = None,
        active_path: ActivePathState | None = None,
        findings: tuple[FindingRecord, ...] = (),
        tactical_scratchpad: TraversalScratchpad | None = None,
        choice_points_count: int = 0,
        navigation_perception: NavigationPerceptionResult | None = None,
        last_artifact_result: dict[str, object] | None = None,
        last_inspection_result: dict[str, object] | None = None,
        current_inspection_result: dict[str, object] | None = None,
        current_search_history: tuple[str, ...] = (),
        current_node_goal_validation: dict[str, object] | None = None,
        current_node_goal_validation_state: DocumentValidationNodeState | None = None,
        strategic_return_point: object | None = None,
        can_refine_navigation_perception: bool = True,
        refine_navigation_perception_reason: str | None = None,
        can_validate_current_content: bool = False,
        validate_current_content_reason: str | None = None,
    ) -> NodeView:
        perception_urls: set[str] = set()
        if (
            navigation_perception is not None
            and hasattr(navigation_perception, "top_candidate_observations")
        ):
            for obs in navigation_perception.top_candidate_observations:
                url = self._normalize_url(getattr(obs, "url", None))
                if url:
                    perception_urls.add(url)

        pending_years = pending_years_from_goal_trace(goal_trace)

        if pending_edges:
            pending_edges = tuple(
                sorted(
                    pending_edges,
                    key=lambda edge: (
                        1 if self._normalize_url(edge.target_url) in perception_urls else 0,
                        year_alignment_score(
                            str(edge.target_url or ""),
                            str(edge.label or ""),
                            pending_years,
                        ),
                        edge.base_score if edge.base_score is not None else 0.0,
                    ),
                    reverse=True,
                )
            )

        candidates = tuple(self._build_candidate(edge) for edge in pending_edges)
        arrival_view = self._build_arrival(arrival)
        memory_view = self._build_memory(node)
        choice_points_view = self._build_choice_points(choice_points, goal_trace=goal_trace)
        restrictions = self._build_restrictions(node=node, scope=scope)
        goal_progress_view = self._build_goal_progress(goal_trace)
        anchor_view = self._build_anchor(anchor)
        active_path_view = self._build_active_path(anchor=anchor, active_path=active_path)
        path_context_view = self._build_path_context(
            node=node,
            anchor=anchor,
            active_path=active_path,
            choice_points_count=choice_points_count,
        )
        findings_view = self._build_relevant_findings(findings)
        scratchpad_view = self._build_scratchpad(tactical_scratchpad)
        navigation_perception_view = self._build_navigation_perception(
            navigation_perception=navigation_perception,
            pending_edges=pending_edges,
            all_edges_from_node=all_edges_from_node,
            can_refine_navigation_perception=can_refine_navigation_perception,
            refine_navigation_perception_reason=refine_navigation_perception_reason,
        )
        goal_validation_view = self._build_goal_validation(
            node=node,
            last_artifact_result=last_artifact_result,
            last_inspection_result=last_inspection_result,
            current_node_goal_validation=current_node_goal_validation,
            current_node_goal_validation_state=current_node_goal_validation_state,
            findings=findings,
            goal_trace=goal_trace,
        )
        strategic_return_view = self._build_strategic_return_point(
            strategic_return_point,
            goal_trace=goal_trace,
        )
        search_targets = self._build_search_targets(current_inspection_result)

        return NodeView(
            node_id=node.node_id,
            url=node.canonical_url,
            title=node.title,
            page_type=node.page_type.value,
            page_type_confidence=node.page_type_confidence,
            node_status=node.status,
            visited_count=node.visited_count,
            exploration_ratio=node.exploration_ratio(),
            useful_ratio=node.useful_ratio(),
            choice_points=choice_points_view,
            goal_context=scope.goal_context,
            scope_strategy=scope.scope_strategy,
            anchor=anchor_view,
            active_path=active_path_view,
            path_context=path_context_view,
            relevant_findings=findings_view,
            goal_progress=goal_progress_view,
            scratchpad=scratchpad_view,
            navigation_perception=navigation_perception_view,
            goal_validation=goal_validation_view,
            strategic_return_point=strategic_return_view,
            can_refine_navigation_perception=can_refine_navigation_perception,
            refine_navigation_perception_reason=refine_navigation_perception_reason,
            can_validate_current_content=can_validate_current_content,
            validate_current_content_reason=validate_current_content_reason,
            memory=memory_view,
            arrival=arrival_view,
            candidates=candidates,
            restrictions=restrictions,
            search_targets=search_targets,
            search_capability_available=bool(search_targets),
            current_search_history=current_search_history,
        )

    def _build_search_targets(
        self,
        current_inspection_result: dict[str, object] | None,
    ) -> tuple[SearchTargetView, ...]:
        if not isinstance(current_inspection_result, dict):
            return ()

        raw_targets = current_inspection_result.get("search_targets") or ()
        items: list[SearchTargetView] = []

        for raw in raw_targets:
            if not isinstance(raw, dict):
                continue

            search_target_id = self._coerce_optional_str(raw.get("search_target_id"))
            if not search_target_id:
                continue

            items.append(
                SearchTargetView(
                    search_target_id=search_target_id,
                    label=self._coerce_optional_str(raw.get("label")),
                    placeholder=self._coerce_optional_str(raw.get("placeholder")),
                    name=self._coerce_optional_str(raw.get("name")),
                    input_type=self._coerce_optional_str(raw.get("input_type")),
                    same_host=raw.get("same_host") if isinstance(raw.get("same_host"), bool) else None,
                    source_frame=self._coerce_optional_str(raw.get("source_frame")),
                    confidence=self._coerce_optional_float(raw.get("confidence")),
                )
            )

        items.sort(key=lambda item: item.confidence or 0.0, reverse=True)
        return tuple(items[:3])

    def _build_candidate(self, edge: EdgeState) -> NodeViewCandidate:
        return NodeViewCandidate(
            edge_id=edge.edge_id,
            label=edge.label,
            target_url=edge.target_url,
            candidate_type=edge.candidate_type,
            relation=edge.relation,
            status=edge.status,
            attempt_count=edge.attempt_count,
            base_score=edge.base_score,
            resource_kind=edge.resource_kind,
            delivery_mode=edge.delivery_mode,
            reason=self._candidate_reason(edge),
            hint=self._candidate_hint(edge),
        )

    def _build_arrival(self, arrival: ArrivalContext | None) -> NodeViewArrival | None:
        if arrival is None:
            return None

        return NodeViewArrival(
            from_node_id=arrival.from_node_id,
            via_edge_id=arrival.via_edge_id,
            arrival_depth=arrival.arrival_depth,
            arrival_mode=arrival.arrival_mode,
            is_reentry=arrival.is_reentry,
        )

    def _build_memory(self, node: GraphNodeState) -> NodeViewMemory:
        return NodeViewMemory(
            local_summary=node.working_memory.local_summary,
            active_hypothesis=node.working_memory.active_hypothesis,
            next_hints=node.working_memory.next_hints,
            avoid_hints=node.working_memory.avoid_hints,
        )

    def _build_goal_progress(self, goal_trace: GoalTrace | None) -> GoalProgressView | None:
        if goal_trace is None:
            return None

        active = goal_trace.active_proposal()
        if active is None:
            return GoalProgressView(intent=goal_trace.intent.normalized_goal)

        conditions = tuple(
            GoalProgressConditionView(
                condition_id=condition.condition_id,
                label=condition.label,
                kind=condition.kind,
                target_kind=condition.target_kind,
                requiredness=condition.requiredness,
                status=condition.status,
                matched_finding_ids=condition.matched_finding_ids,
                year=condition.filters.get("year")
                if isinstance(condition.filters.get("year"), int)
                else None,
                min_count=condition.min_count,
            )
            for condition in active.conditions
        )
        satisfied = sum(1 for condition in conditions if condition.status == "satisfied")
        pending = sum(1 for condition in conditions if condition.status != "satisfied")
        return GoalProgressView(
            intent=goal_trace.intent.normalized_goal,
            active_proposal_id=active.proposal_id,
            active_proposal_summary=active.summary,
            proposal_status=active.status,
            satisfied_conditions=satisfied,
            pending_conditions=pending,
            conditions=conditions,
        )

    def _build_anchor(self, anchor: AnchorState | None) -> AnchorView | None:
        if anchor is None:
            return None
        return AnchorView(
            anchor_id=anchor.anchor_id,
            anchor_url=anchor.anchor_url,
            root_node_id=anchor.root_node_id,
            label=anchor.label,
        )

    def _build_active_path(
        self,
        *,
        anchor: AnchorState | None,
        active_path: ActivePathState | None,
    ) -> ActivePathView | None:
        if anchor is None or active_path is None or not active_path.steps:
            return None

        prefix = tuple(step.canonical_url for step in active_path.steps[-3:])
        tip = active_path.tip()
        return ActivePathView(
            anchor_url=anchor.anchor_url,
            current_url=tip.canonical_url if tip is not None else "",
            current_node_id=tip.node_id if tip is not None else None,
            path_depth=max(0, len(active_path.steps) - 1),
            semantic_prefix=prefix,
        )

    def _build_path_context(
        self,
        *,
        node: GraphNodeState,
        anchor: AnchorState | None,
        active_path: ActivePathState | None,
        choice_points_count: int,
    ) -> PathContextView | None:
        if active_path is None or not active_path.steps:
            return None

        current_url = node.canonical_url
        arrived_from_url = None
        if len(active_path.steps) >= 2:
            arrived_from_url = active_path.steps[-2].canonical_url
        elif anchor is not None:
            arrived_from_url = anchor.anchor_url

        return PathContextView(
            current_url=current_url,
            arrived_from_url=arrived_from_url,
            path_depth=max(0, len(active_path.steps) - 1),
            recoverable_choice_points=choice_points_count,
        )

    def _build_relevant_findings(
        self,
        findings: tuple[FindingRecord, ...],
    ) -> RelevantFindingsView | None:
        if not findings:
            return RelevantFindingsView(total_count=0, items=())

        items: list[RelevantFindingViewItem] = []
        for finding in findings[:5]:
            source_url = finding.evidence[0].source_url if finding.evidence else None
            year = finding.attributes.get("year") if isinstance(finding.attributes, dict) else None
            document_family = (
                finding.attributes.get("document_family")
                if isinstance(finding.attributes, dict)
                else None
            )
            items.append(
                RelevantFindingViewItem(
                    finding_id=finding.finding_id,
                    label=finding.label,
                    value=finding.value,
                    kind=getattr(finding.kind, "value", str(finding.kind)),
                    confidence=finding.confidence,
                    source_url=source_url,
                    year=year if isinstance(year, int) else None,
                    document_family=str(document_family) if document_family else None,
                )
            )

        return RelevantFindingsView(total_count=len(findings), items=tuple(items))

    def _build_scratchpad(
        self,
        tactical_scratchpad: TraversalScratchpad | None,
    ) -> TacticalScratchpadView | None:
        if tactical_scratchpad is None:
            return TacticalScratchpadView()
        return TacticalScratchpadView(
            working_plan=tactical_scratchpad.working_plan,
            tactical_observations=tactical_scratchpad.tactical_observations,
            notes=tactical_scratchpad.notes,
        )

    def _build_navigation_perception(
        self,
        *,
        navigation_perception: NavigationPerceptionResult | None,
        pending_edges: tuple[EdgeState, ...],
        all_edges_from_node: tuple[EdgeState, ...] = (),
        can_refine_navigation_perception: bool = True,
        refine_navigation_perception_reason: str | None = None,
    ) -> NavigationPerceptionView | None:
        if navigation_perception is None:
            return None

        edge_by_url = {
            self._normalize_url(edge.target_url): edge.edge_id
            for edge in all_edges_from_node
            if self._normalize_url(edge.target_url)
        }
        if not edge_by_url:
            edge_by_url = {
                self._normalize_url(edge.target_url): edge.edge_id
                for edge in pending_edges
                if self._normalize_url(edge.target_url)
            }
        observations = tuple(
            NavigationPerceptionCandidateView(
                edge_id=edge_by_url.get(self._normalize_url(item.url)),
                url=item.url,
                label=item.label,
                score=item.score,
                rationale=item.rationale,
                supports_condition_labels=item.supports_condition_labels,
                target_document_kind_match=item.target_document_kind_match,
                temporal_match=item.temporal_match,
                progress_likelihood=item.progress_likelihood,
                is_intra_page_anchor=item.is_intra_page_anchor,
            )
            for item in navigation_perception.top_candidate_observations[:5]
        )

        return NavigationPerceptionView(
            status=navigation_perception.status,
            confidence=navigation_perception.confidence,
            layout_kind=navigation_perception.layout_kind,
            recommended_next_step=navigation_perception.recommended_next_step,
            navigation_frame_detected=navigation_perception.navigation_frame_detected,
            content_frame_detected=navigation_perception.content_frame_detected,
            visible_candidate_count=navigation_perception.visible_candidate_count,
            produced_meaningful_delta=navigation_perception.produced_meaningful_delta,
            goal_slice_exhausted=navigation_perception.goal_slice_exhausted,
            goal_slice_exhaustion_reason=navigation_perception.goal_slice_exhaustion_reason,
            immediate_condition_gain=navigation_perception.immediate_condition_gain,
            best_immediate_condition_labels=navigation_perception.best_immediate_condition_labels,
            current_node_document_family=(
                None
                if navigation_perception.current_node_goal_match is None
                else navigation_perception.current_node_goal_match.document_family
            ),
            current_node_supports_condition_labels=(
                ()
                if navigation_perception.current_node_goal_match is None
                else navigation_perception.current_node_goal_match.supports_condition_labels
            ),
            current_node_match_rationale=(
                None
                if navigation_perception.current_node_goal_match is None
                else navigation_perception.current_node_goal_match.rationale
            ),
            current_node_match_confidence=(
                None
                if navigation_perception.current_node_goal_match is None
                else navigation_perception.current_node_goal_match.confidence
            ),
            strategic_return_suggested=navigation_perception.strategic_return_suggested,
            strategic_return_reason=navigation_perception.strategic_return_reason,
            strategic_return_priority=navigation_perception.strategic_return_priority,
            can_refine_navigation_perception=can_refine_navigation_perception,
            refine_navigation_perception_reason=refine_navigation_perception_reason,
            summary=navigation_perception.summary,
            top_candidate_observations=observations,
        )

    def _build_goal_validation(
        self,
        *,
        node: GraphNodeState,
        last_artifact_result: dict[str, object] | None,
        last_inspection_result: dict[str, object] | None,
        current_node_goal_validation: dict[str, object] | None,
        current_node_goal_validation_state: DocumentValidationNodeState | None,
        findings: tuple[FindingRecord, ...],
        goal_trace: GoalTrace | None,
    ) -> GoalValidationView | None:
        payload = self._extract_goal_validation_payload(
            node=node,
            artifact_result=last_artifact_result,
            inspection_result=last_inspection_result,
            current_node_goal_validation=current_node_goal_validation,
        )
        if payload is None:
            return None

        metadata = payload.get("metadata")
        metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}

        validation_status = self._coerce_optional_str(
            metadata_dict.get("validation_status") or payload.get("status")
        )

        can_revalidate_current_node = (
            False
            if current_node_goal_validation_state is None
            else current_node_goal_validation_state.can_revalidate
        )
        revalidate_reason = (
            "no_validation_state_for_current_evidence"
            if current_node_goal_validation_state is None
            else current_node_goal_validation_state.reason
        )

        matched_here: set[str] = set()
        for finding in findings:
            if not finding.evidence:
                continue
            if finding.evidence[0].source_node_id != node.node_id:
                continue
            attrs = finding.attributes if isinstance(finding.attributes, dict) else {}
            if str(attrs.get("validation_status") or "").strip().lower() != "validated":
                continue
            matched_here.update(
                str(item).strip()
                for item in (attrs.get("matched_condition_ids") or ())
                if str(item).strip()
            )

        active = None if goal_trace is None else goal_trace.active_proposal()
        pending_ids = {
            condition.condition_id
            for condition in (active.conditions if active is not None else ())
            if condition.status != "satisfied"
        }

        # Safety net de vista:
        # si esta evidencia/nodo ya produjo matches validados y aún quedan pendientes globales,
        # no empujes revalidación local; empuja siblings/candidates.
        if matched_here and pending_ids:
            can_revalidate_current_node = False
            revalidate_reason = "current_evidence_consumed_try_sibling_edges"

        # Si la validación local ya salió "validated" y no hay state claro,
        # sigue siendo más seguro no revalidar lo mismo.
        if validation_status == "validated" and current_node_goal_validation_state is None:
            can_revalidate_current_node = False
            revalidate_reason = "current_evidence_consumed_try_sibling_edges"

        return GoalValidationView(
            available=True,
            target_kind=self._coerce_optional_str(payload.get("target_kind")),
            validation_status=validation_status,
            summary=self._coerce_optional_str(payload.get("summary")),
            confidence=self._coerce_optional_float(payload.get("confidence")),
            document_family=self._latest_document_family_from_findings(node=node, findings=findings),
            source_action=self._coerce_optional_str(
                metadata_dict.get("source_action") or payload.get("source_action")
            ),
            recommended_next_step=self._coerce_optional_str(payload.get("recommended_next_step")),
            can_revalidate_current_node=can_revalidate_current_node,
            revalidate_reason=revalidate_reason,
        )

    def _extract_goal_validation_payload(
        self,
        *,
        node: GraphNodeState,
        artifact_result: dict[str, object] | None,
        inspection_result: dict[str, object] | None,
        current_node_goal_validation: dict[str, object] | None,
    ) -> dict[str, object] | None:
        if isinstance(current_node_goal_validation, dict):
            return current_node_goal_validation
        if isinstance(artifact_result, dict):
            payload = artifact_result.get("local_perception")
            if isinstance(payload, dict):
                return payload
        if isinstance(inspection_result, dict):
            payload = inspection_result.get("local_perception")
            if isinstance(payload, dict):
                page_url = self._coerce_optional_str(inspection_result.get("page_url"))
                if page_url is None or page_url == node.canonical_url:
                    return payload
        return None

    def _latest_document_family_from_findings(
        self,
        *,
        node: GraphNodeState,
        findings: tuple[FindingRecord, ...],
    ) -> str | None:
        for finding in reversed(findings):
            if not finding.evidence:
                continue
            if finding.evidence[0].source_node_id != node.node_id:
                continue
            attrs = finding.attributes if isinstance(finding.attributes, dict) else {}
            family = attrs.get("document_family")
            if family:
                return str(family)
        return None

    @staticmethod
    def _normalize_url(value: str | None) -> str:
        return str(value or "").strip()

    @staticmethod
    def _coerce_optional_str(value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _coerce_optional_float(value: object) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_strategic_return_point(
        self,
        strategic_return_point: object | None,
        *,
        goal_trace: GoalTrace | None = None,
    ) -> StrategicReturnPointView | None:
        if strategic_return_point is None:
            return None
        node_id = getattr(strategic_return_point, "node_id", None)
        canonical_url = getattr(strategic_return_point, "canonical_url", None)
        if not node_id or not canonical_url:
            return None
        supports_condition_ids = self._infer_strategic_return_supports(
            strategic_return_point,
            goal_trace=goal_trace,
        )
        return StrategicReturnPointView(
            node_id=str(node_id),
            url=str(canonical_url),
            priority=float(getattr(strategic_return_point, "priority", 0.0) or 0.0),
            supports_condition_ids=supports_condition_ids,
            kind=self._infer_strategic_return_kind(strategic_return_point),
            reason=getattr(strategic_return_point, "reason", None),
        )

    def _infer_strategic_return_supports(
        self,
        strategic_return_point: object,
        *,
        goal_trace: GoalTrace | None,
    ) -> tuple[str, ...]:
        active = None if goal_trace is None else goal_trace.active_proposal()
        if active is None:
            return ()
        text = " ".join(
            filter(
                None,
                [
                    str(getattr(strategic_return_point, "canonical_url", "") or "").lower(),
                    str(getattr(strategic_return_point, "reason", "") or "").lower(),
                ],
            )
        )
        matched: list[str] = []
        for condition in active.conditions:
            if condition.status == "satisfied":
                continue
            year = condition.filters.get("year")
            if isinstance(year, int) and str(year) in text:
                matched.append(condition.condition_id)
                continue
            tokens = [
                token
                for token in (
                    f"{str(condition.target_kind or '').replace('_', ' ')} "
                    f"{str(condition.label or '')}"
                ).lower().split()
                if len(token) >= 4
            ]
            if tokens and any(token in text for token in tokens):
                matched.append(condition.condition_id)
        return tuple(matched[:2])

    @staticmethod
    def _infer_strategic_return_kind(strategic_return_point: object) -> str | None:
        text = " ".join(
            filter(
                None,
                [
                    str(getattr(strategic_return_point, "canonical_url", "") or "").lower(),
                    str(getattr(strategic_return_point, "reason", "") or "").lower(),
                ],
            )
        )
        if re.search(r"\b20\d{2}\b", text):
            return "year_hub"
        return "pivot"

    def _build_choice_points(
        self,
        choice_points: tuple[object, ...],
        goal_trace: GoalTrace | None = None,
    ) -> ChoicePointsView | None:
        if not choice_points:
            return ChoicePointsView(total_count=0, top_items=())

        pending_years = pending_years_from_goal_trace(goal_trace)

        sorted_points = sorted(
            choice_points,
            key=lambda item: (
                year_alignment_score(
                    str(getattr(item, "target_url", "") or ""),
                    str(getattr(item, "label", "") or ""),
                    pending_years,
                ),
                float(getattr(item, "priority", 0.0) or 0.0),
            ),
            reverse=True,
        )

        top_items: list[ChoicePointViewItem] = []
        for item in sorted_points[:7]:
            choice_point_id = getattr(item, "choice_point_id", None)
            edge_id = getattr(item, "edge_id", None)
            target_url = getattr(item, "target_url", None)
            priority = getattr(item, "priority", 0.0)
            discovery_reason = getattr(item, "discovery_reason", None)

            if not choice_point_id or not edge_id or not target_url:
                continue

            top_items.append(
                ChoicePointViewItem(
                    choice_point_id=choice_point_id,
                    edge_id=edge_id,
                    target_url=target_url,
                    priority=float(priority or 0.0),
                    discovery_reason=discovery_reason,
                )
            )

        return ChoicePointsView(
            total_count=len(choice_points),
            top_items=tuple(top_items),
        )

    def _build_restrictions(
        self,
        *,
        node: GraphNodeState,
        scope: ExplorationScopeState,
    ) -> tuple[str, ...]:
        restrictions: list[str] = [
            "evita candidatos terminalmente fallidos",
            "evita repetir demasiados intentos",
            "prefiere progreso estructural",
        ]

        if node.exhausted:
            restrictions.append("el nodo actual ya fue marcado como agotado")

        if node.visited_count >= 2:
            restrictions.append("ten cuidado con reentradas repetidas")

        if scope.rejected_edge_ids:
            restrictions.append("evita edges ya rechazados por este scope")

        if scope.opened_artifact_urls:
            restrictions.append("considera artifacts ya abiertos antes de repetir rutas")

        return tuple(restrictions)

    def _candidate_reason(self, edge: EdgeState) -> str | None:
        if edge.is_terminal_failure():
            return "terminal_failure"
        if edge.attempt_count >= 2:
            return "high_repetition"
        if edge.delivery_mode == "direct":
            return "direct_artifact_candidate"
        if edge.delivery_mode == "bridge":
            return "bridge_candidate"
        return None

    def _candidate_hint(self, edge: EdgeState) -> str | None:
        if edge.resource_kind == "pdf_document":
            return "document_candidate"
        if edge.table_heading or edge.adjacent_cell_text:
            return "table_context_candidate"
        if edge.same_host is True:
            return "same_host_candidate"
        return None