from __future__ import annotations

from typing import Protocol

from graph_mapper_agent.application.goal_validation import (
    GoalValidationRequest,
    ProgressiveGoalValidationResult,
)


class GoalValidationUseCasePort(Protocol):
    def execute(
        self,
        request: GoalValidationRequest,
    ) -> ProgressiveGoalValidationResult: ...
