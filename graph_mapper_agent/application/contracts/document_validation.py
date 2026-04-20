from __future__ import annotations
#graph_mapper_agent/application/contracts/document_validation.py
from typing import Literal

from pydantic import BaseModel, Field

ValidationStatus = Literal["validated", "invalid", "inconclusive", "needs_more_pages"]
ValidationStrategy = Literal["first_page", "first_pages_window", "pattern_search", "visual_page"]
ValidatedCarrier = Literal["pdf", "html_inline", "text_inline", "image", "unknown"]
CarrierRequirementAssessment = Literal[
    "not_applicable",
    "preferred_only",
    "strict_required_and_satisfied",
    "strict_required_but_missing",
]
ValidationScopeAssessment = Literal[
    "final_document_inline",
    "final_document_artifact",
    "carrier_mismatch_but_final_content",
    "index_or_hub",
    "insufficient_local_evidence",
    "unknown",
]


class DocumentValidationLlmOutput(BaseModel):
    status: ValidationStatus
    rationale: str = Field(min_length=1)
    evidence_summary: str = ""
    recommended_next_strategy: ValidationStrategy | None = None
    matched_condition_ids: list[str] = Field(default_factory=list)
    validated_document_family: str | None = None
    validated_year: int | None = None
    validated_carrier: ValidatedCarrier | None = None
    carrier_requirement_assessment: CarrierRequirementAssessment | None = None
    validation_scope_assessment: ValidationScopeAssessment | None = None


GoalValidationLlmOutput = DocumentValidationLlmOutput
