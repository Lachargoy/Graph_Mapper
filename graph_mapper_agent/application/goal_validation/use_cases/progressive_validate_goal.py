from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.application.goal_validation.models import (
    GoalValidationRequest,
    GoalValidationResult,
)
from graph_mapper_agent.application.goal_validation.policy import (
    GoalValidationPolicy,
)
from graph_mapper_agent.application.goal_validation.validation_pass_executor_port import (
    GoalValidationPassExecutorPort,
)


@dataclass(frozen=True, slots=True)
class ProgressiveGoalValidationResult:
    history: tuple[GoalValidationResult, ...]
    final_result: GoalValidationResult


class ProgressiveGoalValidationUseCase:
    def __init__(
        self,
        *,
        policy: GoalValidationPolicy,
        executor: GoalValidationPassExecutorPort,
    ) -> None:
        self._policy = policy
        self._executor = executor

    def execute(
        self,
        request: GoalValidationRequest,
    ) -> ProgressiveGoalValidationResult:
        history: list[GoalValidationResult] = []

        while True:
            next_pass = self._policy.next_pass(request, history=tuple(history))
            if next_pass is None:
                if not history:
                    raise RuntimeError("Validation policy returned no initial pass")
                return ProgressiveGoalValidationResult(
                    history=tuple(history),
                    final_result=history[-1],
                )

            result = self._executor.execute_pass(request, next_pass)
            history.append(result)

            if not result.requests_more_evidence():
                return ProgressiveGoalValidationResult(
                    history=tuple(history),
                    final_result=result,
                )
