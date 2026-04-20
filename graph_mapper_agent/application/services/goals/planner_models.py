from __future__ import annotations
#graph_mapper_agent/application/contracts/goal_planning_models.py
from pydantic import BaseModel, Field


class PlannedGoalCondition(BaseModel):
    condition_id: str = Field(..., description="Stable identifier for the active condition.")
    label: str = Field(..., description="Short human-readable label for the condition.")
    kind: str = Field(..., description="Structural type of the condition.")
    target_kind: str = Field(
        ...,
        description=(
            "General class of the target goal or expected deliverable. "
            "It must not, by itself, mix document family with strict carrier requirements."
        ),
    )
    requiredness: str = Field(default="mandatory", description="Level of requirement.")
    filters: dict[str, object] = Field(
        default_factory=dict,
        description=(
            "Structured restrictions used to evaluate the condition. "
            "It may include year, document_family, preferred_carrier, "
            "accepted_carriers, and strict_carrier_required."
        ),
    )
    min_count: int = Field(default=1, description="Minimum required count to satisfy the condition.")


class GoalPlanningOutput(BaseModel):
    goal_intent: str | None = Field(
        default=None,
        description="Normalized base intent of the requested goal.",
    )
    proposal_summary: str | None = Field(
        default=None,
        description="Operational summary of the current planner proposal.",
    )
    conditions: list[PlannedGoalCondition] = Field(
        default_factory=list,
        description="Structured active conditions proposed by the planner.",
    )
    planning_notes: str | None = Field(
        default=None,
        description="Brief notes about how the goal was decomposed.",
    )


class PlanningTurnOutput(BaseModel):
    turn_kind: str = Field(
        ...,
        description="Conversational turn type: conversation, plan_update, or launch.",
    )
    has_research_goal: bool = Field(
        default=False,
        description="Indicates whether the turn already contains a real researchable goal.",
    )
    assistant_reply: str = Field(
        ...,
        description="Short natural conversational reply to show to the user.",
    )
    plan_patch: dict[str, object] = Field(
        default_factory=dict,
        description="Proposed changes to the current conversational plan.",
    )


__all__ = [
    "GoalPlanningOutput",
    "PlanningTurnOutput",
    "PlannedGoalCondition",
]