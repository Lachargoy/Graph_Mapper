from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar


StrategyT = TypeVar("StrategyT")
RequestT = TypeVar("RequestT")
ResultT = TypeVar("ResultT")


class GoalScheduler(Protocol[StrategyT, RequestT, ResultT]):
    def choose_next_goal(
        self,
        goals: list["NavigationGoal[StrategyT, RequestT, ResultT]"],
    ) -> "NavigationGoal[StrategyT, RequestT, ResultT] | None": ...


@dataclass
class NavigationGoal(Generic[StrategyT, RequestT, ResultT]):
    goal_id: str
    intent: str
    request: RequestT
    strategy: StrategyT
    priority: int = 0
    metadata: dict[str, object] | None = None
    strategy_state: object | None = None
    status: str = "pending"
    result: ResultT | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class PriorityGoalScheduler(Generic[StrategyT, RequestT, ResultT]):
    def choose_next_goal(
        self,
        goals: list[NavigationGoal[StrategyT, RequestT, ResultT]],
    ) -> NavigationGoal[StrategyT, RequestT, ResultT] | None:
        active = [goal for goal in goals if goal.status in {"pending", "running"}]
        if not active:
            return None
        active.sort(key=lambda goal: (-goal.priority, goal.goal_id))
        return active[0]


@dataclass
class GoalLoop(Generic[StrategyT, RequestT, ResultT]):
    scheduler: GoalScheduler[StrategyT, RequestT, ResultT] = field(
        default_factory=PriorityGoalScheduler
    )
    goals: list[NavigationGoal[StrategyT, RequestT, ResultT]] = field(
        default_factory=list
    )

    def add_goal(self, goal: NavigationGoal[StrategyT, RequestT, ResultT]) -> None:
        self.goals.append(goal)

    def next_goal(self) -> NavigationGoal[StrategyT, RequestT, ResultT] | None:
        goal = self.scheduler.choose_next_goal(self.goals)
        if goal is not None and goal.status == "pending":
            goal.status = "running"
        return goal

    def mark_completed(self, goal_id: str, result: ResultT) -> None:
        goal = self._get(goal_id)
        goal.status = "completed"
        goal.result = result
        goal.error = None

    def mark_failed(self, goal_id: str, error: Exception) -> None:
        goal = self._get(goal_id)
        goal.status = "failed"
        goal.error = error

    def mark_waiting(self, goal_id: str) -> None:
        goal = self._get(goal_id)
        goal.status = "pending"

    def unresolved(self) -> list[NavigationGoal[StrategyT, RequestT, ResultT]]:
        return [
            goal for goal in self.goals if goal.status not in {"completed", "failed"}
        ]

    def _get(self, goal_id: str) -> NavigationGoal[StrategyT, RequestT, ResultT]:
        for goal in self.goals:
            if goal.goal_id == goal_id:
                return goal
        raise KeyError(f"Unknown goal_id: {goal_id}")

