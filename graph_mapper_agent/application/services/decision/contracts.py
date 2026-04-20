from __future__ import annotations
#graph_mapper_agent/application/services/decision/contracts.py
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


GraphMapperAction = Literal[
    "refine_navigation_perception",
    "validate_current_content",
    "follow_edge",
    "download_artifact",
    "open_artifact",
    "search_with_text",
    "mark_exhausted",
    "success",
]


@dataclass(slots=True, frozen=True)
class ScratchpadUpdate:
    working_plan: str | None = None
    tactical_observations: str | None = None


@dataclass(slots=True, frozen=True)
class GraphMapperDecision:
    action: str
    edge_id: str | None = None
    search_target_id: str | None = None
    query_text: str | None = None
    decision_rationale: str | None = None
    confidence: float | None = None
    scratchpad_update: ScratchpadUpdate | None = None


class ScratchpadUpdatePayload(BaseModel):
    working_plan: str | None = Field(default=None)
    tactical_observations: str | None = Field(default=None)


class GraphMapperNavigationDecision(BaseModel):
    action: GraphMapperAction = Field(...)
    edge_id: str | None = Field(default=None)
    search_target_id: str | None = Field(
        default=None,
        description=(
            "ID of the available search target listed in AVAILABLE SEARCH TARGETS. "
            "Only applies to search_with_text."
        ),
    )
    query_text: str | None = Field(
        default=None,
        description=(
            "Search text to send to the selected search target. "
            "Only applies to search_with_text."
        ),
    )
    decision_rationale: str | None = Field(default=None)
    confidence: float | None = Field(default=None)
    scratchpad_update: ScratchpadUpdatePayload | None = Field(
        default=None,
        description=(
            "Optional update to the tactical scratchpad. "
            "Use working_plan for the current plan and tactical_observations "
            "for relevant tactical notes."
        ),
    )


def parse_scratchpad_update(value: object) -> ScratchpadUpdate | None:
    if not isinstance(value, dict):
        return None
    working_plan = safe_str(value.get("working_plan"))
    tactical_observations = safe_str(value.get("tactical_observations"))
    if not working_plan and not tactical_observations:
        return None
    return ScratchpadUpdate(
        working_plan=working_plan,
        tactical_observations=tactical_observations,
    )


def safe_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "GraphMapperAction",
    "GraphMapperDecision",
    "GraphMapperNavigationDecision",
    "ScratchpadUpdate",
    "ScratchpadUpdatePayload",
    "parse_scratchpad_update",
    "safe_str",
]