from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from graph_mapper_agent.application.goal_validation.artifact_models import (
    GoalValidationArtifact,
)
from graph_mapper_agent.application.goal_validation.validation_models import (
    GoalCondition,
)

LocalPerceptionTargetKind = Literal[
    'artifact_document',
    'inline_document_content',
    'navigation_state',
]

LocalPerceptionStatus = Literal[
    'completed',
    'unsupported',
]


@dataclass(frozen=True, slots=True)
class LocalPerceptionTargetRef:
    artifact: GoalValidationArtifact | None = None
    node_id: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class LocalPerceptionRequest:
    target_kind: LocalPerceptionTargetKind
    question: str
    target_ref: LocalPerceptionTargetRef
    goal_conditions: tuple[GoalCondition, ...] = ()
    pattern_hints: tuple[str, ...] = ()
    max_pages: int = 3
    page_budget: int = 3
    escalation_allowed: bool = True
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LocalPerceptionResult:
    target_kind: LocalPerceptionTargetKind
    status: LocalPerceptionStatus
    confidence: float
    summary: str
    recommended_next_step: str | None = None
    payload: object | None = None
    metadata: dict[str, object] = field(default_factory=dict)
