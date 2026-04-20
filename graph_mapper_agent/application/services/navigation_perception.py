from __future__ import annotations
#graph_mapper_agent/application/services/navigation_perception.py
from dataclasses import dataclass, replace
import unicodedata

from graph_mapper_agent.application.goal_validation.artifact_models import (
    GoalValidationArtifact,
)
from graph_mapper_agent.application.goal_validation.validation_models import (
    GoalCondition,
)
from graph_mapper_agent.application.navigation_perception.models import (
    NavigationPerceptionRequest,
    NavigationPerceptionResult,
)
from graph_mapper_agent.application.navigation_perception.service import (
    NavigationPerceptionService,
)
from graph_mapper_agent.application.local_perception.models import (
    LocalPerceptionRequest,
    LocalPerceptionTargetRef,
)
from graph_mapper_agent.application.local_perception.service import (
    LocalPerceptionService,
)

from graph_mapper_agent.application.services.finding_extractor import (
    FindingExtractor,
)
from graph_mapper_agent.application.services.goals.models import (
    GoalTrace,
)
from graph_mapper_agent.application.contracts.runtime_views import (
    RuntimeNavigationPerceptionPort,
)
from graph_mapper_agent.domain.graph import GraphNodeState
from graph_mapper_agent.domain.graph_merge import (
    MergeObservedCandidatesResult,
    ObservedCandidateMergePolicy,
)
from graph_mapper_agent.domain.findings import FindingRecord


def navigation_perception_result_signature(
    result: NavigationPerceptionResult | None,
) -> str | None:
    if result is None:
        return None
    top_candidates = tuple(
        (
            str(item.url or "").strip(),
            str(item.label or "").strip(),
            round(float(item.score or 0.0), 3),
            tuple(
                str(value).strip()
                for value in item.supports_condition_labels
                if str(value).strip()
            ),
            str(item.progress_likelihood or "").strip(),
        )
        for item in result.top_candidate_observations[:5]
    )
    payload = (
        str(result.layout_kind or "").strip(),
        str(result.recommended_next_step or "").strip(),
        bool(result.goal_slice_exhausted),
        int(result.immediate_condition_gain or 0),
        tuple(
            str(value).strip()
            for value in result.best_immediate_condition_labels
            if str(value).strip()
        ),
        bool(result.produced_meaningful_delta),
        top_candidates,
    )
    return repr(payload)


def navigation_perception_context_signature(
    *,
    node: GraphNodeState,
    goal_trace: GoalTrace | None,
    all_edges_from_node: tuple[object, ...],
) -> str:
    active = None if goal_trace is None else goal_trace.active_proposal()
    pending_conditions = ()
    if active is not None:
        pending_conditions = tuple(
            (
                str(condition.condition_id or "").strip(),
                str(condition.target_kind or "").strip(),
                condition.filters.get("year"),
            )
            for condition in active.conditions
            if condition.status != "satisfied"
        )
    edge_fingerprint = tuple(
        sorted(
            (
                str(getattr(edge, "target_url", "") or "").strip(),
                str(getattr(edge, "label", "") or "").strip(),
                str(getattr(edge, "delivery_mode", "") or "").strip(),
                str(getattr(edge, "status", "") or "").strip(),
            )
            for edge in all_edges_from_node
            if str(getattr(edge, "target_url", "") or "").strip()
        )
    )
    payload = (
        node.node_id,
        str(node.canonical_url or "").strip(),
        str(getattr(node.page_type, "value", node.page_type) or "").strip(),
        round(float(node.page_type_confidence or 0.0), 3),
        pending_conditions,
        edge_fingerprint,
    )
    return repr(payload)


@dataclass(slots=True, frozen=True)
class NavigationPerceptionTriggerPolicy:
    high_candidate_count_threshold: int = 10
    low_confidence_threshold: float = 0.75

    def should_run(self, *, runtime: GraphMapperState, node: GraphNodeState) -> bool:
        prior_result = runtime.navigation_perception_by_node.get(node.node_id)
        if prior_result is not None:
            return False

        if runtime.has_frozen_dom_snapshot(node.node_id):
            return True

        candidate_count = len(runtime.graph.pending_edges_from_node(node.node_id))
        if candidate_count == 0:
            return False

        if node.visited_count <= 1:
            return True

        if candidate_count >= self.high_candidate_count_threshold:
            return True

        confidence = float(node.page_type_confidence or 0.0)
        if confidence <= self.low_confidence_threshold:
            return True

        page_type = str(getattr(node.page_type, "value", node.page_type) or "unknown")
        if page_type in {"unknown", "table_index", "calendar_index"}:
            return True

        return False


@dataclass(slots=True, frozen=True)
class NavigationPerceptionIntentBuilder:
    max_pattern_hints: int = 6
    include_screenshot: bool = False

    def build(
        self,
        *,
        node: GraphNodeState,
        goal_context: str,
        goal_trace: GoalTrace | None,
        findings: tuple[FindingRecord, ...],
    ) -> NavigationPerceptionRequest:
        question = goal_context.strip() or "Refinar navegacion local del nodo actual."
        goal_summary = goal_context.strip() or None
        pending_goal_conditions: list[str] = []
        target_document_kinds: list[str] = []
        temporal_constraints: list[str] = []
        hint_parts: list[str] = []

        active = None if goal_trace is None else goal_trace.active_proposal()
        if active is not None:
            goal_summary = active.summary or goal_summary
            pending = [
                condition for condition in active.conditions if condition.status != "satisfied"
            ]
            if pending:
                pending_goal_conditions = [
                    condition.label for condition in pending if condition.label
                ]
                target_document_kinds = [
                    condition.target_kind
                    for condition in pending
                    if str(condition.target_kind or "").strip()
                ]
                question = self._build_multi_goal_question(
                    pending_goal_conditions=pending_goal_conditions,
                    node=node,
                )
                for condition in pending:
                    hint_parts.extend(self._extract_hint_tokens(condition.label))
                    hint_parts.extend(self._extract_hint_tokens(condition.target_kind))
                    year = condition.filters.get("year")
                    if isinstance(year, int):
                        temporal_constraints.append(str(year))

        if not hint_parts:
            hint_parts.extend(self._extract_hint_tokens(question))

        for finding in findings[:3]:
            if finding.label:
                hint_parts.extend(self._extract_hint_tokens(finding.label))

        deduped_hints = self._dedupe(hint_parts)[: self.max_pattern_hints]
        deduped_temporal = tuple(self._dedupe(temporal_constraints))
        deduped_target_kinds = tuple(self._dedupe(target_document_kinds))
        deduped_pending = tuple(self._dedupe(pending_goal_conditions))
        return NavigationPerceptionRequest(
            question=question,
            node_id=node.node_id,
            url=node.canonical_url,
            pattern_hints=tuple(deduped_hints),
            goal_summary=goal_summary,
            pending_goal_conditions=deduped_pending,
            target_document_kinds=deduped_target_kinds,
            temporal_constraints=deduped_temporal,
            include_screenshot=self.include_screenshot,
            metadata={
                "node_status": node.status,
                "visited_count": node.visited_count,
                "page_type": getattr(node.page_type, "value", str(node.page_type)),
            },
        )

    @staticmethod
    def _build_multi_goal_question(
        *,
        pending_goal_conditions: list[str],
        node: GraphNodeState,
    ) -> str:
        if not pending_goal_conditions:
            return "Refinar navegacion local del nodo actual."
        node_url = str(node.canonical_url or "").strip()
        joined = "; ".join(condition for condition in pending_goal_conditions if condition)
        return (
            "Evaluar este nodo local contra todas las condiciones pendientes y "
            "priorizar el mejor progreso inmediato sin sesgarte a la primera. "
            f"Condiciones pendientes: {joined}. "
            f"URL actual: {node_url}"
        )

    @staticmethod
    def _extract_hint_tokens(text: str) -> list[str]:
        normalized = NavigationPerceptionIntentBuilder._normalize_text(text)
        tokens: list[str] = []
        for token in normalized.replace("_", " ").split():
            if len(token) >= 3:
                tokens.append(token)
        return tokens

    @staticmethod
    def _normalize_text(text: str) -> str:
        raw = str(text or "").strip().lower()
        decomposed = unicodedata.normalize("NFKD", raw)
        return "".join(
            ch if ch.isalnum() or ch in {"_", " "} else " "
            for ch in decomposed
            if not unicodedata.combining(ch)
        )

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        deduped: list[str] = []
        for value in values:
            if value not in deduped:
                deduped.append(value)
        return deduped


@dataclass(slots=True)
class NavigationPerceptionCoordinator:
    service: NavigationPerceptionService
    trigger_policy: NavigationPerceptionTriggerPolicy
    intent_builder: NavigationPerceptionIntentBuilder
    candidate_merge_policy: ObservedCandidateMergePolicy
    finding_extractor: FindingExtractor | None = None
    local_perception_service: LocalPerceptionService | None = None
    document_validation_state_updater: object | None = None

    def run_if_needed(
        self,
        *,
        runtime: RuntimeNavigationPerceptionPort,
        node: GraphNodeState,
        goal_context: str,
        goal_trace: GoalTrace | None,
        findings: tuple[FindingRecord, ...],
    ) -> NavigationPerceptionResult | None:
        if not self.trigger_policy.should_run(runtime=runtime, node=node):
            return runtime.navigation_perception_by_node.get(node.node_id)

        request = self.intent_builder.build(
            node=node,
            goal_context=goal_context,
            goal_trace=goal_trace,
            findings=findings,
        )
        request = _inject_validation_state_metadata(
            runtime=runtime,
            node=node,
            request=request,
        )

        print(
            f"[debug.np.coordinator.pre] node_id={node.node_id!r} "
            f"has_frozen={runtime.has_frozen_dom_snapshot(node.node_id)} "
            f"search_exists={node.node_id in runtime.search_result_by_node}",
            flush=True,
        )

        if not self.trigger_policy.should_run(runtime=runtime, node=node):
            print(
                f"[debug.np.coordinator.skip] omitiendo percepción para {node.node_id!r} "
                f"(ya tiene resultado o no cumple criterios)",
                flush=True,
            )
            return runtime.navigation_perception_by_node.get(node.node_id)

        request = _inject_snapshot_if_available(runtime=runtime, node=node, request=request)
        result = self.service.perceive(request)
        merge_result = self.candidate_merge_policy.merge(
            graph=runtime.graph,
            node=node,
            observed_candidates=result.observed_candidates,
            observed_step=runtime.step_count,
        )
        runtime.navigation_perception_by_node[node.node_id] = result
        runtime.navigation_perception_merge_by_node[node.node_id] = merge_result
        self._handle_current_node_match(
            runtime=runtime,
            node=node,
            goal_trace=goal_trace,
            result=result,
        )
        return result

    def run_explicit(
        self,
        *,
        runtime: RuntimeNavigationPerceptionPort,
        node: GraphNodeState,
        goal_context: str,
        goal_trace: GoalTrace | None,
        findings: tuple[FindingRecord, ...],
        max_explicit_runs_per_node: int = 1,
    ) -> NavigationPerceptionResult:
        explicit_runs = runtime.navigation_perception_explicit_runs_by_node.get(
            node.node_id, 0
        )
        if explicit_runs >= max_explicit_runs_per_node:
            existing = runtime.navigation_perception_by_node.get(node.node_id)
            if existing is not None:
                return existing

        request = self.intent_builder.build(
            node=node,
            goal_context=goal_context,
            goal_trace=goal_trace,
            findings=findings,
        )
        request = _inject_validation_state_metadata(
            runtime=runtime,
            node=node,
            request=request,
        )

        print(
            f"[debug.np.coordinator.pre] node_id={node.node_id!r} "
            f"has_frozen={runtime.has_frozen_dom_snapshot(node.node_id)} "
            f"search_exists={node.node_id in runtime.search_result_by_node}",
            flush=True,
        )

        if not self.trigger_policy.should_run(runtime=runtime, node=node):
            print(
                f"[debug.np.coordinator.skip] omitiendo percepción para {node.node_id!r} "
                f"(ya tiene resultado o no cumple criterios)",
                flush=True,
            )
            return runtime.navigation_perception_by_node.get(node.node_id)

        request = _inject_snapshot_if_available(runtime=runtime, node=node, request=request)
        result = self.service.perceive(request)
        merge_result = self.candidate_merge_policy.merge(
            graph=runtime.graph,
            node=node,
            observed_candidates=result.observed_candidates,
            observed_step=runtime.step_count,
        )
        runtime.navigation_perception_by_node[node.node_id] = result
        runtime.navigation_perception_merge_by_node[node.node_id] = merge_result
        runtime.navigation_perception_explicit_runs_by_node[node.node_id] = (
            explicit_runs + 1
        )
        self._handle_current_node_match(
            runtime=runtime,
            node=node,
            goal_trace=goal_trace,
            result=result,
        )
        return result

    @staticmethod
    def merge_result_for_node(
        runtime: RuntimeNavigationPerceptionPort,
        node_id: str,
    ) -> MergeObservedCandidatesResult | None:
        return runtime.navigation_perception_merge_by_node.get(node_id)

    def _handle_current_node_match(
        self,
        *,
        runtime: RuntimeNavigationPerceptionPort,
        node: GraphNodeState,
        goal_trace: GoalTrace | None,
        result: NavigationPerceptionResult,
    ) -> None:
        if result.current_node_goal_match is None:
            return
        if self.local_perception_service is None or self.finding_extractor is None:
            return
        node_validation_state = runtime.goal_validation_state_by_node.get(node.node_id)
        if node_validation_state is not None and not node_validation_state.can_revalidate:
            return

        inspection_result = runtime.inspection_result_by_node.get(node.node_id)
        if not isinstance(inspection_result, dict):
            return
        if _looks_like_index_family(result.current_node_goal_match.document_family):
            return
        content = _optional_str(inspection_result.get("content")) or _optional_str(
            inspection_result.get("text_excerpt")
        )
        if not content or len(content.strip()) < 120:
            return
        if not _inspection_looks_like_terminal_document(inspection_result):
            return

        artifact = GoalValidationArtifact(
            local_path=None,
            source_url=_optional_str(inspection_result.get("page_url")) or node.canonical_url,
            filename=_optional_str(inspection_result.get("title")) or node.title or None,
            inline_text=content,
        )
        question, pattern_hints, goal_conditions = _build_current_node_validation_intent(
            node=node,
            goal_trace=goal_trace,
            result=result,
        )
        local_result = self.local_perception_service.perceive(
            LocalPerceptionRequest(
                target_kind="inline_document_content",
                question=question,
                target_ref=LocalPerceptionTargetRef(artifact=artifact),
                goal_conditions=goal_conditions,
                pattern_hints=pattern_hints,
                max_pages=1,
                page_budget=1,
                escalation_allowed=False,
                metadata={
                    "source_action": "navigation_perception_current_node_validation",
                    "node_id": node.node_id,
                    "current_node_document_family": result.current_node_goal_match.document_family,
                },
            )
        )
        payload = {
            "target_kind": local_result.target_kind,
            "status": local_result.status,
            "confidence": local_result.confidence,
            "summary": local_result.summary,
            "recommended_next_step": local_result.recommended_next_step,
            "metadata": dict(local_result.metadata),
        }
        runtime.goal_validation_payload_by_node[node.node_id] = payload
        if self.document_validation_state_updater is not None:
            self.document_validation_state_updater(
                runtime=runtime,
                node_id=node.node_id,
                payload=payload,
                inspection_result=inspection_result,
            )

        finding = self.finding_extractor.from_navigation_perception_current_node(
            node_id=node.node_id,
            source_url=node.canonical_url,
            match=result.current_node_goal_match,
            summary=result.summary,
        )
        if finding is not None:
            finding = self.finding_extractor.from_open_artifact(
                node_id=node.node_id,
                source_url=node.canonical_url,
                edge_id=None,
                edge_label=finding.label,
                artifact_text=content,
                artifact_url=_optional_str(inspection_result.get("page_url"))
                or node.canonical_url,
                local_perception=payload,
                source_action="navigation_perception_current_node_validation",
            )
        if finding is None:
            return

        runtime.register_finding(finding)
        runtime.navigation_perception_current_node_finding_by_node[node.node_id] = (
            finding.finding_id
        )
        print(
            f"[navigation_perception.validation] validated current-node candidate "
            f"node_id={node.node_id!r} finding_id={finding.finding_id!r} "
            f"validation_status={payload.get('metadata', {}).get('validation_status') if isinstance(payload.get('metadata'), dict) else None!r}",
            flush=True,
        )


def _inject_snapshot_if_available(
    *,
    runtime: RuntimeNavigationPerceptionPort,
    node: GraphNodeState,
    request: NavigationPerceptionRequest,
) -> NavigationPerceptionRequest:
    snapshot = runtime.resolve_node_observation_snapshot(node.node_id)
    if snapshot:
        print(
            f"[debug.np.coordinator] inyectando snapshot en request "
            f"node_id={node.node_id!r} "
            f"candidate_count={len(list(snapshot.get('candidates') or []))}",
            flush=True,
        )
        updated_metadata = {
            **(request.metadata or {}),
            "frozen_snapshot": dict(snapshot),
        }
        return replace(request, metadata=updated_metadata)

    print(f"[debug.np.coordinator] sin snapshot para node_id={node.node_id!r}", flush=True)
    return request


def _inject_validation_state_metadata(
    *,
    runtime: RuntimeNavigationPerceptionPort,
    node: GraphNodeState,
    request: NavigationPerceptionRequest,
) -> NavigationPerceptionRequest:
    state = runtime.goal_validation_state_by_node.get(node.node_id)
    if state is None:
        return request

    updated_metadata = {
        **(request.metadata or {}),
        "current_node_can_revalidate": state.can_revalidate,
        "current_node_validation_status": state.last_validation_status,
        "current_node_validation_reason": state.reason,
        "current_node_last_matched_condition_ids": tuple(state.last_matched_condition_ids or ()),
        "current_node_last_evidence_signature": state.last_evidence_signature,
    }
    return replace(request, metadata=updated_metadata)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_current_node_validation_intent(
    *,
    node: GraphNodeState,
    goal_trace: GoalTrace | None,
    result: NavigationPerceptionResult,
) -> tuple[str, tuple[str, ...], tuple[GoalCondition, ...]]:
    current_match = result.current_node_goal_match
    if current_match is None:
        return (
            f"Validar si el contenido visible del nodo actual '{node.canonical_url}' satisface alguna condicion pendiente.",
            (),
            (),
        )

    active = None if goal_trace is None else goal_trace.active_proposal()
    if active is None:
        return (
            f"Validar si el nodo actual cumple el tipo documental {current_match.document_family}.",
            _dedupe_tokens(
                (
                    node.canonical_url,
                    node.title,
                    current_match.document_family,
                    *(current_match.supports_condition_labels or ()),
                )
            ),
            (),
        )

    pending = [condition for condition in active.conditions if condition.status != "satisfied"]
    goal_conditions = tuple(
        GoalCondition(
            condition_id=condition.condition_id,
            label=condition.label,
            target_kind=condition.target_kind,
            year=condition.filters.get("year")
            if isinstance(condition.filters.get("year"), int)
            else None,
            requiredness=condition.requiredness,
            min_count=condition.min_count,
        )
        for condition in pending
    )
    if not pending:
        return (
            f"Validar si el nodo actual cumple el tipo documental {current_match.document_family}.",
            _dedupe_tokens(
                (
                    node.canonical_url,
                    node.title,
                    current_match.document_family,
                    *(current_match.supports_condition_labels or ()),
                )
            ),
            (),
        )
    condition_lines = [
        f"{condition.label} (target_kind={condition.target_kind}, year={condition.filters.get('year')})"
        for condition in pending
    ]
    question = (
        "Determina si el contenido visible del nodo actual satisface alguna de las condiciones pendientes. "
        "Evalua solo el nodo actual, sin asumir por navegacion. "
        f"Condiciones pendientes: {'; '.join(condition_lines)}."
    )
    return (
        question,
        _dedupe_tokens(
            (
                node.canonical_url,
                node.title,
                current_match.document_family,
                *(current_match.supports_condition_labels or ()),
                *(condition.label for condition in pending),
                *(condition.target_kind for condition in pending),
            )
        ),
        goal_conditions,
    )


def _dedupe_tokens(parts: tuple[object, ...]) -> tuple[str, ...]:
    tokens: list[str] = []
    for part in parts:
        raw = str(part or "").strip().lower().replace("_", " ")
        for token in raw.split():
            token = token.strip(" ,.;:()[]{}'\"")
            if len(token) < 3:
                continue
            if token not in tokens:
                tokens.append(token)
    return tuple(tokens[:10])


def _looks_like_index_family(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    index_markers = (
        "index",
        "indice",
        "índice",
        "calendar",
        "hub",
        "listing",
        "listado",
    )
    return any(marker in text for marker in index_markers)


def _inspection_looks_like_terminal_document(inspection_result: dict[str, object]) -> bool:
    candidates = list(inspection_result.get("candidates") or ())
    if not candidates:
        return True
    candidate_count = _candidate_count_from_inspection(inspection_result)
    if candidate_count <= 2:
        return True
    non_anchor_candidates = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            non_anchor_candidates += 1
            continue
        if candidate.get("is_intra_page_anchor") is True:
            continue
        non_anchor_candidates += 1
    return non_anchor_candidates == 0


def _candidate_count_from_inspection(inspection_result: dict[str, object]) -> int:
    metadata = inspection_result.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    inspection_metadata = inspection_result.get("inspection_metadata")
    inspection_metadata_dict = (
        inspection_metadata if isinstance(inspection_metadata, dict) else {}
    )
    raw_value = (
        metadata_dict.get("candidate_count")
        or inspection_metadata_dict.get("candidate_count")
        or len(list(inspection_result.get("candidates") or ()))
    )
    try:
        return int(raw_value or 0)
    except (TypeError, ValueError):
        return 0


__all__ = [
    "NavigationPerceptionCoordinator",
    "NavigationPerceptionIntentBuilder",
    "NavigationPerceptionTriggerPolicy",
    "navigation_perception_context_signature",
    "navigation_perception_result_signature",
]
