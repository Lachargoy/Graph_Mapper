from __future__ import annotations
#graph_mapper_agent/application/contracts/research_answer_models.py
from pydantic import BaseModel, Field


class ResearchAnswerSynthesisOutput(BaseModel):
    status: str = Field(
        ...,
        description="Synthesis status: ready, needs_more_research, or inconclusive.",
    )
    final_answer: str = Field(
        ...,
        description="Clear final answer for the user.",
    )
    follow_up_recommendation: str | None = Field(
        default=None,
        description="Suggested next step if more research is needed.",
    )