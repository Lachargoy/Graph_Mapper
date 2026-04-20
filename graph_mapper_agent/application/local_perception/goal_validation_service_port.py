from __future__ import annotations

from typing import Protocol

from graph_mapper_agent.application.goal_validation import (
    GoalValidationRequest,
    ProgressiveGoalValidationResult,
)


class GoalValidationServicePort(Protocol):
    def validate(
        self,
        request: GoalValidationRequest,
    ) -> ProgressiveGoalValidationResult: ...
