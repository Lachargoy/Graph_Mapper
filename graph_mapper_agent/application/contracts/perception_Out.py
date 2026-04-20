from __future__ import annotations
#graph_mapper_agent/application/contracts/navigation_perception.py
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class NavigationPerceptionCuratedCandidateOutput(BaseModel):
    url: str = Field(min_length=1)
    label: str = ''
    rationale: str = Field(min_length=1)
    source_kind: str | None = None
    score: float = 0.0
    supports_condition_labels: list[str] = Field(default_factory=list)
    target_document_kind_match: str | None = None
    temporal_match: list[str] = Field(default_factory=list)
    progress_likelihood: Literal['low', 'medium', 'high'] | None = None
    is_intra_page_anchor: bool | None = None


class NavigationPerceptionCurrentNodeMatchOutput(BaseModel):
    document_family: str = Field(min_length=1)
    supports_condition_labels: list[str] = Field(default_factory=list)
    rationale: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    artifact_url: str | None = None


class NavigationPerceptionVisualRecoveryHintOutput(BaseModel):
    visible_label: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    suspected_document_family: str | None = None
    matches_condition_labels: list[str] = Field(default_factory=list)


class NavigationPerceptionLlmOutput(BaseModel):
    status: Literal['analyzed', 'inconclusive']
    summary: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_next_step: Literal[
        'use_navigation_frame_candidates',
        'inspect_candidates',
        'inspect_content',
        'validate_current_content',
        'retry_or_expand_navigation_probe',
        'backtrack_or_use_recoverable_choice_points',
    ] | None = None
    layout_kind: Literal[
        'split_navigation_content',
        'candidate_index_with_content',
        'candidate_index',
        'content_only',
        'unknown',
    ] | None = None
    navigation_frame_detected: bool | None = None
    content_frame_detected: bool | None = None
    produced_meaningful_delta: bool | None = None
    goal_slice_exhausted: bool | None = None
    goal_slice_exhaustion_reason: str | None = None
    immediate_condition_gain: int | None = None
    best_immediate_condition_labels: list[str] = Field(default_factory=list)
    strategic_return_suggested: bool | None = None
    strategic_return_reason: str | None = None
    strategic_return_priority: float | None = None
    current_node_goal_match: NavigationPerceptionCurrentNodeMatchOutput | None = None
    visual_recovery_hints: list[NavigationPerceptionVisualRecoveryHintOutput] = Field(default_factory=list)
    curated_candidates: list[NavigationPerceptionCuratedCandidateOutput] = Field(default_factory=list)

    @field_validator('strategic_return_priority', mode='before')
    @classmethod
    def _normalize_optional_float(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {'', 'null', 'none'}:
                return None
        return value
