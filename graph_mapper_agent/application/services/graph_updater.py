from __future__ import annotations
#graph_mapper_agent/application/services/graph_updater.py
from dataclasses import dataclass
from typing import Callable
from typing import Any
from uuid import uuid4

from graph_mapper_agent.application.contracts.runtime_views import (
    RuntimeUpdaterPort,
)
from graph_mapper_agent.application.services.finding_extractor import (
    FindingExtractor,
)
from graph_mapper_agent.domain.exploration_scope import (
    ArrivalContext,
)
from graph_mapper_agent.domain.path import PathStep

__all__ = ["GraphUpdater"]

_LOG_PREFIX = "[graph_mapper.updater]"
_FINDINGS_PREFIX = "[graph_mapper.findings]"
_GOALS_PREFIX = "[graph_mapper.goals]"

_ARTIFACT_TEXT_KEYS: tuple[str, ...] = (
    "text",
    "content_text",
    "extracted_text",
    "markdown_text",
)

_MAX_ARTIFACT_PAGES_TO_SCAN: int = 3


@dataclass(slots=True)
class _EdgeContext:
    edge: Any
    parent_node: Any

    @property
    def edge_id(self) -> str:
        return self.edge.edge_id

    @property
    def from_node_id(self) -> str:
        return self.edge.from_node_id

    @property
    def label(self) -> str:
        return self.edge.label

    @property
    def target_url(self) -> str:
        return self.edge.target_url


@dataclass(slots=True, frozen=True)
class GraphUpdater:
    finding_extractor: FindingExtractor | None = None
    document_validation_state_updater: Callable[..., None] | None = None

    def apply_action_result(
        self,
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object],
    ) -> None:
        action = str(action_result.get("action") or "").strip()
        status = str(action_result.get("status") or "").strip() or "ok"

        _log(
            f"apply_action_result action={action!r} "
            f"status={status!r} "
            f"step={getattr(runtime, 'step_count', None)!r}"
        )

        if status != "ok":
            self._apply_failed_action_result(runtime, action_result)
            return

        handler = self._action_handlers().get(action)
        if handler is not None:
            handler(runtime, action_result)
        else:
            _log(f"action ignorada action={action!r}")

    def _action_handlers(self) -> dict[str, Any]:
        return {
            "follow_edge": self._apply_follow_edge,
            "download_artifact": self._apply_download_artifact,
            "open_artifact": self._apply_open_artifact,
            "validate_current_content": self._apply_validate_current_content,
            "search_with_text": self._apply_search_with_text,
            "mark_exhausted": self._apply_mark_exhausted,
        }

    @staticmethod
    def _resolve_edge_context(
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object],
        caller: str,
    ) -> _EdgeContext | None:
        edge_id = _optional_str(action_result.get("edge_id"))
        if not edge_id:
            _log(f"{caller} sin edge_id")
            return None

        edge = runtime.graph.get_edge(edge_id)
        if edge is None:
            _log(f"{caller} edge no encontrado edge_id={edge_id!r}")
            return None

        parent_node = runtime.graph.get_node(edge.from_node_id)
        if parent_node is None:
            _log(f"{caller} parent_node no encontrado from_node_id={edge.from_node_id!r}")
            return None

        return _EdgeContext(edge=edge, parent_node=parent_node)

    @staticmethod
    def _mark_edge_useful(
        ec: _EdgeContext,
        runtime: RuntimeUpdaterPort,
    ) -> None:
        ec.edge.status = "useful"
        ec.parent_node.add_explored_edge(ec.edge_id)
        ec.parent_node.add_useful_edge(ec.edge_id)

    @staticmethod
    def _mark_edge_failed(
        ec: _EdgeContext,
        *,
        runtime: RuntimeUpdaterPort,
        outcome: str,
        error: str | None,
    ) -> None:
        ec.edge.mark_attempt(
            outcome=outcome,
            error=error,
            next_status="failed",
        )
        ec.parent_node.add_explored_edge(ec.edge_id)

        if ec.parent_node.has_pending_edges():
            ec.parent_node.mark_partially_exhausted()
        else:
            ec.parent_node.mark_exhausted()

        scope = runtime.get_active_scope()
        if scope is not None:
            scope.register_progress(f"failed_edge:{ec.edge_id}")

    def _apply_failed_action_result(
        self,
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object],
    ) -> None:
        action = str(action_result.get("action") or "").strip() or "unknown"
        reason = _optional_str(action_result.get("execution_reason")) or "action_failed"
        ec = self._resolve_edge_context(runtime, action_result, "_apply_failed_action_result")
        if ec is None:
            _log(
                f"failed action without edge context action={action!r} reason={reason!r}"
            )
            return

        self._mark_edge_failed(
            ec,
            runtime=runtime,
            outcome=action,
            error=reason,
        )

        addition = (
            f"\n[Paso {getattr(runtime, 'step_count', None)}] "
            f"⚠️ El edge '{ec.label}' falló durante '{action}'. Razón: {reason}."
        )
        existing = ec.parent_node.working_memory.local_summary or ""
        ec.parent_node.working_memory.local_summary = (existing + addition).strip()
        ec.parent_node.working_memory.revision_count += 1

        _log(
            f"failed edge action applied action={action!r} "
            f"edge_id={ec.edge_id!r} reason={reason!r}"
        )
        ec.parent_node.last_progress_step = runtime.step_count

    def _try_extract_and_register_finding(
        self,
        runtime: RuntimeUpdaterPort,
        *,
        node_id: str,
        source_url: str | None,
        edge_id: str | None,
        edge_label: str | None,
        local_perception: dict[str, object] | None,
        inspection_result: dict[str, object] | None = None,
        artifact_text: str | None = None,
        artifact_url: str | None = None,
        source_action: str = "action_validation",
    ) -> None:
        if self.finding_extractor is None:
            return

        if local_perception is None:
            return

        payload = dict(local_perception)
        metadata = dict(payload.get("metadata") or {})

        evidence_ref = (
            (artifact_url or "").strip()
            or _optional_str(None if inspection_result is None else inspection_result.get("page_url"))
            or _optional_str(None if inspection_result is None else inspection_result.get("final_url"))
            or source_url
        )
        if evidence_ref:
            metadata["evidence_ref"] = evidence_ref
        payload["metadata"] = metadata

        runtime.goal_validation_payload_by_node[node_id] = payload

        if self.document_validation_state_updater is not None:
            self.document_validation_state_updater(
                runtime=runtime,
                node_id=node_id,
                payload=payload,
                inspection_result=inspection_result,
                evidence_ref=evidence_ref,
            )

        finding = self.finding_extractor.from_open_artifact(
            node_id=node_id,
            source_url=source_url,
            edge_id=edge_id,
            edge_label=edge_label,
            artifact_text=artifact_text,
            artifact_url=artifact_url,
            local_perception=payload,
            source_action=source_action,
        )

        self._register_and_match_finding(runtime, finding)

    def _try_extract_download_finding(
        self,
        runtime: RuntimeUpdaterPort,
        *,
        node_id: str,
        source_url: str | None,
        edge_id: str | None,
        edge_label: str | None,
        artifact_url: str | None,
        download_result: dict[str, object],
    ) -> None:
        if self.finding_extractor is None:
            return

        try:
            finding = self.finding_extractor.from_download_artifact(
                node_id=node_id,
                source_url=source_url,
                edge_id=edge_id,
                edge_label=edge_label,
                artifact_url=artifact_url,
                download_result=download_result,
            )
        except AttributeError:
            _log(
                "WARNING: finding_extractor no implementa from_download_artifact(...)"
            )
            finding = None

        self._register_and_match_finding(runtime, finding)

    def _register_and_match_finding(
        self,
        runtime: RuntimeUpdaterPort,
        finding: object | None,
    ) -> None:
        if finding is None:
            _log("no finding to register")
            return

        runtime.register_finding(finding)

        _log_findings(
            f"registered "
            f"finding_id={getattr(finding, 'finding_id', None)!r} "
            f"label={getattr(finding, 'label', None)!r} "
            f"value={getattr(finding, 'value', None)!r}"
        )

        evaluated = runtime.evaluated_goal_trace()
        runtime.reprioritize_choice_points(evaluated)
        active = None if evaluated is None else evaluated.active_proposal()
        if active is None:
            _log_goals("no active dynamic goal proposal to evaluate")
            return

        satisfied = sum(1 for c in active.conditions if c.status == "satisfied")
        pending = sum(1 for c in active.conditions if c.status != "satisfied")
        _log_goals(
            f"dynamic evaluation updated "
            f"proposal_id={active.proposal_id!r} "
            f"satisfied={satisfied} pending={pending}"
        )

    def _apply_follow_edge(
        self,
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object],
    ) -> None:
        ec = self._resolve_edge_context(runtime, action_result, "_apply_follow_edge")
        if ec is None:
            return

        inspection_result = _safe_dict(action_result.get("inspection_result"))
        resolved_url = _optional_str(inspection_result.get("page_url")) or ec.target_url
        title = (
            _optional_str(inspection_result.get("title"))
            or _optional_str(inspection_result.get("page_title"))
            or ec.label
        )

        child_node = runtime.graph.ensure_node(
            node_id=ec.edge.child_node_id or f"node_{ec.edge_id}",
            canonical_url=resolved_url,
            title=title,
            is_root=False,
        )
        ec.edge.child_node_id = child_node.node_id

        if inspection_result:
            runtime.inspection_result_by_node[child_node.node_id] = dict(inspection_result)

        runtime.current_content_owner_node_id = child_node.node_id

        self._mark_edge_useful(ec, runtime)
        ec.parent_node.mark_expanded()

        arrival = self._create_arrival(
            runtime=runtime,
            child_node=child_node,
            ec=ec,
            arrival_mode="follow",
            discovery_reason="follow_edge",
        )
        runtime.register_arrival(arrival)

        runtime.current_node_id = child_node.node_id
        child_node.register_visit(arrival_context_id=arrival.arrival_context_id)

        addition = (
            f"\n[Paso {runtime.step_count}] ✅ Entré al link '{ec.label}'. "
            f"Progreso útil."
        )
        ec.parent_node.working_memory.local_summary = (
            ec.parent_node.working_memory.local_summary + addition
        ).strip()
        ec.parent_node.working_memory.revision_count += 1

        scope = runtime.get_active_scope()
        if scope is not None:
            scope.register_progress(f"follow_edge:{ec.edge_id}")
            scope.register_node(
                child_node.node_id,
                arrival_context_id=arrival.arrival_context_id,
            )

        if runtime.active_path is not None:
            runtime.active_path.append_step(
                PathStep(
                    path_step_id=f"path_step_{child_node.node_id}_{runtime.step_count}",
                    node_id=child_node.node_id,
                    canonical_url=child_node.canonical_url,
                    arrival_context_id=arrival.arrival_context_id,
                    depth=arrival.arrival_depth,
                    via_edge_id=ec.edge_id,
                )
            )

        _log(
            f"follow_edge applied "
            f"edge_id={ec.edge_id!r} "
            f"from_node={ec.from_node_id!r} "
            f"to_node={child_node.node_id!r} "
            f"resolved_url={resolved_url!r}"
        )

        local_perception = _safe_perception(inspection_result)
        if local_perception is not None:
            self._try_extract_and_register_finding(
                runtime,
                node_id=child_node.node_id,
                source_url=resolved_url,
                edge_id=ec.edge_id,
                edge_label=ec.label,
                local_perception=local_perception,
                inspection_result=inspection_result,
                artifact_text=(
                    _optional_str(inspection_result.get("content"))
                    or _optional_str(inspection_result.get("text_excerpt"))
                ),
                artifact_url=resolved_url,
                source_action="follow_edge_validation",
            )

    @staticmethod
    def _create_arrival(
        runtime: RuntimeUpdaterPort,
        child_node: Any,
        ec: _EdgeContext,
        arrival_mode: str,
        discovery_reason: str,
    ) -> ArrivalContext:
        scope = runtime.get_active_scope()
        parent_arrival = None
        if scope is not None:
            parent_arrival = runtime.get_arrival(scope.current_arrival_context_id)

        return ArrivalContext(
            arrival_context_id=f"arrival_{uuid4().hex[:12]}",
            node_id=child_node.node_id,
            from_node_id=ec.from_node_id,
            via_edge_id=ec.edge_id,
            arrival_depth=(
                (parent_arrival.arrival_depth + 1) if parent_arrival is not None else 1
            ),
            arrival_mode=arrival_mode,
            parent_scope_id=scope.scope_id if scope is not None else None,
            discovery_reason=discovery_reason,
            is_reentry=child_node.visited_count > 0,
            step_index=runtime.step_count,
        )

    def _apply_download_artifact(
        self,
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object],
    ) -> None:
        ec = self._resolve_edge_context(runtime, action_result, "_apply_download_artifact")
        if ec is None:
            return

        owner_node = _resolve_content_owner_node(runtime, ec.parent_node)
        download_result = _safe_dict(action_result.get("download_result"))

        artifact_url = (
            _optional_str(download_result.get("download_url"))
            or _optional_str(download_result.get("candidate_url"))
            or ec.target_url
        )

        runtime.download_result_by_node[owner_node.node_id] = dict(download_result)
        runtime.artifact_result_by_node.pop(owner_node.node_id, None)
        runtime.current_content_owner_node_id = owner_node.node_id

        self._mark_edge_useful(ec, runtime)

        if artifact_url:
            owner_node.add_artifact_url(artifact_url)

        filename = (
            _optional_str(download_result.get("filename"))
            or _optional_str(download_result.get("storage_ref"))
            or "artifact"
        )
        owner_node.working_memory.local_summary = (
            f"Se descargó el artifact '{filename}' desde el edge '{ec.label}'."
        )
        owner_node.working_memory.revision_count += 1

        scope = runtime.get_active_scope()
        if scope is not None:
            if artifact_url:
                scope.add_opened_artifact(artifact_url)
            scope.register_progress(f"download_artifact:{ec.edge_id}")

        _log(
            f"download_artifact applied "
            f"edge_id={ec.edge_id!r} "
            f"artifact_url={artifact_url!r} "
            f"filename={filename!r} "
            f"owner_node_id={owner_node.node_id!r}"
        )

        local_perception = _safe_perception(download_result)

        if local_perception is not None:
            self._try_extract_and_register_finding(
                runtime,
                node_id=owner_node.node_id,
                source_url=owner_node.canonical_url,
                edge_id=ec.edge_id,
                edge_label=ec.label,
                local_perception=local_perception,
                inspection_result=runtime.inspection_result_by_node.get(owner_node.node_id),
                artifact_url=artifact_url,
                source_action="download_artifact_validation",
            )
        else:
            self._try_extract_download_finding(
                runtime,
                node_id=owner_node.node_id,
                source_url=owner_node.canonical_url,
                edge_id=ec.edge_id,
                edge_label=ec.label,
                artifact_url=artifact_url,
                download_result=download_result,
            )

    def _apply_open_artifact(
        self,
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object],
    ) -> None:
        ec = self._resolve_edge_context(runtime, action_result, "_apply_open_artifact")
        if ec is None:
            return

        owner_node = _resolve_content_owner_node(runtime, ec.parent_node)
        download_result = _safe_dict(action_result.get("download_result"))
        artifact_result = _safe_dict(action_result.get("artifact_result"))

        artifact_url = (
            _optional_str(download_result.get("download_url"))
            or _optional_str(download_result.get("candidate_url"))
            or ec.target_url
        )

        runtime.download_result_by_node[owner_node.node_id] = dict(download_result)
        runtime.artifact_result_by_node[owner_node.node_id] = dict(artifact_result)
        runtime.current_content_owner_node_id = owner_node.node_id

        self._mark_edge_useful(ec, runtime)

        if artifact_url:
            owner_node.add_artifact_url(artifact_url)

        extracted_text = _extract_artifact_text(artifact_result)
        timestamp = runtime.step_count

        if extracted_text:
            snippet = extracted_text[:140].replace("\n", " ").strip()
            addition = (
                f"\n[Paso {timestamp}] 📖 Se abrió el artifact del edge "
                f"'{ec.label}'. Texto detectado: {snippet}"
            )
        else:
            addition = (
                f"\n[Paso {timestamp}] 📖 Se abrió el artifact del edge "
                f"'{ec.label}', sin texto extraíble claro."
            )

        existing = owner_node.working_memory.local_summary or ""
        owner_node.working_memory.local_summary = (existing + addition).strip()
        owner_node.working_memory.revision_count += 1

        scope = runtime.get_active_scope()
        if scope is not None:
            if artifact_url:
                scope.add_opened_artifact(artifact_url)
            scope.register_progress(f"open_artifact:{ec.edge_id}")

        _log(
            f"open_artifact applied "
            f"edge_id={ec.edge_id!r} "
            f"artifact_url={artifact_url!r} "
            f"text_detected={bool(extracted_text)} "
            f"owner_node_id={owner_node.node_id!r}"
        )

        local_perception = _safe_perception(artifact_result)

        if local_perception is not None:
            self._try_extract_and_register_finding(
                runtime,
                node_id=owner_node.node_id,
                source_url=owner_node.canonical_url,
                edge_id=ec.edge_id,
                edge_label=ec.label,
                local_perception=local_perception,
                inspection_result=runtime.inspection_result_by_node.get(owner_node.node_id),
                artifact_text=extracted_text,
                artifact_url=artifact_url,
            )
        elif self.finding_extractor is not None:
            finding = self.finding_extractor.from_open_artifact(
                node_id=owner_node.node_id,
                source_url=owner_node.canonical_url,
                edge_id=ec.edge_id,
                edge_label=ec.label,
                artifact_text=extracted_text,
                artifact_url=artifact_url,
                local_perception=None,
            )
            self._register_and_match_finding(runtime, finding)

    def _apply_mark_exhausted(
        self,
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object] | None = None,
    ) -> None:
        scope = runtime.get_active_scope()
        if scope is None or not scope.current_node_id:
            _log("_apply_mark_exhausted sin scope actual o sin current_node_id")
            return

        node = runtime.graph.get_node(scope.current_node_id)
        if node is None:
            _log(
                f"_apply_mark_exhausted node no encontrado "
                f"node_id={scope.current_node_id!r}"
            )
            return

        node.mark_exhausted()
        scope.register_progress("node_exhausted")

        if runtime.active_path is not None:
            tip = runtime.active_path.tip()
            if tip is not None:
                runtime.active_path.close_suffix_from(tip.path_step_id)

        _log(f"mark_exhausted applied node_id={node.node_id!r}")

    def _apply_validate_current_content(
        self,
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object],
    ) -> None:
        target_node_id = self._resolve_validation_target_node_id(runtime, action_result)
        if not target_node_id:
            _log("_apply_validate_current_content sin target_node_id resoluble")
            return

        node = runtime.graph.get_node(target_node_id)
        if node is None:
            _log(
                f"_apply_validate_current_content node no encontrado "
                f"node_id={target_node_id!r}"
            )
            return

        inspection_result = _optional_dict(action_result.get("inspection_result"))
        download_result = _optional_dict(action_result.get("download_result"))
        artifact_result = _optional_dict(action_result.get("artifact_result"))
        validation_target = action_result.get("validation_target")

        local_perception, evidence_ref_override = _resolve_validation_local_perception(
            validation_target=validation_target,
            inspection_result=inspection_result,
            download_result=download_result,
            artifact_result=artifact_result,
        )

        self._update_validation_caches(
            runtime=runtime,
            target_node_id=target_node_id,
            inspection_result=inspection_result,
            download_result=download_result,
            artifact_result=artifact_result,
            local_perception=local_perception,
            evidence_ref_override=evidence_ref_override,
        )

        scope = runtime.get_active_scope()
        if scope is not None:
            scope.register_progress(f"validate_current_content:{target_node_id}")

        source_kind = (
            _optional_str(getattr(validation_target, "source_kind", None))
            or "resolved_fallback"
        )

        node.last_progress_step = runtime.step_count
        node.working_memory.local_summary = (
            (node.working_memory.local_summary or "")
            + f"\n[Paso {runtime.step_count}] 🧪 Se validó contenido del nodo "
            f"'{node.node_id}' desde source_kind='{source_kind}'."
        ).strip()
        node.working_memory.revision_count += 1

        _log(
            f"validate_current_content applied "
            f"target_node_id={target_node_id!r} "
            f"source_kind={source_kind!r} "
            f"has_local_perception={local_perception is not None!r}"
        )

        if self.finding_extractor is not None and local_perception is not None:
            artifact_url = None
            artifact_text = None

            if source_kind == "download" and download_result is not None:
                artifact_url = (
                    _optional_str(download_result.get("download_url"))
                    or _optional_str(download_result.get("candidate_url"))
                )

            elif source_kind == "artifact":
                if download_result is not None:
                    artifact_url = (
                        _optional_str(download_result.get("download_url"))
                        or _optional_str(download_result.get("candidate_url"))
                    )
                if artifact_result is not None:
                    artifact_text = _extract_artifact_text(artifact_result)

            elif source_kind == "inspection" and inspection_result is not None:
                artifact_url = (
                    _optional_str(inspection_result.get("page_url"))
                    or _optional_str(inspection_result.get("final_url"))
                    or node.canonical_url
                )
                artifact_text = (
                    _optional_str(inspection_result.get("content"))
                    or _optional_str(inspection_result.get("text_excerpt"))
                )

            try:
                finding = self.finding_extractor.from_open_artifact(
                    node_id=target_node_id,
                    source_url=node.canonical_url,
                    edge_id=None,
                    edge_label=None,
                    artifact_text=artifact_text,
                    artifact_url=artifact_url,
                    local_perception=local_perception,
                    source_action="validate_current_content",
                )
            except TypeError:
                finding = None

            self._register_and_match_finding(runtime, finding)

    @staticmethod
    def _resolve_validation_target_node_id(
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object],
    ) -> str | None:
        validation_target = action_result.get("validation_target")
        return (
            _optional_str(getattr(validation_target, "node_id", None))
            or _optional_str(getattr(runtime, "current_content_owner_node_id", None))
            or _optional_str(getattr(runtime, "current_node_id", None))
        )

    def _update_validation_caches(
        self,
        runtime: RuntimeUpdaterPort,
        target_node_id: str,
        inspection_result: dict[str, object] | None,
        download_result: dict[str, object] | None,
        artifact_result: dict[str, object] | None,
        local_perception: dict[str, object] | None,
        evidence_ref_override: str | None = None,
    ) -> None:
        if inspection_result is not None:
            runtime.inspection_result_by_node[target_node_id] = dict(inspection_result)
            runtime.current_content_owner_node_id = target_node_id

        if download_result is not None:
            runtime.download_result_by_node[target_node_id] = dict(download_result)
            runtime.current_content_owner_node_id = target_node_id

        if artifact_result is not None:
            runtime.artifact_result_by_node[target_node_id] = dict(artifact_result)
            runtime.current_content_owner_node_id = target_node_id

        if local_perception is not None:
            payload = dict(local_perception)

            metadata = dict(payload.get("metadata") or {})
            evidence_ref = (
                evidence_ref_override
                or _resolve_evidence_ref(
                    inspection_result=inspection_result,
                    download_result=download_result,
                    artifact_result=artifact_result,
                )
            )
            if evidence_ref:
                metadata["evidence_ref"] = evidence_ref
            payload["metadata"] = metadata

            runtime.goal_validation_payload_by_node[target_node_id] = payload

            if self.document_validation_state_updater is not None:
                self.document_validation_state_updater(
                    runtime=runtime,
                    node_id=target_node_id,
                    payload=payload,
                    inspection_result=runtime.inspection_result_by_node.get(target_node_id),
                    evidence_ref=evidence_ref,
                )

    def _apply_search_with_text(
        self,
        runtime: RuntimeUpdaterPort,
        action_result: dict[str, object],
    ) -> None:
        print(
            "[debug.updater.search.enter] "
            f"current_node_id={runtime.current_node_id!r} "
            f"query_text={action_result.get('query_text')!r} "
            f"search_target_id={action_result.get('search_target_id')!r}",
            flush=True,
        )

        current_node_id = runtime.current_node_id
        if not current_node_id:
            _log("_apply_search_with_text sin current_node_id")
            return

        current_node = runtime.graph.get_node(current_node_id)
        if current_node is None:
            _log(f"_apply_search_with_text node no encontrado node_id={current_node_id!r}")
            return

        inspection_result = _safe_dict(action_result.get("inspection_result"))
        if not inspection_result:
            _log("_apply_search_with_text sin inspection_result")
            return

        query_text = _optional_str(action_result.get("query_text"))
        search_metadata = _optional_dict(inspection_result.get("search_metadata"))

        # FIX CENTRAL:
        # Si la búsqueda no encontró target o no produjo cambio real de estado,
        # no mutar el nodo, no congelar snapshot, no reinterpretar la misma página
        # como si fuera un resultado válido de búsqueda.
        if not _search_result_has_real_delta(
            current_node=current_node,
            inspection_result=inspection_result,
            search_metadata=search_metadata,
        ):
            status = (
                _optional_str(None if search_metadata is None else search_metadata.get("status"))
                or "unknown"
            )
            state_delta_kind = (
                _optional_str(
                    None if search_metadata is None else search_metadata.get("state_delta_kind")
                )
                or "unknown"
            )
            results_detected = (
                None if search_metadata is None else search_metadata.get("results_detected")
            )

            available_search_target_ids: list[str] = []
            if isinstance(search_metadata, dict):
                raw_available = search_metadata.get("available_search_target_ids") or []
                if isinstance(raw_available, (list, tuple)):
                    available_search_target_ids = [
                        str(item).strip()
                        for item in raw_available
                        if str(item).strip()
                    ]

            if query_text:
                runtime.register_search_query(current_node.node_id, query_text)

            current_node.working_memory.local_summary = (
                f"[Paso {runtime.step_count}] 🔎 Búsqueda sin efecto real"
                + (f" query='{query_text}'." if query_text else ".")
                + f" No se aplicó update al nodo "
                + f"(status={status}, state_delta_kind={state_delta_kind}, "
                + f"results_detected={results_detected})."
                + (
                    f" search_target disponible(s): {available_search_target_ids}."
                    if available_search_target_ids
                    else ""
                )
            )
            current_node.working_memory.revision_count += 1
            current_node.last_progress_step = runtime.step_count

            scope = runtime.get_active_scope()
            if scope is not None and query_text:
                scope.register_progress(f"search_with_text_noop:{query_text}")

            _log(
                f"search_with_text ignored as no-op "
                f"node_id={current_node.node_id!r} "
                f"query={query_text!r} "
                f"status={status!r} "
                f"state_delta_kind={state_delta_kind!r} "
                f"results_detected={results_detected!r} "
                f"available_search_target_ids={available_search_target_ids!r}"
            )
            return

        previous_inspection = runtime.inspection_result_by_node.get(current_node.node_id)

        resolved_url = (
            _optional_str(inspection_result.get("page_url"))
            or _optional_str(inspection_result.get("final_url"))
            or current_node.canonical_url
        )
        title = (
            _optional_str(inspection_result.get("title"))
            or _optional_str(inspection_result.get("page_title"))
            or current_node.title
        )

        create_new_node = self._search_should_create_new_node(
            current_node=current_node,
            previous_inspection=previous_inspection,
            new_inspection=inspection_result,
        )

        candidates = list(inspection_result.get("candidates") or [])

        if create_new_node:
            target_node = runtime.graph.ensure_node(
                node_id=f"node_search_{uuid4().hex[:12]}",
                canonical_url=resolved_url,
                title=title,
                is_root=False,
            )
        else:
            target_node = current_node

        target_id = target_node.node_id
        is_reused = target_id == current_node.node_id

        print(
            f"[debug.updater.search.target] target_id={target_id!r} "
            f"is_reused={is_reused} create_new_node={create_new_node} "
            f"candidate_count={len(candidates)}",
            flush=True,
        )

        runtime.inspection_result_by_node[target_id] = dict(inspection_result)
        runtime.search_result_by_node[target_id] = dict(inspection_result)
        runtime.mark_frozen_dom_snapshot(target_id)

        if query_text:
            runtime.register_search_query(target_id, query_text)

        runtime.current_node_id = target_id
        runtime.current_content_owner_node_id = target_id

        target_node.inspected = False
        runtime.navigation_perception_by_node.pop(target_id, None)
        runtime.navigation_perception_refine_state_by_node.pop(target_id, None)
        runtime.navigation_perception_merge_by_node.pop(target_id, None)
        runtime.navigation_perception_explicit_runs_by_node.pop(target_id, None)
        runtime.navigation_perception_current_node_finding_by_node.pop(target_id, None)

        # IMPORTANTE:
        # No borrar runtime.goal_validation_state_by_node[target_id].
        # Queremos preservar la memoria semántica de validación del nodo
        # para no reabrir validate_current_content sobre evidencia ya consumida.

        if runtime.last_node_view is not None and runtime.last_node_view.node_id == target_id:
            runtime.last_node_view = None

        scope = runtime.get_active_scope()

        if create_new_node or not is_reused:
            parent_arrival = None
            if scope is not None:
                parent_arrival = runtime.get_arrival(scope.current_arrival_context_id)

            arrival = ArrivalContext(
                arrival_context_id=f"arrival_{uuid4().hex[:12]}",
                node_id=target_id,
                from_node_id=current_node.node_id,
                via_edge_id=None,
                arrival_depth=(
                    (parent_arrival.arrival_depth + 1)
                    if parent_arrival is not None
                    else 1
                ),
                arrival_mode="search",
                parent_scope_id=None if scope is None else scope.scope_id,
                discovery_reason="search_with_text",
                is_reentry=target_node.visited_count > 0,
                step_index=runtime.step_count,
            )
            runtime.register_arrival(arrival)
            target_node.register_visit(arrival_context_id=arrival.arrival_context_id)

            if scope is not None:
                scope.current_node_id = target_id
                scope.current_arrival_context_id = arrival.arrival_context_id
                scope.register_node(target_id, arrival_context_id=arrival.arrival_context_id)

            if runtime.active_path is not None:
                runtime.active_path.append_step(
                    PathStep(
                        path_step_id=f"path_step_{target_id}_{runtime.step_count}",
                        node_id=target_id,
                        canonical_url=target_node.canonical_url,
                        arrival_context_id=arrival.arrival_context_id,
                        depth=arrival.arrival_depth,
                        via_edge_id=None,
                    )
                )

        msg = (
            f"[Paso {runtime.step_count}] 🔎 Búsqueda ejecutada"
            + (f" query='{query_text}'." if query_text else ".")
            + f" Se han revelado {len(candidates)} resultados. PRIORIZA navegar por los nuevos CANDIDATOS DISPONIBLES."
        )
        target_node.working_memory.local_summary = msg
        target_node.working_memory.revision_count += 1
        target_node.last_progress_step = runtime.step_count

        if scope is not None and query_text:
            scope.register_progress(f"search_with_text:{query_text}")

        _log(
            f"search_with_text processed target_id={target_id!r} "
            f"create_new_node={create_new_node} reused={is_reused} "
            f"query={query_text!r} candidates={len(candidates)}"
        )

    def _search_should_create_new_node(
        self,
        *,
        current_node: Any,
        previous_inspection: dict[str, object] | None,
        new_inspection: dict[str, object],
    ) -> bool:
        return _search_should_create_new_node_static(
            current_node=current_node,
            previous_inspection=previous_inspection,
            new_inspection=new_inspection,
        )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _optional_dict(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)

    # Si no es dict, intentamos convertirlo si parece un objeto con campos
    try:
        # Soporte básico para objetos con __dict__ o pydantic models
        if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
            return dict(getattr(value, "model_dump")())
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
    except Exception:
        pass

    return None


def _safe_perception(result: dict[str, object] | None) -> dict[str, object] | None:
    if result is None:
        return None
    local_perception = result.get("local_perception")
    return dict(local_perception) if isinstance(local_perception, dict) else None


def _resolve_content_owner_node(
    runtime: RuntimeUpdaterPort,
    fallback_node: Any,
) -> Any:
    owner_node_id = (
        getattr(runtime, "current_content_owner_node_id", None)
        or getattr(runtime, "current_node_id", None)
    )
    if owner_node_id:
        owner = runtime.graph.get_node(owner_node_id)
        if owner is not None:
            return owner
    return fallback_node

def _resolve_evidence_ref(
    inspection_result: dict[str, object] | None,
    download_result: dict[str, object] | None,
    artifact_result: dict[str, object] | None,
) -> str | None:
    if isinstance(download_result, dict):
        ref = (
            _optional_str(download_result.get("download_url"))
            or _optional_str(download_result.get("candidate_url"))
        )
        if ref:
            return ref

    if isinstance(artifact_result, dict):
        ref = (
            _optional_str(artifact_result.get("source_url"))
            or _optional_str(artifact_result.get("artifact_url"))
            or _optional_str(artifact_result.get("final_url"))
            or _optional_str(artifact_result.get("url"))
        )
        if ref:
            return ref

    if isinstance(inspection_result, dict):
        ref = (
            _optional_str(inspection_result.get("page_url"))
            or _optional_str(inspection_result.get("final_url"))
            or _optional_str(inspection_result.get("url"))
        )
        if ref:
            return ref

    return None

def _resolve_validation_local_perception(
    *,
    validation_target: object,
    inspection_result: dict[str, object] | None,
    download_result: dict[str, object] | None,
    artifact_result: dict[str, object] | None,
) -> tuple[dict[str, object] | None, str | None]:
    source_kind = _optional_str(getattr(validation_target, "source_kind", None))
    content_signature = _optional_str(getattr(validation_target, "content_signature", None))
    artifact_url = _optional_str(getattr(validation_target, "artifact_url", None))
    page_url = _optional_str(getattr(validation_target, "page_url", None))

    if source_kind == "artifact":
        return _safe_perception(artifact_result), content_signature or artifact_url

    if source_kind == "download":
        return _safe_perception(download_result), content_signature or artifact_url

    if source_kind == "inspection":
        return _safe_perception(inspection_result), content_signature or page_url

    local_perception = (
        _safe_perception(artifact_result)
        or _safe_perception(download_result)
        or _safe_perception(inspection_result)
    )
    evidence_ref_override = content_signature or artifact_url or page_url
    return local_perception, evidence_ref_override
    
def _extract_artifact_text(artifact_result: dict[str, object]) -> str | None:
    for key in _ARTIFACT_TEXT_KEYS:
        value = artifact_result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    pages = artifact_result.get("pages")
    if isinstance(pages, list):
        chunks: list[str] = []
        for page in pages[:_MAX_ARTIFACT_PAGES_TO_SCAN]:
            if isinstance(page, dict):
                text = page.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
        if chunks:
            return "\n".join(chunks)

    return None


def _inspection_signature(inspection_result: dict[str, object] | None) -> str:
    if not isinstance(inspection_result, dict):
        return ""

    page_url = (
        _optional_str(inspection_result.get("page_url"))
        or _optional_str(inspection_result.get("final_url"))
        or ""
    )
    title = _optional_str(inspection_result.get("title")) or ""
    content = (
        _optional_str(inspection_result.get("content"))
        or _optional_str(inspection_result.get("text_excerpt"))
        or ""
    )
    content_preview = content[:300]

    candidates = list(inspection_result.get("candidates") or ())
    candidate_urls: list[str] = []
    for item in candidates[:5]:
        if isinstance(item, dict):
            url = _optional_str(item.get("url"))
            if url:
                candidate_urls.append(url)

    return "|".join(
        (
            page_url,
            title,
            content_preview,
            str(len(content)),
            str(len(candidates)),
            *candidate_urls,
        )
    )


def _search_should_create_new_node_static(
    current_node: Any,
    previous_inspection: dict[str, object] | None,
    new_inspection: dict[str, object],
) -> bool:
    search_metadata = new_inspection.get("search_metadata")
    if isinstance(search_metadata, dict):
        state_delta_kind = _optional_str(search_metadata.get("state_delta_kind"))
        if state_delta_kind == "navigation":
            return True
        if state_delta_kind == "dom_mutation":
            return True

    prev_sig = _inspection_signature(previous_inspection)
    new_sig = _inspection_signature(new_inspection)

    if not prev_sig:
        return True

    prev_url = (
        _optional_str(previous_inspection.get("page_url"))
        if isinstance(previous_inspection, dict)
        else None
    )
    new_url = _optional_str(new_inspection.get("page_url")) or _optional_str(
        new_inspection.get("final_url")
    )

    if prev_url and new_url and prev_url != new_url:
        return True

    if prev_sig != new_sig:
        return True

    return False


def _log(message: str) -> None:
    print(f"{_LOG_PREFIX} {message}", flush=True)


def _log_findings(message: str) -> None:
    print(f"{_FINDINGS_PREFIX} {message}", flush=True)


def _log_goals(message: str) -> None:
    print(f"{_GOALS_PREFIX} {message}", flush=True)
def _search_result_has_real_delta(
    *,
    current_node: Any,
    inspection_result: dict[str, object],
    search_metadata: dict[str, object] | None,
) -> bool:
    """
    Decide si un search_with_text produjo cambio real de estado.

    Reglas:
    - Si el executor reporta target_not_found / failed -> NO delta real.
    - Si no hubo resultados y state_delta_kind='none' -> NO delta real.
    - Si la URL final sigue siendo la misma y no hay señal explícita de delta,
      trátalo como NO delta real.
    - Si no existe search_metadata, solo asumimos delta real si hay cambio de URL
      o hay candidatos nuevos que antes no estaban.
    """
    status = None
    state_delta_kind = None
    results_detected = None

    if isinstance(search_metadata, dict):
        status = _optional_str(search_metadata.get("status"))
        state_delta_kind = _optional_str(search_metadata.get("state_delta_kind"))
        results_detected = search_metadata.get("results_detected")

    if status in {"target_not_found", "target_missing", "failed", "no_target"}:
        return False

    if results_detected is False and state_delta_kind in {None, "none", "no_change"}:
        return False

    current_url = _optional_str(current_node.canonical_url)
    new_url = (
        _optional_str(inspection_result.get("page_url"))
        or _optional_str(inspection_result.get("final_url"))
    )

    if (
        current_url
        and new_url
        and current_url == new_url
        and state_delta_kind in {None, "none", "no_change"}
        and results_detected is not True
    ):
        # Si no hay metadatos que confirmen delta y la URL es la misma,
        # sospechamos que no hubo cambio. Pero si hay candidatos,
        # podria ser una búsqueda AJAX que inyectó resultados sin cambiar URL.
        candidates = inspection_result.get("candidates")
        if not candidates or (isinstance(candidates, (list, tuple)) and len(candidates) == 0):
            return False

    # Si no tenemos metadatos, seamos más estrictos
    if search_metadata is None:
        if current_url and new_url and current_url != new_url:
            return True
        candidates = inspection_result.get("candidates")
        if candidates and isinstance(candidates, (list, tuple)) and len(candidates) > 0:
            return True
        return False

    return True