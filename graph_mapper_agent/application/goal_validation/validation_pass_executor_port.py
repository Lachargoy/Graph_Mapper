from __future__ import annotations

from typing import Protocol

from graph_mapper_agent.application.goal_validation.validation_models import (
    GoalValidationPass,
    GoalValidationRequest,
    GoalValidationResult,
)


class GoalValidationPassExecutorPort(Protocol):
    def execute_pass(
        self,
        request: GoalValidationRequest,
        validation_pass: GoalValidationPass,
    ) -> GoalValidationResult: ...


__all__ = ["GoalValidationPassExecutorPort"]
