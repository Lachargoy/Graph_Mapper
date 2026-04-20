from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)


@dataclass(frozen=True)
class ResearchChatRequest:
    user_message: str
    entry_url: str
    session_id: str | None = None
    research_mode: str = "collect_artifacts"

    decision_mode: str = "llm"
    max_hops: int = 250
    max_pages: int = 500
    timeout_seconds: int = 200

    allow_artifact_download: bool = True
    allow_artifact_open: bool = True

    run_id: str = field(default_factory=lambda: f"research-{uuid4().hex[:12]}")
    workflow_name: str = "graph_mapper_chat"
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

    def validate(self) -> None:
        if not self.user_message.strip():
            raise ValueError("ResearchChatRequest.user_message cannot be empty.")
        if not self.entry_url.strip():
            raise ValueError("ResearchChatRequest.entry_url cannot be empty.")
        if self.max_hops <= 0:
            raise ValueError("ResearchChatRequest.max_hops must be > 0.")
        if self.max_pages <= 0:
            raise ValueError("ResearchChatRequest.max_pages must be > 0.")
        if self.timeout_seconds <= 0:
            raise ValueError("ResearchChatRequest.timeout_seconds must be > 0.")
        if self.decision_mode not in {"heuristic", "llm"}:
            raise ValueError(
                "ResearchChatRequest.decision_mode must be 'heuristic' or 'llm'."
            )
        if self.research_mode not in {"read_only", "collect_artifacts", "mixed"}:
            raise ValueError(
                "ResearchChatRequest.research_mode must be "
                "'read_only', 'collect_artifacts' or 'mixed'."
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
class ResearchChatFinding:
    label: str
    value: str
    confidence: float | None = None
    source_url: str | None = None
    snippet: str | None = None


@dataclass(frozen=True)
class ResearchChatEvidence:
    source_url: str | None = None
    carrier: str | None = None
    text_excerpt: str | None = None
    page_number: int | None = None
    mime_type: str | None = None


@dataclass(frozen=True)
class ResearchChatResponse:
    session_id: str
    run_id: str
    final_status: str | None
    answer: str
    summary: str
    current_node_id: str | None
    current_url: str | None
    total_nodes: int
    total_edges: int
    findings: tuple[ResearchChatFinding, ...] = ()
    extracted_evidence: tuple[ResearchChatEvidence, ...] = ()
    final_state: dict[str, object] = field(default_factory=dict)
