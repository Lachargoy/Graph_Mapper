from __future__ import annotations
#graph_mapper_agent/application/services/decision/llm_context.py
from dataclasses import dataclass
from typing import Any

from graph_mapper_agent.application.services.decision.contracts import (
    ScratchpadUpdate,
)
from graph_mapper_agent.domain.view import NodeView


@dataclass
class DecisionLlmContext:
    node_view: NodeView
    action: str
    edge_id: str | None
    search_target_id: str | None
    query_text: str | None
    confidence: float | None
    rationale: str | None
    scratchpad: ScratchpadUpdate | None
    selected_candidate: Any
    selected_search_target: Any
    arrival_edge_id: str | None
    working_plan: str | None
    tactical_observations: str | None

    def or_confidence(self, default: float) -> float:
        return self.confidence if self.confidence is not None else default

    def suffixed(self, suffix: str, default_base: str = "") -> str:
        base = self.rationale or default_base
        return f"{base} | {suffix}" if base else suffix


__all__ = ["DecisionLlmContext"]
