from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from graph_mapper_agent.application.goal_validation.artifact_models import (
    GoalValidationArtifact,
)

GoalValidationStatus = Literal[
    "validated",
    "invalid",
    "inconclusive",
    "needs_more_pages",
]
GoalValidationStrategy = Literal[
    "first_page",
    "first_pages_window",
    "pattern_search",
    "visual_page",
]
CarrierKind = Literal[
    "pdf",
    "html_inline",
    "text_inline",
    "image",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class GoalValidationRequest:
    artifact: GoalValidationArtifact
    validation_goal: str
    goal_conditions: tuple["GoalCondition", ...] = ()
    preferred_strategy: GoalValidationStrategy = "first_page"
    max_pages: int = 3
    page_budget: int = 3
    escalation_allowed: bool = True
    pattern_hints: tuple[str, ...] = ()
    target_page: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GoalValidationPass:
    level: int
    strategy: GoalValidationStrategy
    reason: str
    page_numbers: tuple[int, ...] = ()
    pattern_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GoalCondition:
    condition_id: str
    label: str
    target_kind: str
    year: int | None = None
    requiredness: str = "mandatory"
    min_count: int = 1
    document_family: str | None = None
    preferred_carrier: CarrierKind | None = None
    accepted_carriers: tuple[CarrierKind, ...] = ()
    strict_carrier_required: bool = False

    def effective_document_family(self) -> str:
        text = (self.document_family or self.target_kind or "").strip()
        return text or "unknown"

    def effective_accepted_carriers(self) -> tuple[CarrierKind, ...]:
        return tuple(self.accepted_carriers or ())

    def allows_carrier(self, carrier: CarrierKind | None) -> bool:
        if carrier is None:
            return not self.strict_carrier_required

        accepted = self.effective_accepted_carriers()
        if self.strict_carrier_required:
            if accepted:
                return carrier in accepted
            if self.preferred_carrier is not None:
                return carrier == self.preferred_carrier
            return False

        if not accepted:
            return True
        return carrier in accepted


@dataclass(frozen=True, slots=True)
class GoalValidationResult:
    status: GoalValidationStatus
    validation_pass: GoalValidationPass
    rationale: str
    evidence_summary: str = ""
    pages_consumed: int = 0
    recommended_next_strategy: GoalValidationStrategy | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def requests_more_evidence(self) -> bool:
        return self.status in {"inconclusive", "needs_more_pages"}
