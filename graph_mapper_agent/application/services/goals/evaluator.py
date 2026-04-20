from __future__ import annotations
#graph_mapper_agent/application/services/goals/evaluator.py
from dataclasses import replace

from graph_mapper_agent.application.services.goals.models import (
    DynamicGoalCondition,
    GoalTrace,
)
from graph_mapper_agent.domain.findings import FindingRecord


class DynamicGoalEvaluator:
    def evaluate(
        self,
        trace: GoalTrace,
        findings: tuple[FindingRecord, ...],
    ) -> GoalTrace:
        active = trace.active_proposal()
        if active is None:
            return trace

        evaluated_conditions = tuple(
            self._evaluate_condition(condition, findings)
            for condition in active.conditions
        )
        updated_active = active.with_conditions(evaluated_conditions)

        proposals = tuple(
            updated_active
            if proposal.proposal_id == updated_active.proposal_id
            else proposal
            for proposal in trace.proposals
        )
        return replace(trace, proposals=proposals)

    def _evaluate_condition(
        self,
        condition: DynamicGoalCondition,
        findings: tuple[FindingRecord, ...],
    ) -> DynamicGoalCondition:
        matched_ids: list[str] = []
        unique_evidence_keys: set[str] = set()

        for finding in findings:
            if not self._matches(condition, finding):
                continue

            matched_ids.append(finding.finding_id)
            evidence_key = self._evidence_key(finding)
            if evidence_key:
                unique_evidence_keys.add(evidence_key)
            else:
                unique_evidence_keys.add(f"finding:{finding.finding_id}")

        matched_count = len(unique_evidence_keys)
        required_count = max(1, condition.min_count)

        status = "satisfied" if matched_count >= required_count else "pending"

        return condition.with_evaluation(
            status=status,
            matched_finding_ids=tuple(matched_ids),
        )

    def _matches(self, condition: DynamicGoalCondition, finding: FindingRecord) -> bool:
        attrs = finding.attributes if isinstance(finding.attributes, dict) else {}

        expected_year = condition.filters.get("year")
        if expected_year is not None and attrs.get("year") != expected_year:
            return False

        if condition.target_kind and not finding_matches_target_kind(condition, finding):
            return False

        return True

    def _evidence_key(self, finding: FindingRecord) -> str | None:
        attrs = finding.attributes if isinstance(finding.attributes, dict) else {}

        for key in (
            "artifact_url",
            "download_url",
            "final_url",
            "source_url",
            "candidate_url",
        ):
            value = attrs.get(key)
            if value:
                return str(value).strip()

        return None


def finding_matches_target_kind(
    condition: DynamicGoalCondition,
    finding: FindingRecord,
) -> bool:
    attrs = finding.attributes if isinstance(finding.attributes, dict) else {}
    validation_status = str(attrs.get("validation_status") or "").strip().lower()
    matched_condition_ids = tuple(
        str(item)
        for item in (attrs.get("matched_condition_ids") or ())
        if str(item).strip()
    )

    if matched_condition_ids:
        return (
            validation_status == "validated"
            and condition.condition_id in matched_condition_ids
        )

    return False


__all__ = [
    "DynamicGoalEvaluator",
    "finding_matches_target_kind",
]