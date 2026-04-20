from __future__ import annotations

from graph_mapper_agent.application.use_cases import (
    ResearchChatRequest,
    chat_with_research,
)
from graph_mapper_agent.bootstrap.builders.ledger import (
    build_ledger_writer,
)

from .models import ChatTurnRequest, ChatTurnResponse


def process_chat_turn(request: ChatTurnRequest) -> ChatTurnResponse:
    request.validate()

    session_id = request.resolved_session_id()
    writer = build_ledger_writer(request.ledger_database_url)

    user_message_id = _record_chat_user_message(
        writer=writer,
        session_id=session_id,
        request=request,
    )

    research_response = chat_with_research(
        ResearchChatRequest(
            user_message=request.user_message,
            entry_url=request.entry_url,
            session_id=session_id,
            research_mode=request.research_mode,
            decision_mode=request.decision_mode,
            max_hops=request.max_hops,
            max_pages=request.max_pages,
            timeout_seconds=request.timeout_seconds,
            allow_artifact_download=request.allow_artifact_download,
            allow_artifact_open=request.allow_artifact_open,
            run_id=request.run_id,
            workflow_name="graph_mapper_chat",
            source_namespace=request.source_namespace,
            resource_key=request.resource_key,
            metadata=dict(request.metadata),
            execution_metadata={
                "interface_kind": "chat",
                "session_id": session_id,
                **dict(request.execution_metadata),
            },
            llm_runtime=request.llm_runtime,
            navigation_perception_llm_runtime=request.navigation_perception_llm_runtime,
            goal_validation_llm_runtime=request.goal_validation_llm_runtime,
            evidence_extraction_visual_llm_runtime=request.evidence_extraction_visual_llm_runtime,
            evidence_extraction_ocr_llm_runtime=request.evidence_extraction_ocr_llm_runtime,
            ledger_database_url=request.ledger_database_url,
        )
    )

    assistant_message_id = _record_chat_assistant_message(
        writer=writer,
        session_id=session_id,
        response=research_response,
    )

    return ChatTurnResponse(
        session_id=session_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        research_response=research_response,
    )


def _record_chat_user_message(
    *,
    writer: object | None,
    session_id: str,
    request: ChatTurnRequest,
) -> str | None:
    if writer is None:
        return None

    record_session = getattr(writer, "record_session", None)
    if callable(record_session):
        record_session(
            session_id=session_id,
            session_kind="chat",
            context={
                "entry_url": request.entry_url,
                "source_namespace": request.source_namespace,
                "resource_key": request.resource_key,
            },
            metadata={
                "last_run_id": request.run_id,
            },
        )

    record_message = getattr(writer, "record_message", None)
    if not callable(record_message):
        return None
    return record_message(
        session_id=session_id,
        role="user",
        content={
            "text": request.user_message,
            "entry_url": request.entry_url,
        },
        metadata={
            "kind": "chat_turn_input",
            "run_id": request.run_id,
        },
    )


def _record_chat_assistant_message(
    *,
    writer: object | None,
    session_id: str,
    response,
) -> str | None:
    if writer is None:
        return None
    record_message = getattr(writer, "record_message", None)
    if not callable(record_message):
        return None
    return record_message(
        session_id=session_id,
        role="assistant",
        content={
            "answer": response.answer,
            "summary": response.summary,
            "final_status": response.final_status,
            "current_url": response.current_url,
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
        },
        metadata={
            "kind": "chat_turn_output",
            "run_id": response.run_id,
        },
    )
