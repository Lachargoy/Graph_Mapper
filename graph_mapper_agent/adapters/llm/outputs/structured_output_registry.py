from __future__ import annotations
#graph_mapper_agent/adapters/llm/outputs/structured_output_registry.py
from pydantic import BaseModel

from graph_mapper_agent.application.contracts.research_answer_models import (
    ResearchAnswerSynthesisOutput,
)
from graph_mapper_agent.application.contracts.evidence_coverage_models import (
    EvidenceCoverageAssessmentOutput,
)
from graph_mapper_agent.application.services.decision.contracts import (
    GraphMapperNavigationDecision,
)
from graph_mapper_agent.application.services.goals.planner_models import (
    GoalPlanningOutput,
    PlanningTurnOutput,)


from graph_mapper_agent.application.contracts.document_validation import (
    DocumentValidationLlmOutput,
    GoalValidationLlmOutput,
)
from graph_mapper_agent.application.contracts.perception_Out import NavigationPerceptionLlmOutput



def resolve_output_type(expected_output_name: str | None) -> type[BaseModel] | None:
    if expected_output_name == "graph_mapper_navigation_decision":
        return GraphMapperNavigationDecision
    if expected_output_name == "graph_mapper_goal_planning":
        return GoalPlanningOutput
    if expected_output_name == "graph_mapper_planning_turn":
        return PlanningTurnOutput
    if expected_output_name == "graph_mapper_research_answer_synthesis":
        return ResearchAnswerSynthesisOutput
    if expected_output_name == "graph_mapper_evidence_coverage":
        return EvidenceCoverageAssessmentOutput
    if expected_output_name == "goal_validation_output":
        return GoalValidationLlmOutput
    if expected_output_name == "document_validation_output":
        return DocumentValidationLlmOutput
    if expected_output_name == "navigation_perception_output":
        return NavigationPerceptionLlmOutput
    return None
