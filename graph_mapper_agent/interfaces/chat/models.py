from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from graph_mapper_agent.application.use_cases.chat_models import (
    ResearchChatResponse,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)


@dataclass(frozen=True)
class ChatTurnRequest:
    user_message: str
    entry_url: str

    session_id: str | None = None
    run_id: str = field(default_factory=lambda: f"chat-run-{uuid4().hex[:12]}")
    research_mode: str = "collect_artifacts"

    decision_mode: str = "llm"
    max_hops: int = 250
    max_pages: int = 500
    timeout_seconds: int = 200

    allow_artifact_download: bool = True
    allow_artifact_open: bool = True

    source_namespace: str = "generic"
    resource_key: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)
    execution_metadata: dict[str, Any] = field(default_factory=dict)

    llm_runtime: LlmRuntimeConfig | None = None
    navigation_perception_llm_runtime: LlmRuntimeConfig | None = None
    goal_validation_llm_runtime: LlmRuntimeConfig | None = None
    evidence_extraction_visual_llm_runtime: LlmRuntimeConfig | None = None
    evidence_extraction_ocr_llm_runtime: LlmRuntimeConfig | None = None
    ledger_database_url: str | None = None

    def resolved_session_id(self) -> str:
        value = str(self.session_id or "").strip()
        if value:
            return value
        return f"session-{self.run_id}"

    def validate(self) -> None:
        if not self.user_message.strip():
            raise ValueError("ChatTurnRequest.user_message must not be empty.")
        if not self.entry_url.strip():
            raise ValueError("ChatTurnRequest.entry_url must not be empty.")
        if self.max_hops <= 0:
            raise ValueError("ChatTurnRequest.max_hops must be > 0.")
        if self.max_pages <= 0:
            raise ValueError("ChatTurnRequest.max_pages must be > 0.")
        if self.timeout_seconds <= 0:
            raise ValueError("ChatTurnRequest.timeout_seconds must be > 0.")
        if self.decision_mode not in {"heuristic", "llm"}:
            raise ValueError(
                "ChatTurnRequest.decision_mode must be 'heuristic' or 'llm'."
            )
        if self.research_mode not in {"read_only", "collect_artifacts", "mixed"}:
            raise ValueError(
                "ChatTurnRequest.research_mode must be "
                "'read_only', 'collect_artifacts', or 'mixed'."
            )
        if self.llm_runtime is not None:
            self.llm_runtime.validate()
        if self.navigation_perception_llm_runtime is not None:
            self.navigation_perception_llm_runtime.validate()
        if self.goal_validation_llm_runtime is not None:
            self.goal_validation_llm_runtime.validate()
        if self.evidence_extraction_visual_llm_runtime is not None:
            self.evidence_extraction_visual_llm_runtime.validate()
        if self.evidence_extraction_ocr_llm_runtime is not None:
            self.evidence_extraction_ocr_llm_runtime.validate()


@dataclass(frozen=True)
class ChatTurnResponse:
    session_id: str
    user_message_id: str | None
    assistant_message_id: str | None
    research_response: ResearchChatResponse
