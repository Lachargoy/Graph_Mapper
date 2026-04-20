from __future__ import annotations
#aither/application/web_navigation/navigation_perception/models.py
from dataclasses import dataclass, field
from typing import Literal

from graph_mapper_agent.domain.graph import ObservedCandidate

NavigationPerceptionStatus = Literal[
    'analyzed',
    'inconclusive',
]


@dataclass(frozen=True, slots=True)
class NavigationPerceptionRequest:
    question: str
    node_id: str | None = None
    url: str | None = None
    pattern_hints: tuple[str, ...] = ()
    goal_summary: str | None = None
    pending_goal_conditions: tuple[str, ...] = ()
    target_document_kinds: tuple[str, ...] = ()
    temporal_constraints: tuple[str, ...] = ()
    include_screenshot: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    url: str
    label: str
    score: float
    rationale: str
    source_kind: str | None = None
    supports_condition_labels: tuple[str, ...] = ()
    target_document_kind_match: str | None = None
    temporal_match: tuple[str, ...] = ()
    progress_likelihood: str | None = None
    is_intra_page_anchor: bool | None = None


@dataclass(frozen=True, slots=True)
class VisualRecoveryHint:
    visible_label: str
    rationale: str
    confidence: float | None = None
    suspected_document_family: str | None = None
    matches_condition_labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CurrentNodeGoalMatch:
    document_family: str
    supports_condition_labels: tuple[str, ...] = ()
    rationale: str | None = None
    confidence: float | None = None
    artifact_url: str | None = None


@dataclass(frozen=True, slots=True)
class NavigationPerceptionResult:
    status: NavigationPerceptionStatus
    summary: str
    confidence: float
    recommended_next_step: str | None = None
    layout_kind: str | None = None
    visible_candidate_count: int | None = None
    navigation_frame_detected: bool | None = None
    content_frame_detected: bool | None = None
    produced_meaningful_delta: bool | None = None
    goal_slice_exhausted: bool | None = None
    goal_slice_exhaustion_reason: str | None = None
    immediate_condition_gain: int | None = None
    best_immediate_condition_labels: tuple[str, ...] = ()
    strategic_return_suggested: bool | None = None
    strategic_return_reason: str | None = None
    strategic_return_priority: float | None = None
    current_node_goal_match: CurrentNodeGoalMatch | None = None
    visual_recovery_hints: tuple[VisualRecoveryHint, ...] = ()
    top_candidate_observations: tuple[CandidateObservation, ...] = ()
    observed_candidates: tuple[ObservedCandidate, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)
