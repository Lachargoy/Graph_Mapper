from __future__ import annotations

import unittest

from graph_mapper_agent.application.goal_validation import (
    GoalCondition,
    GoalValidationArtifact,
    GoalValidationPass,
    GoalValidationRequest,
    GoalValidationResult,
    ProgressiveGoalValidationResult,
)
from graph_mapper_agent.application.local_perception.models import (
    LocalPerceptionRequest,
    LocalPerceptionTargetRef,
)
from graph_mapper_agent.application.local_perception.service import (
    LocalPerceptionService,
)


class _CaptureGoalValidationService:
    def __init__(self) -> None:
        self.calls: list[GoalValidationRequest] = []

    def validate(
        self,
        request: GoalValidationRequest,
    ) -> ProgressiveGoalValidationResult:
        self.calls.append(request)
        final_result = GoalValidationResult(
            status="validated",
            validation_pass=GoalValidationPass(
                level=1,
                strategy="first_page",
                reason="test",
                page_numbers=(1,),
            ),
            rationale="validated by service",
            recommended_next_strategy=None,
            metadata={
                "matched_condition_ids": ("cond-1",),
                "validated_document_family": "invoice",
                "validated_year": 2025,
                "validation_scope_assessment": "final_document_inline",
            },
        )
        return ProgressiveGoalValidationResult(
            history=(final_result,),
            final_result=final_result,
        )


class LocalPerceptionGoalValidationTests(unittest.TestCase):
    def test_local_perception_uses_goal_validation_request(self) -> None:
        service = _CaptureGoalValidationService()
        local = LocalPerceptionService(goal_validation_service=service)

        request = LocalPerceptionRequest(
            target_kind="artifact_document",
            question="validate evidence",
            target_ref=LocalPerceptionTargetRef(
                artifact=GoalValidationArtifact(inline_text="invoice 2025")
            ),
            goal_conditions=(
                GoalCondition(
                    condition_id="cond-1",
                    label="Invoice 2025",
                    target_kind="invoice",
                    year=2025,
                ),
            ),
            pattern_hints=("invoice",),
            metadata={"source_action": "test"},
        )

        result = local.perceive(request)

        self.assertEqual(1, len(service.calls))
        self.assertIsInstance(service.calls[0], GoalValidationRequest)
        self.assertEqual("validate evidence", service.calls[0].validation_goal)
        self.assertEqual("completed", result.status)
        self.assertEqual("validated", result.metadata["validation_status"])
        self.assertEqual(("cond-1",), result.metadata["matched_condition_ids"])
