from __future__ import annotations

from graph_mapper_agent.application.goal_validation.models import (
    GoalValidationRequest,
)
from graph_mapper_agent.application.goal_validation.use_cases.progressive_validate_goal import (
    ProgressiveGoalValidationResult,
    ProgressiveGoalValidationUseCase,
)


class GoalValidationService:
    def __init__(self, *, use_case: ProgressiveGoalValidationUseCase) -> None:
        self._use_case = use_case

    def validate(
        self,
        request: GoalValidationRequest,
    ) -> ProgressiveGoalValidationResult:
        return self._use_case.execute(request)
