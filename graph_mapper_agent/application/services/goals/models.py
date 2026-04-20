from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal


CarrierKind = Literal[
    "pdf",
    "html_inline",
    "text_inline",
    "image",
    "unknown",
]


@dataclass(slots=True, frozen=True)
class DynamicGoalCondition:
    condition_id: str
    label: str
    kind: str
    target_kind: str
    requiredness: str = "mandatory"
    filters: dict[str, object] = field(default_factory=dict)
    min_count: int = 1
    status: str = "pending"
    matched_finding_ids: tuple[str, ...] = ()

    def with_evaluation(
        self,
        *,
        status: str,
        matched_finding_ids: tuple[str, ...],
    ) -> "DynamicGoalCondition":
        return replace(
            self,
            status=status,
            matched_finding_ids=matched_finding_ids,
        )

    @property
    def year_filter(self) -> int | None:
        value = self.filters.get("year")
        return value if isinstance(value, int) else None

    @property
    def document_family(self) -> str:
        value = self.filters.get("document_family")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return self.target_kind

    @property
    def preferred_carrier(self) -> CarrierKind | None:
        value = self.filters.get("preferred_carrier")
        if isinstance(value, str) and value.strip():
            return value.strip()  # type: ignore[return-value]
        return None

    @property
    def accepted_carriers(self) -> tuple[CarrierKind, ...]:
        raw = self.filters.get("accepted_carriers")
        if not isinstance(raw, (list, tuple)):
            return ()
        items: list[CarrierKind] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                items.append(item.strip())  # type: ignore[arg-type]
        return tuple(items)

    @property
    def strict_carrier_required(self) -> bool:
        value = self.filters.get("strict_carrier_required")
        return bool(value)

    def allows_carrier(self, carrier: str | None) -> bool:
        if carrier is None:
            return not self.strict_carrier_required

        if self.strict_carrier_required:
            if self.accepted_carriers:
                return carrier in self.accepted_carriers
            if self.preferred_carrier is not None:
                return carrier == self.preferred_carrier
            return False

        if not self.accepted_carriers:
            return True

        return carrier in self.accepted_carriers

    def with_filter_values(self, **updates: object) -> "DynamicGoalCondition":
        merged = dict(self.filters)
        merged.update(updates)
        return replace(self, filters=merged)


@dataclass(slots=True, frozen=True)
class GoalIntent:
    intent_id: str
    source_goal_context: str
    normalized_goal: str


@dataclass(slots=True, frozen=True)
class GoalProposal:
    proposal_id: str
    version: int
    summary: str
    status: str = "draft"
    conditions: tuple[DynamicGoalCondition, ...] = ()
    planning_notes: str | None = None
    parent_proposal_id: str | None = None

    def with_status(self, status: str) -> "GoalProposal":
        return replace(self, status=status)

    def with_conditions(
        self,
        conditions: tuple[DynamicGoalCondition, ...],
    ) -> "GoalProposal":
        return replace(self, conditions=conditions)


@dataclass(slots=True, frozen=True)
class GoalTrace:
    intent: GoalIntent
    proposals: tuple[GoalProposal, ...] = ()
    active_proposal_id: str | None = None
    validation_log: tuple[str, ...] = ()

    def active_proposal(self) -> GoalProposal | None:
        if not self.active_proposal_id:
            return None
        for proposal in self.proposals:
            if proposal.proposal_id == self.active_proposal_id:
                return proposal
        return None

    def get_proposal(self, proposal_id: str) -> GoalProposal | None:
        for proposal in self.proposals:
            if proposal.proposal_id == proposal_id:
                return proposal
        return None


__all__ = [
    "CarrierKind",
    "DynamicGoalCondition",
    "GoalIntent",
    "GoalProposal",
    "GoalTrace",
]
