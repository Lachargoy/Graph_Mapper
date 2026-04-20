from __future__ import annotations

from typing import TYPE_CHECKING

from graph_mapper_agent.application.goal_validation.models import (
    GoalValidationRequest,
)
from graph_mapper_agent.application.goal_validation.use_cases.progressive_validate_goal import (
    ProgressiveGoalValidationResult,
)

if TYPE_CHECKING:
    from graph_mapper_agent.application.goal_validation.service import (
        GoalValidationService,
    )


class ValidateGoalUseCase:
    def __init__(self, *, service: GoalValidationService) -> None:
        self._service = service

    def execute(
        self,
        request: GoalValidationRequest,
    ) -> ProgressiveGoalValidationResult:
        return self._service.validate(request)
