from __future__ import annotations
#graph_mapper_agent/application/use_cases/chat_with_research.py
from datetime import datetime
from typing import Any

from graph_mapper_agent.application.evidence_extraction import (
    EvidenceArtifact,
    EvidenceExtractionRequest,
    EvidenceExtractionService,
    ExtractEvidenceUseCase,
    ValidatedEvidenceExtractionRequest,
)
from graph_mapper_agent.bootstrap.builders.llm import (
    build_llm_runtime_bundle,
)
from graph_mapper_agent.bootstrap.builders.evidence_extraction import (
    build_evidence_extraction_service,
)
from graph_mapper_agent.bootstrap.builders.ledger import (
    build_ledger_writer,
)
from graph_mapper_agent.ledger.application.query_service import (
    build_ledger_query_service,
)
from graph_mapper_agent.application.goal_validation import (
    GoalValidationPass,
    GoalValidationResult,
)
from graph_mapper_agent.application.contracts.research_answer_models import (
    ResearchAnswerSynthesisOutput,
)
from graph_mapper_agent.bootstrap.config import GraphMapperConfig
from graph_mapper_agent.bootstrap.dto import RunGraphMapperInput
from graph_mapper_agent.bootstrap.execution_config import (
    GuidedGraphMapperConfig,
)
from graph_mapper_agent.bootstrap.runner import run_graph_mapper
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeRequest,
)

from .chat_models import (
    ResearchChatEvidence,
    ResearchChatFinding,
    ResearchChatRequest,
    ResearchChatResponse,
)


def _current_date_context() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def chat_with_research(request: ResearchChatRequest) -> ResearchChatResponse:
    request.validate()
    policy = _resolved_research_policy(request)

    run_input = RunGraphMapperInput(
        request=GraphMapperConfig(
            entry_url=request.entry_url,
            goal=request.user_message,
            max_hops=request.max_hops,
            max_pages=request.max_pages,
            decision_mode=request.decision_mode,
            allow_artifact_download=bool(policy["allow_artifact_download"]),
            allow_artifact_open=request.allow_artifact_open,
            metadata=dict(request.metadata),
        ),
        execution=GuidedGraphMapperConfig(
            jurisdiction_code=request.source_namespace,
            document_key=_document_key_for_request(request),
            timeout_seconds=request.timeout_seconds,
            target_kind="research_session",
            target_id=request.resource_key or request.run_id,
            workflow_name=request.workflow_name,
            run_id=request.run_id,
            execution_metadata={
                "interface_kind": "chat_research",
                "research_mode": request.research_mode,
                "artifact_persistence_mode": str(policy["artifact_persistence_mode"]),
                "session_id": request.session_id,
                "user_message": request.user_message,
                **dict(request.execution_metadata),
            },
            llm_runtime=request.llm_runtime,
            navigation_perception_llm_runtime=request.navigation_perception_llm_runtime,
            goal_validation_llm_runtime=request.goal_validation_llm_runtime,
            evidence_extraction_visual_llm_runtime=request.evidence_extraction_visual_llm_runtime,
            evidence_extraction_ocr_llm_runtime=request.evidence_extraction_ocr_llm_runtime,
            ledger_database_url=request.ledger_database_url,
        ),
    )

    result = run_graph_mapper(run_input)
    summary = _summarize_result(
        result.final_state,
        final_status=result.final_status,
        user_message=request.user_message,
        run_id=request.run_id,
        ledger_database_url=request.ledger_database_url,
        llm_runtime_config=request.llm_runtime,
        ocr_runtime_config=request.evidence_extraction_ocr_llm_runtime,
    )
    answer = _synthesize_answer(summary=summary, request=request)

    return ResearchChatResponse(
        session_id=_resolved_session_id(request),
        run_id=request.run_id,
        final_status=result.final_status,
        answer=answer,
        summary=summary["summary_text"],
        current_node_id=summary["current_node_id"],
        current_url=summary["current_url"],
        total_nodes=summary["total_nodes"],
        total_edges=summary["total_edges"],
        findings=summary["findings"],
        extracted_evidence=summary["extracted_evidence"],
        final_state=result.final_state,
    )


def _resolved_session_id(request: ResearchChatRequest) -> str:
    value = _optional_str(request.session_id)
    if value:
        return value
    return f"session-{request.run_id}"


def _document_key_for_request(request: ResearchChatRequest) -> str:
    raw = (request.resource_key or request.run_id or "").strip()
    if raw:
        return raw
    return "research-session"


def _resolved_research_policy(request: ResearchChatRequest) -> dict[str, object]:
    mode = str(request.research_mode or "collect_artifacts").strip().lower()
    if mode == "read_only":
        return {
            "allow_artifact_download": False,
            "artifact_persistence_mode": "never",
        }
    if mode == "mixed":
        return {
            "allow_artifact_download": bool(request.allow_artifact_download),
            "artifact_persistence_mode": "manual",
        }
    return {
        "allow_artifact_download": bool(request.allow_artifact_download),
        "artifact_persistence_mode": "on_validation",
    }


def _summarize_result(
    final_state: dict[str, object],
    *,
    final_status: str | None,
    user_message: str,
    run_id: str,
    ledger_database_url: str | None,
    llm_runtime_config=None,
    ocr_runtime_config=None,
) -> dict[str, Any]:
    runtime = final_state.get("runtime")
    current_node_id = _optional_str(getattr(runtime, "current_node_id", None))
    graph = getattr(runtime, "graph", None)

    total_nodes = len(getattr(graph, "nodes_by_id", {}) or {})
    total_edges = len(getattr(graph, "edges_by_id", {}) or {})

    current_url = None
    if current_node_id and graph is not None:
        get_node = getattr(graph, "get_node", None)
        if callable(get_node):
            current_node = get_node(current_node_id)
            current_url = _optional_str(getattr(current_node, "canonical_url", None))

    findings = _summarize_findings(getattr(runtime, "findings", {}) or {})
    extracted_evidence = _extract_validated_evidence(
        runtime,
        run_id=run_id,
        ledger_database_url=ledger_database_url,
        llm_runtime_config=llm_runtime_config,
        ocr_runtime_config=ocr_runtime_config,
    )
    findings_text = _findings_text(findings)
    evidence_text = _evidence_text(extracted_evidence)
    goal_progress = _goal_progress(getattr(runtime, "goal_trace", None))
    goal_progress_text = goal_progress["text"] if goal_progress is not None else None

    status_text = _optional_str(final_status) or "unknown"
    parts = [
        f"Run finished with status `{status_text}`.",
        f"Investigated Goal: {user_message.strip()}",
        f"Explored graph: {total_nodes} nodes and {total_edges} edges.",
    ]
    if current_url:
        parts.append(f"Last active node: {current_url}")
    if goal_progress_text:
        parts.append(goal_progress_text)
    if findings_text:
        parts.append(findings_text)
    if evidence_text:
        parts.append(evidence_text)

    return {
        "summary_text": " ".join(part for part in parts if part),
        "current_node_id": current_node_id,
        "current_url": current_url,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "findings": findings,
        "extracted_evidence": extracted_evidence,
        "goal_progress": goal_progress,
    }


def _summarize_findings(
    findings_by_id: dict[str, object],
) -> tuple[ResearchChatFinding, ...]:
    items: list[ResearchChatFinding] = []
    for finding in findings_by_id.values():
        label = _optional_str(getattr(finding, "label", None))
        value = _optional_str(getattr(finding, "value", None))
        if not label and not value:
            continue
        evidence = getattr(finding, "evidence", ()) or ()
        first_evidence = evidence[0] if evidence else None
        items.append(
            ResearchChatFinding(
                label=label or value or "finding",
                value=value or label or "",
                confidence=_optional_float(getattr(finding, "confidence", None)),
                source_url=_optional_str(getattr(first_evidence, "source_url", None)),
                snippet=_optional_str(getattr(first_evidence, "snippet", None)),
            )
        )
    items.sort(
        key=lambda item: (
            -(item.confidence if item.confidence is not None else -1.0),
            item.label,
        )
    )
    return tuple(items[:5])


def _findings_text(findings: tuple[ResearchChatFinding, ...]) -> str | None:
    if not findings:
        return None
    parts = []
    for item in findings[:3]:
        chunk = item.label
        if item.value and item.value != item.label:
            chunk = f"{chunk}: {item.value}"
        parts.append(chunk)
    return "Key Findings: " + "; ".join(parts) + "."


def _goal_progress(goal_trace: object | None) -> dict[str, object] | None:
    if goal_trace is None:
        return None
    active = getattr(goal_trace, "active_proposal", None)
    proposal = active() if callable(active) else None
    if proposal is None:
        return None
    conditions = tuple(getattr(proposal, "conditions", ()) or ())
    if not conditions:
        return None
    satisfied = 0
    pending = 0
    for condition in conditions:
        status = _optional_str(getattr(condition, "status", None)) or "pending"
        if status == "satisfied":
            satisfied += 1
        elif status == "pending":
            pending += 1
    return {
        "satisfied": satisfied,
        "pending": pending,
        "total": len(conditions),
        "text": (
            f"Goal progress: {satisfied}/{len(conditions)} satisfied, "
            f"{pending} pending."
        ),
    }


def _build_answer(summary: dict[str, Any]) -> str:
    findings = summary["findings"]
    extracted_evidence = summary["extracted_evidence"]
    sections: list[str] = [summary["summary_text"]]
    if findings:
        bullet_lines = []
        for item in findings[:3]:
            line = f"- {item.label}"
            if item.value and item.value != item.label:
                line += f": {item.value}"
            if item.source_url:
                line += f" ({item.source_url})"
            bullet_lines.append(line)
        sections.append("Highlighted Evidence:\n" + "\n".join(bullet_lines))
    if extracted_evidence:
        evidence_lines = []
        for item in extracted_evidence[:3]:
            snippet = _optional_str(item.text_excerpt) or ""
            line = f"- {snippet}"
            if item.source_url:
                line += f" ({item.source_url})"
            evidence_lines.append(line)
        sections.append("Extracted content:\n" + "\n".join(evidence_lines))
    return "\n\n".join(section for section in sections if section)


def _synthesize_answer(
    *,
    summary: dict[str, Any],
    request: ResearchChatRequest,
) -> str:
    if request.llm_runtime is None:
        return _build_answer(summary)

    ledger = build_ledger_writer(request.ledger_database_url)
    bundle = build_llm_runtime_bundle(
        llm_runtime_config=request.llm_runtime,
        expected_output_name="graph_mapper_research_answer_synthesis",
        ledger=ledger,
        label_prefix="research_answer_synthesis",
    )
    if bundle is None:
        return _build_answer(summary)

    synthesis_input = _answer_synthesis_payload(summary, request)
    synthesis_user_content = _answer_synthesis_user_content_from_payload(synthesis_input)
    _record_answer_synthesis_input(
        ledger=ledger,
        run_id=request.run_id,
        summary=summary,
        payload=synthesis_input,
    )

    try:
        response = _invoke_runtime(
            bundle.runtime,
            LlmRuntimeRequest(
                operation_name="graph_mapper_research_answer_synthesis",
                expected_output_name="graph_mapper_research_answer_synthesis",
                messages=[
                    {"role": "system", "content": _answer_synthesis_system_prompt()},
                    {
                        "role": "user",
                        "content": synthesis_user_content,
                    },
                ],
                metadata={
                    "prompt_version": "research_answer_synthesis_v1",
                    "structured_output_name": "graph_mapper_research_answer_synthesis",
                },
            ),
        )
        payload = _extract_llm_json_payload(response)
        parsed = ResearchAnswerSynthesisOutput.model_validate(payload)
        _record_answer_synthesis_output(
            ledger=ledger,
            run_id=request.run_id,
            payload=payload,
        )
        answer = _optional_str(parsed.final_answer)
        follow_up = _optional_str(parsed.follow_up_recommendation)
        if not answer:
            return _build_answer(summary)
        if follow_up and parsed.status == "needs_more_research":
            return f"{answer}\n\nSuggested follow-up: {follow_up}"
        return answer
    except Exception:
        return _build_answer(summary)


def _extract_validated_evidence(
    runtime: object | None,
    *,
    run_id: str,
    ledger_database_url: str | None,
    llm_runtime_config=None,
    ocr_runtime_config=None,
) -> tuple[ResearchChatEvidence, ...]:
    if runtime is None:
        return ()

    payloads = getattr(runtime, "document_validation_payload_by_node", {}) or {}
    download_by_node = getattr(runtime, "download_result_by_node", {}) or {}
    artifact_by_node = getattr(runtime, "artifact_result_by_node", {}) or {}
    inspection_by_node = getattr(runtime, "inspection_result_by_node", {}) or {}

    ledger = build_ledger_writer(ledger_database_url)
    coverage_runtime = None
    if llm_runtime_config is not None:
        bundle = build_llm_runtime_bundle(
            llm_runtime_config=llm_runtime_config,
            expected_output_name="graph_mapper_evidence_coverage",
            ledger=ledger,
            label_prefix="evidence_coverage",
        )
        if bundle is not None:
            coverage_runtime = bundle.runtime
    extraction_service: EvidenceExtractionService = build_evidence_extraction_service(
        ocr_runtime_config=ocr_runtime_config,
        coverage_runtime=coverage_runtime,
    )
    extraction_use_case = ExtractEvidenceUseCase(service=extraction_service)
    items: list[ResearchChatEvidence] = []

    for node_id, payload in payloads.items():
        if not isinstance(payload, dict):
            continue
        metadata = payload.get("metadata")
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        if str(metadata_dict.get("validation_status") or "").strip() != "validated":
            continue
        goal_validation_result = _goal_validation_result_from_payload(payload)
        if goal_validation_result is None:
            continue

        artifact = _artifact_for_node(
            node_id=node_id,
            download_by_node=download_by_node,
            artifact_by_node=artifact_by_node,
            inspection_by_node=inspection_by_node,
        )
        if artifact is None:
            continue

        try:
            result = extraction_use_case.execute(
                ValidatedEvidenceExtractionRequest(
                    extraction_request=EvidenceExtractionRequest(
                        artifact=artifact,
                        max_pages=2,
                        include_text=True,
                        include_rendered_pages=False,
                        metadata={
                            "node_id": node_id,
                            "source": "chat_with_research",
                            "ocr_mode": _resolve_ocr_mode_from_request(request),
                        },
                    ),
                    goal_validation_result=goal_validation_result,
                )
            )
        except Exception:
            continue

        for item in result.items:
            text = _optional_str(item.text)
            if not text:
                continue
            _record_extracted_evidence(
                ledger=ledger,
                run_id=run_id,
                artifact=artifact,
                node_id=node_id,
                result=result,
                item=item,
            )
            items.append(
                ResearchChatEvidence(
                    source_url=artifact.source_url,
                    carrier=result.carrier,
                    text_excerpt=text[:500],
                    page_number=item.page_number,
                    mime_type=item.mime_type,
                )
            )
            if len(items) >= 5:
                return tuple(items)

    return tuple(items)


def _record_extracted_evidence(
    *,
    ledger: object | None,
    run_id: str,
    artifact: EvidenceArtifact,
    node_id: str,
    result,
    item,
) -> None:
    if ledger is None or not run_id.strip():
        return
    recorder = getattr(ledger, "record_evidence", None)
    if not callable(recorder):
        return

    result_metadata = getattr(result, "metadata", {}) or {}
    item_metadata = getattr(item, "metadata", {}) or {}
    source = _optional_str(result_metadata.get("source")) or "unknown"
    recorder(
        run_id=run_id,
        evidence_kind="evidence_extraction_result",
        source_kind=f"extracted_{getattr(result, 'carrier', 'unknown')}",
        source_url=artifact.source_url,
        local_path=artifact.local_path,
        mime_type=_optional_str(getattr(item, "mime_type", None))
        or artifact.media_type
        or artifact.screenshot_mime_type,
        title=artifact.filename,
        content={
            "carrier": getattr(result, "carrier", None),
            "evidence_kind": getattr(item, "evidence_kind", None),
            "page_number": getattr(item, "page_number", None),
            "text_excerpt": (_optional_str(getattr(item, "text", None)) or "")[:4000],
            "metadata": dict(item_metadata),
        },
        metadata={
            "node_id": node_id,
            "extraction_backend": source,
            "visual_strategy": result_metadata.get("visual_strategy"),
            "result_metadata": dict(result_metadata),
        },
    )


def _artifact_for_node(
    *,
    node_id: str,
    download_by_node: dict[str, object],
    artifact_by_node: dict[str, object],
    inspection_by_node: dict[str, object],
) -> EvidenceArtifact | None:
    download = download_by_node.get(node_id)
    if isinstance(download, dict):
        local_path = _optional_str(download.get("original_path"))
        source_url = _optional_str(download.get("download_url"))
        media_type = _optional_str(download.get("content_type"))
        filename = _optional_str(download.get("filename"))
        if local_path or source_url:
            return EvidenceArtifact(
                local_path=local_path,
                source_url=source_url,
                media_type=media_type,
                filename=filename,
            )

    artifact = artifact_by_node.get(node_id)
    if isinstance(artifact, dict):
        content = _optional_str(artifact.get("content")) or _optional_str(
            artifact.get("text_excerpt")
        )
        if content:
            return EvidenceArtifact(
                inline_text=content,
            )

    inspection = inspection_by_node.get(node_id)
    if isinstance(inspection, dict):
        content = _optional_str(inspection.get("content")) or _optional_str(
            inspection.get("text_excerpt")
        )
        source_url = _optional_str(inspection.get("page_url"))
        if content:
            return EvidenceArtifact(
                source_url=source_url,
                inline_text=content,
                screenshot_base64=_optional_str(inspection.get("screenshot_base64")),
                screenshot_mime_type=_optional_str(
                    inspection.get("screenshot_mime_type")
                ),
            )

    return None


def _goal_validation_result_from_payload(
    payload: dict[str, object],
) -> GoalValidationResult | None:
    goal_validation = payload.get("goal_validation")
    if not isinstance(goal_validation, dict):
        return None
    final_result = goal_validation.get("final_result")
    if not isinstance(final_result, dict):
        return None
    validation_pass = final_result.get("validation_pass")
    if not isinstance(validation_pass, dict):
        return None

    status = _optional_str(final_result.get("status"))
    strategy = _optional_str(validation_pass.get("strategy"))
    reason = _optional_str(validation_pass.get("reason"))
    if not status or not strategy or not reason:
        return None

    page_numbers_raw = validation_pass.get("page_numbers")
    page_numbers = ()
    if isinstance(page_numbers_raw, list):
        page_numbers = tuple(
            int(item) for item in page_numbers_raw if isinstance(item, int)
        )

    pattern_hints_raw = validation_pass.get("pattern_hints")
    pattern_hints = ()
    if isinstance(pattern_hints_raw, list):
        pattern_hints = tuple(
            str(item).strip()
            for item in pattern_hints_raw
            if isinstance(item, str) and str(item).strip()
        )

    metadata = final_result.get("metadata")
    metadata_dict = metadata if isinstance(metadata, dict) else {}

    return GoalValidationResult(
        status=status,
        validation_pass=GoalValidationPass(
            level=int(validation_pass.get("level") or 0),
            strategy=strategy,
            reason=reason,
            page_numbers=page_numbers,
            pattern_hints=pattern_hints,
        ),
        rationale=_optional_str(final_result.get("rationale")) or "",
        evidence_summary=_optional_str(final_result.get("evidence_summary")) or "",
        pages_consumed=int(final_result.get("pages_consumed") or 0),
        recommended_next_strategy=_optional_str(
            final_result.get("recommended_next_strategy")
        ),
        metadata=dict(metadata_dict),
    )


def _evidence_text(evidence: tuple[ResearchChatEvidence, ...]) -> str | None:
    if not evidence:
        return None
    snippets = []
    for item in evidence[:2]:
        excerpt = _optional_str(item.text_excerpt)
        if excerpt:
            snippets.append(excerpt[:140])
    if not snippets:
        return None
    return "Validated extracted content: " + " | ".join(snippets) + "."


def _answer_synthesis_system_prompt() -> str:
    return (
        "You are the final synthesizer for a deep research agent.\n"
        f"Current system date: {_current_date_context()}.\n"
        "You will receive the user goal, the final run status, goal progress, findings, extracted evidence, links, recent conversation history, and the run operational context.\n"
        "You must decide if there is sufficient basis to answer or if further research is still needed.\n"
        "If the evidence is sufficient, respond with status=ready and a clear, direct, and useful final answer.\n"
        "If important conditions are still missing, respond with status=needs_more_research and briefly explain what is missing.\n"
        "Do not return a technical log or a mechanical list of runtime metrics, unless it helps the answer.\n"
        "Use sources/evidence concretely, and when useful mention key links or documents seen during the run.\n"
        "If the payload includes source_journey, use it to explain by source what was visited, downloaded, validated, or extracted.\n"
        "If the payload contains downloaded documents or opened artifacts, you can explicitly mention them as part of the research journey.\n"
        "If there are gaps, state them clearly and connect the suggested follow-up step with what has already been visited or downloaded.\n"
        "Respond ONLY with valid JSON following the expected schema."
    )


def _answer_synthesis_user_content(
    summary: dict[str, Any],
    request: ResearchChatRequest,
) -> str:
    return _answer_synthesis_user_content_from_payload(
        _answer_synthesis_payload(summary, request)
    )


def _answer_synthesis_payload(
    summary: dict[str, Any],
    request: ResearchChatRequest,
) -> dict[str, object]:
    findings = [
        {
            "label": item.label,
            "value": item.value,
            "confidence": item.confidence,
            "source_url": item.source_url,
            "snippet": item.snippet,
        }
        for item in summary["findings"]
    ]
    evidence = [
        {
            "source_url": item.source_url,
            "carrier": item.carrier,
            "text_excerpt": item.text_excerpt,
            "page_number": item.page_number,
            "mime_type": item.mime_type,
        }
        for item in summary["extracted_evidence"]
    ]
    operational_context = _answer_synthesis_operational_context(
        run_id=request.run_id,
        session_id=_resolved_session_id(request),
        ledger_database_url=request.ledger_database_url,
    )
    return {
        "current_date": _current_date_context(),
        "user_goal": request.user_message,
        "entry_url": request.entry_url,
        "research_mode": request.research_mode,
        "run_summary": summary["summary_text"],
        "current_url": summary["current_url"],
        "graph": {
            "total_nodes": summary["total_nodes"],
            "total_edges": summary["total_edges"],
        },
        "goal_progress": summary.get("goal_progress"),
        "findings": findings,
        "extracted_evidence": evidence,
        "operational_context": operational_context,
    }


def _answer_synthesis_operational_context(
    *,
    run_id: str,
    session_id: str,
    ledger_database_url: str | None,
) -> dict[str, object]:
    try:
        query = build_ledger_query_service(ledger_database_url)
        run_data = query.get_run(run_id) or {}
        session_data = query.get_session(session_id) or {}
    except Exception:
        return {}

    evidence = run_data.get("evidence_records")
    evidence_items = evidence if isinstance(evidence, list) else []
    steps = run_data.get("steps")
    llm_calls = run_data.get("llm_calls")
    messages = session_data.get("messages")

    downloads = [
        _artifact_link_payload(item)
        for item in evidence_items
        if str(item.get("evidence_kind") or "") == "download_result"
    ]
    opened = [
        _artifact_link_payload(item)
        for item in evidence_items
        if str(item.get("evidence_kind") or "") == "artifact_result"
    ]
    validations = [
        _validation_payload(item)
        for item in evidence_items
        if str(item.get("evidence_kind") or "") == "goal_validation_result"
    ]
    visited_links = _visited_links_from_evidence(evidence_items)
    recent_messages = [
        _session_message_payload(item)
        for item in (messages if isinstance(messages, list) else [])[-8:]
    ]

    return {
        "run_status": run_data.get("status"),
        "steps_count": len(steps) if isinstance(steps, list) else 0,
        "llm_calls_count": len(llm_calls) if isinstance(llm_calls, list) else 0,
        "visited_links": visited_links[:12],
        "downloaded_documents": downloads[:8],
        "opened_artifacts": opened[:8],
        "validation_events": validations[-6:],
        "source_journey": _source_journey_from_evidence(evidence_items)[:12],
        "recent_conversation": [item for item in recent_messages if item],
    }


def _artifact_link_payload(item: dict[str, Any]) -> dict[str, object]:
    content = item.get("content_json")
    content_dict = content if isinstance(content, dict) else {}
    source_url = _optional_str(
        item.get("source_url")
        or content_dict.get("download_url")
        or content_dict.get("final_url")
    )
    local_path = _optional_str(
        item.get("local_path")
        or content_dict.get("local_path")
        or content_dict.get("original_path")
    )
    return {
        "title": _optional_str(
            item.get("title")
            or content_dict.get("artifact_kind")
            or content_dict.get("filename")
        ),
        "source_url": source_url,
        "local_path": local_path,
        "open_local_url": f"/api/artifacts/open?path={local_path}" if local_path else None,
    }


def _validation_payload(item: dict[str, Any]) -> dict[str, object]:
    content = item.get("content_json")
    content_dict = content if isinstance(content, dict) else {}
    matched_ids = content_dict.get("matched_condition_ids")
    return {
        "status": _optional_str(
            content_dict.get("status") or content_dict.get("validation_status")
        ),
        "matched_condition_ids": matched_ids if isinstance(matched_ids, list) else [],
        "recommended_next_step": _optional_str(content_dict.get("recommended_next_step")),
        "source_url": _optional_str(item.get("source_url")),
    }


def _visited_links_from_evidence(items: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for item in items:
        content = item.get("content_json")
        content_dict = content if isinstance(content, dict) else {}
        candidates = (
            _optional_str(item.get("source_url")),
            _optional_str(content_dict.get("page_url")),
            _optional_str(content_dict.get("download_url")),
            _optional_str(content_dict.get("final_url")),
        )
        for url in candidates:
            if not url or url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls


def _source_journey_from_evidence(items: list[dict[str, Any]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    ordered_urls: list[str] = []
    for item in items:
        source_url = _evidence_primary_url(item)
        if not source_url:
            continue
        if source_url not in grouped:
            grouped[source_url] = {
                "source_url": source_url,
                "title": _evidence_title_for_summary(item),
                "actions": [],
                "learned": [],
                "local_path": None,
                "open_local_url": None,
            }
            ordered_urls.append(source_url)
        entry = grouped[source_url]
        local_path = _evidence_local_path(item)
        if local_path and not entry.get("local_path"):
            entry["local_path"] = local_path
            entry["open_local_url"] = f"/api/artifacts/open?path={local_path}"
        action = _evidence_action_summary(item)
        if action and action not in entry["actions"]:
            entry["actions"].append(action)
        learned = _evidence_learning_summary(item)
        if learned and learned not in entry["learned"]:
            entry["learned"].append(learned)
    return [grouped[url] for url in ordered_urls]


def _evidence_primary_url(item: dict[str, Any]) -> str | None:
    content = item.get("content_json")
    content_dict = content if isinstance(content, dict) else {}
    return _optional_str(
        item.get("source_url")
        or content_dict.get("page_url")
        or content_dict.get("download_url")
        or content_dict.get("final_url")
    )


def _evidence_local_path(item: dict[str, Any]) -> str | None:
    content = item.get("content_json")
    content_dict = content if isinstance(content, dict) else {}
    return _optional_str(
        item.get("local_path")
        or content_dict.get("local_path")
        or content_dict.get("original_path")
    )


def _evidence_title_for_summary(item: dict[str, Any]) -> str | None:
    content = item.get("content_json")
    content_dict = content if isinstance(content, dict) else {}
    return _optional_str(
        item.get("title")
        or content_dict.get("title")
        or content_dict.get("artifact_kind")
        or content_dict.get("filename")
    )


def _evidence_action_summary(item: dict[str, Any]) -> str | None:
    kind = str(item.get("evidence_kind") or "").strip()
    content = item.get("content_json")
    content_dict = content if isinstance(content, dict) else {}
    if kind == "download_result":
        return "Document was downloaded."
    if kind == "artifact_result":
        return "Artifact/document was opened."
    if kind == "inspection_result":
        return "Page was inspected."
    if kind == "goal_validation_result":
        status = _optional_str(content_dict.get("status") or content_dict.get("validation_status"))
        if status:
            return f"Evidence evaluated with result {status}."
        return "Validation performed on evidence."
    if kind == "evidence_extraction_result":
        return "Useful content was extracted."
    return None


def _evidence_learning_summary(item: dict[str, Any]) -> str | None:
    kind = str(item.get("evidence_kind") or "").strip()
    content = item.get("content_json")
    content_dict = content if isinstance(content, dict) else {}
    if kind == "inspection_result":
        local_perception = content_dict.get("local_perception")
        local_perception_dict = (
            local_perception if isinstance(local_perception, dict) else {}
        )
        return _trim_summary_text(
            _optional_str(
                local_perception_dict.get("summary") or content_dict.get("summary")
            ),
            260,
        )
    if kind == "goal_validation_result":
        summary = _optional_str(
            content_dict.get("summary")
            or content_dict.get("validation_scope_assessment")
            or content_dict.get("rationale")
        )
        matched_ids = content_dict.get("matched_condition_ids")
        if summary and isinstance(matched_ids, list) and matched_ids:
            return _trim_summary_text(
                f"{summary} Conditions: {', '.join(str(item) for item in matched_ids)}.",
                260,
            )
        return _trim_summary_text(summary, 260)
    if kind == "evidence_extraction_result":
        return _trim_summary_text(
            _optional_str(
                content_dict.get("text_excerpt")
                or content_dict.get("summary")
                or content_dict.get("inline_text")
            ),
            260,
        )
    if kind == "artifact_result":
        return _trim_summary_text(
            _optional_str(content_dict.get("text_excerpt") or content_dict.get("content")),
            260,
        )
    return None


def _trim_summary_text(value: str | None, limit: int) -> str | None:
    text = _optional_str(value)
    if not text:
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _session_message_payload(item: dict[str, Any]) -> dict[str, str] | None:
    role = _optional_str(item.get("role"))
    content = item.get("content_json")
    text: str | None = None
    if isinstance(content, dict):
        text = _optional_str(
            content.get("content")
            or content.get("text")
            or content.get("message")
            or content.get("assistant_reply")
            or content.get("user_message")
        )
    elif isinstance(content, str):
        text = _optional_str(content)
    if not role and not text:
        return None
    return {
        "role": role or "unknown",
        "text": (text or "")[:400],
    }


def _answer_synthesis_user_content_from_payload(
    payload: dict[str, object],
) -> str:
    import json

    return json.dumps(payload, ensure_ascii=True, indent=2)


def _record_answer_synthesis_input(
    *,
    ledger: object | None,
    run_id: str,
    summary: dict[str, Any],
    payload: dict[str, object],
) -> None:
    if ledger is None or not run_id.strip():
        return
    recorder = getattr(ledger, "record_evidence", None)
    if not callable(recorder):
        return
    recorder(
        run_id=run_id,
        evidence_kind="research_answer_synthesis_input",
        source_kind="final_answer_synthesis",
        source_url=summary.get("current_url"),
        title="Payload sent to final synthesis",
        content=payload,
        metadata={
            "prompt_version": "research_answer_synthesis_v1",
            "source": "chat_with_research",
        },
    )


def _record_answer_synthesis_output(
    *,
    ledger: object | None,
    run_id: str,
    payload: dict[str, object],
) -> None:
    if ledger is None or not run_id.strip():
        return
    recorder = getattr(ledger, "record_evidence", None)
    if not callable(recorder):
        return
    recorder(
        run_id=run_id,
        evidence_kind="research_answer_synthesis_output",
        source_kind="final_answer_synthesis",
        title="Structured output from final synthesis",
        content=payload,
        metadata={
            "source": "chat_with_research",
        },
    )


def _invoke_runtime(runtime: object, llm_request: LlmRuntimeRequest):
    for method_name in ("invoke", "execute", "run", "complete", "generate", "call"):
        method = getattr(runtime, method_name, None)
        if callable(method):
            return method(llm_request)
    raise AttributeError(
        f"The runtime {type(runtime).__name__} does not expose a known method "
        "to execute LlmRuntimeRequest"
    )


def _extract_llm_json_payload(llm_response: Any) -> dict[str, object]:
    response_payload = getattr(getattr(llm_response, "interaction", None), "response", None)
    if not isinstance(response_payload, dict):
        raise TypeError("LlmRuntimeResponse.interaction.response must be dict[str, object]")
    for key in (
        "parsed_response",
        "output",
        "parsed_output",
        "structured_output",
        "json_output",
        "content",
        "text",
        "response_text",
        "completion",
    ):
        payload = _coerce_to_dict(response_payload.get(key))
        if payload is not None:
            return payload
    message = response_payload.get("message")
    if isinstance(message, dict):
        payload = _coerce_to_dict(message.get("content"))
        if payload is not None:
            return payload
    raw_response = getattr(llm_response, "raw_response", None)
    if isinstance(raw_response, dict):
        for key in ("output", "parsed_response"):
            payload = _coerce_to_dict(raw_response.get(key))
            if payload is not None:
                return payload
    raise TypeError("Could not extract payload from research answer synthesis")


def _coerce_to_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            import json

            parsed = json.loads(value)
        except Exception:
            return None
        return dict(parsed) if isinstance(parsed, dict) else None
    return None


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _resolve_ocr_mode_from_request(request: ResearchChatRequest) -> str:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    value = str(
        metadata.get("ocr_mode")
        or metadata.get("ollama_ocr_mode")
        or "text"
    ).strip().lower()
    if value in {"table", "table_recognition", "table recognition"}:
        return "table"
    if value in {"figure", "figure_recognition", "figure recognition"}:
        return "figure"
    return "text"


def _optional_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
