from __future__ import annotations
#graph_mapper_agent/application/contracts/evidence_coverage_models.py
from pydantic import BaseModel, Field


class EvidenceCoverageAssessmentOutput(BaseModel):
    coverage_status: str = Field(
        ...,
        description="Coverage level: partial, substantial, or complete.",
    )
    primary_content_detected: bool = Field(
        ...,
        description="Indicates whether the primary content of the resource was detected.",
    )
    sufficiency_for_goal_validation: bool = Field(
        ...,
        description="Indicates whether the observed coverage appears sufficient to validate the goal.",
    )
    rationale: str = Field(
        ...,
        description="Brief justification for the coverage assessment.",
    )
    missing_content_signals: list[str] = Field(
        default_factory=list,
        description="Signals indicating missing or partial content.",
    )