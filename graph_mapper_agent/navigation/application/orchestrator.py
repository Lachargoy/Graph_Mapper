from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, Mapping, TypeVar

from graph_mapper_agent.navigation.domain.goals import (
    GoalLoop,
    GoalScheduler,
    NavigationGoal,
    PriorityGoalScheduler,
)
from graph_mapper_agent.navigation.runtime.engine import (
    StateMachineEngine,
    TransitionDefinition,
)


ResultT = TypeVar("ResultT")
StrategyT = TypeVar("StrategyT")
RequestT = TypeVar("RequestT")


@dataclass(frozen=True)
class NavigationOrchestrator:
    transitions: dict[str, TransitionDefinition]
    terminal_states: set[str] = field(default_factory=lambda: {"success", "fail"})
    max_steps: int = 256

    def build_engine(self) -> StateMachineEngine:
        return StateMachineEngine(
            transitions=self.transitions,
            terminal_states=self.terminal_states,
            max_steps=self.max_steps,
        )

    def execute(
        self,
        initial_state: Mapping[str, object],
        *,
        start_at: str,
    ) -> dict[str, object]:
        return self.build_engine().execute(initial_state, start_at=start_at)


@dataclass(frozen=True)
class GoalExecutionResult(Generic[ResultT]):
    completed: tuple[tuple[str, ResultT], ...] = ()
    failed: tuple[tuple[str, Exception], ...] = ()


@dataclass(frozen=True)
class GoalOrchestrator(Generic[StrategyT, RequestT, ResultT]):
    scheduler: GoalScheduler[StrategyT, RequestT, ResultT] = field(
        default_factory=PriorityGoalScheduler
    )

    def execute(
        self,
        *,
        goals: list[NavigationGoal[StrategyT, RequestT, ResultT]],
        executor: Callable[[NavigationGoal[StrategyT, RequestT, ResultT]], ResultT],
    ) -> GoalExecutionResult[ResultT]:
        goal_loop: GoalLoop[StrategyT, RequestT, ResultT] = GoalLoop(
            scheduler=self.scheduler
        )
        for goal in goals:
            goal_loop.add_goal(goal)

        completed: list[tuple[str, ResultT]] = []
        failed: list[tuple[str, Exception]] = []

        while True:
            current = goal_loop.next_goal()
            if current is None:
                break
            try:
                result = executor(current)
            except Exception as exc:
                goal_loop.mark_failed(current.goal_id, exc)
                failed.append((current.goal_id, exc))
                continue

            goal_loop.mark_completed(current.goal_id, result)
            completed.append((current.goal_id, result))

        return GoalExecutionResult(
            completed=tuple(completed),
            failed=tuple(failed),
        )
