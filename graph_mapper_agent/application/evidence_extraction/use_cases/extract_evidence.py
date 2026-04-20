from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.application.evidence_extraction.models import (
    EvidenceExtractionRequest,
    EvidenceExtractionResult,
)
from graph_mapper_agent.application.evidence_extraction.service import (
    EvidenceExtractionService,
)
from graph_mapper_agent.application.goal_validation import (
    GoalValidationResult,
)


@dataclass(frozen=True, slots=True)
class ValidatedEvidenceExtractionRequest:
    extraction_request: EvidenceExtractionRequest
    goal_validation_result: GoalValidationResult


class ExtractEvidenceUseCase:
    def __init__(self, *, service: EvidenceExtractionService) -> None:
        self._service = service

    def execute(
        self,
        request: ValidatedEvidenceExtractionRequest,
    ) -> EvidenceExtractionResult:
        if request.goal_validation_result.status != "validated":
            raise ValueError(
                "ExtractEvidenceUseCase requiere goal_validation_result.status='validated'."
            )
        return self._service.extract(request.extraction_request)
