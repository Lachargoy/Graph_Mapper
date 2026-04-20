from .alignment import goal_aligned_priority, pending_years_from_goal_trace, year_alignment_score
from .evaluator import DynamicGoalEvaluator
from .models import DynamicGoalCondition, GoalIntent, GoalProposal, GoalTrace

__all__ = [
    "DynamicGoalCondition",
    "DynamicGoalEvaluator",
    "GoalIntent",
    "GoalPlannerRequest",
    "GoalPlannerResult",
    "GoalPlannerUseCase",
    "GoalProposal",
    "GoalTrace",
    "goal_aligned_priority",
    "pending_years_from_goal_trace",
    "year_alignment_score",
]


def __getattr__(name: str):
    if name in {"GoalPlannerRequest", "GoalPlannerResult", "GoalPlannerUseCase"}:
        from .planner import GoalPlannerRequest, GoalPlannerResult, GoalPlannerUseCase

        mapping = {
            "GoalPlannerRequest": GoalPlannerRequest,
            "GoalPlannerResult": GoalPlannerResult,
            "GoalPlannerUseCase": GoalPlannerUseCase,
        }
        return mapping[name]
    raise AttributeError(name)
