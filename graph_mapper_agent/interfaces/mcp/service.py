from __future__ import annotations

from typing import Any, Mapping

from graph_mapper_agent.bootstrap.runner import (
    run_graph_mapper_from_json_dict,
)
from graph_mapper_agent.interfaces.chat import (
    ChatTurnRequest,
    process_chat_turn,
)
from graph_mapper_agent.ledger.application.query_service import (
    build_ledger_query_service,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)

from .models import McpAgentError, McpAgentRequest, McpAgentResponse


def invoke_mcp_method(request: McpAgentRequest) -> McpAgentResponse:
    try:
        if request.method_name == "process_chat_turn":
            return _invoke_process_chat_turn(request)
        if request.method_name == "run_graph_mapper":
            return _invoke_run_graph_mapper(request)
        if request.method_name == "get_run":
            return _invoke_get_run(request)
        if request.method_name == "get_session":
            return _invoke_get_session(request)
        if request.method_name == "get_evidence":
            return _invoke_get_evidence(request)
        raise McpAgentError(
            error_class="UnknownMethod",
            message=f"Metodo MCP no soportado: {request.method_name}",
            retryable=False,
            metadata={
                "supported_methods": [
                    "process_chat_turn",
                    "run_graph_mapper",
                    "get_run",
                    "get_session",
                    "get_evidence",
                ]
            },
        )
    except McpAgentError:
        raise
    except Exception as exc:
        raise McpAgentError(
            error_class=type(exc).__name__,
            message=str(exc) or repr(exc),
            retryable=False,
            metadata={"method_name": request.method_name},
        ) from exc


def _invoke_process_chat_turn(request: McpAgentRequest) -> McpAgentResponse:
    payload = dict(request.input_data or {})
    chat_request = ChatTurnRequest(
        user_message=str(payload.get("user_message") or "").strip(),
        entry_url=str(payload.get("entry_url") or "").strip(),
        session_id=_optional_str(payload.get("session_id")),
        run_id=_optional_str(payload.get("run_id")) or _new_chat_run_id(),
        research_mode=str(payload.get("research_mode") or "collect_artifacts").strip(),
        decision_mode=str(payload.get("decision_mode") or "llm").strip(),
        max_hops=int(payload.get("max_hops") or 250),
        max_pages=int(payload.get("max_pages") or 500),
        timeout_seconds=int(payload.get("timeout_seconds") or 200),
        allow_artifact_download=bool(payload.get("allow_artifact_download", True)),
        allow_artifact_open=bool(payload.get("allow_artifact_open", True)),
        source_namespace=str(payload.get("source_namespace") or "generic").strip(),
        resource_key=_optional_str(payload.get("resource_key")),
        metadata=dict(payload.get("metadata") or {}),
        execution_metadata=dict(payload.get("execution_metadata") or {}),
        llm_runtime=_llm_runtime_from_payload(payload.get("llm_runtime")),
        navigation_perception_llm_runtime=_llm_runtime_from_payload(
            payload.get("navigation_perception_llm_runtime")
        ),
        goal_validation_llm_runtime=_llm_runtime_from_payload(
            payload.get("goal_validation_llm_runtime")
        ),
        evidence_extraction_visual_llm_runtime=_llm_runtime_from_payload(
            payload.get("evidence_extraction_visual_llm_runtime")
        ),
        evidence_extraction_ocr_llm_runtime=_llm_runtime_from_payload(
            payload.get("evidence_extraction_ocr_llm_runtime")
        ),
        ledger_database_url=_optional_str(payload.get("ledger_database_url")),
    )
    response = process_chat_turn(chat_request)
    output_data = {
        "session_id": response.session_id,
        "user_message_id": response.user_message_id,
        "assistant_message_id": response.assistant_message_id,
        "run_id": response.research_response.run_id,
        "final_status": response.research_response.final_status,
        "answer": response.research_response.answer,
        "summary": response.research_response.summary,
        "current_node_id": response.research_response.current_node_id,
        "current_url": response.research_response.current_url,
        "total_nodes": response.research_response.total_nodes,
        "total_edges": response.research_response.total_edges,
        "findings": [
            {
                "label": item.label,
                "value": item.value,
                "confidence": item.confidence,
                "source_url": item.source_url,
                "snippet": item.snippet,
            }
            for item in response.research_response.findings
        ],
    }
    return McpAgentResponse(
        output_data=output_data,
        raw_response={
            "session_id": response.session_id,
            "research_response": _research_response_to_dict(response.research_response),
        },
    )


def _invoke_run_graph_mapper(request: McpAgentRequest) -> McpAgentResponse:
    result = run_graph_mapper_from_json_dict(request.input_data)
    output_data = {
        "final_status": result.final_status,
        "final_state": result.final_state,
    }
    return McpAgentResponse(output_data=output_data, raw_response=output_data)


def _invoke_get_run(request: McpAgentRequest) -> McpAgentResponse:
    payload = dict(request.input_data or {})
    run_id = _required_str(payload.get("run_id"), "run_id")
    query = build_ledger_query_service(_optional_str(payload.get("ledger_database_url")))
    run_data = query.get_run(run_id)
    if run_data is None:
        raise McpAgentError(
            error_class="RunNotFound",
            message=f"No existe run_id={run_id}",
            retryable=False,
        )
    return McpAgentResponse(output_data=run_data, raw_response=run_data)


def _invoke_get_session(request: McpAgentRequest) -> McpAgentResponse:
    payload = dict(request.input_data or {})
    session_id = _required_str(payload.get("session_id"), "session_id")
    query = build_ledger_query_service(_optional_str(payload.get("ledger_database_url")))
    session_data = query.get_session(session_id)
    if session_data is None:
        raise McpAgentError(
            error_class="SessionNotFound",
            message=f"No existe session_id={session_id}",
            retryable=False,
        )
    return McpAgentResponse(output_data=session_data, raw_response=session_data)


def _invoke_get_evidence(request: McpAgentRequest) -> McpAgentResponse:
    payload = dict(request.input_data or {})
    query = build_ledger_query_service(_optional_str(payload.get("ledger_database_url")))
    evidence = query.get_evidence(
        run_id=_optional_str(payload.get("run_id")),
        session_id=_optional_str(payload.get("session_id")),
        evidence_kind=_optional_str(payload.get("evidence_kind")),
        limit=int(payload.get("limit") or 100),
    )
    output = {"items": evidence, "count": len(evidence)}
    return McpAgentResponse(output_data=output, raw_response=output)


def _research_response_to_dict(response) -> dict[str, Any]:
    return {
        "session_id": response.session_id,
        "run_id": response.run_id,
        "final_status": response.final_status,
        "answer": response.answer,
        "summary": response.summary,
        "current_node_id": response.current_node_id,
        "current_url": response.current_url,
        "total_nodes": response.total_nodes,
        "total_edges": response.total_edges,
        "findings": [
            {
                "label": item.label,
                "value": item.value,
                "confidence": item.confidence,
                "source_url": item.source_url,
                "snippet": item.snippet,
            }
            for item in response.findings
        ],
        "final_state": response.final_state,
    }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_str(value: object, field_name: str) -> str:
    text = _optional_str(value)
    if text:
        return text
    raise McpAgentError(
        error_class="InvalidInput",
        message=f"Falta campo requerido: {field_name}",
        retryable=False,
    )


def _llm_runtime_from_payload(value: object) -> LlmRuntimeConfig | None:
    if value is None:
        return None
    if isinstance(value, LlmRuntimeConfig):
        return value
    if isinstance(value, Mapping):
        return LlmRuntimeConfig.from_json_dict(value).resolve_defaults()
    raise TypeError("llm_runtime debe ser LlmRuntimeConfig, mapping o None")


def _new_chat_run_id() -> str:
    from uuid import uuid4

    return f"chat-run-{uuid4().hex[:12]}"
