from __future__ import annotations

from dataclasses import replace

from .models import EvidenceExtractionRequest, EvidenceExtractionResult
from .ports import EvidenceCoverageAssessorPort, EvidenceExtractorPort


class EvidenceExtractionService:
    def __init__(
        self,
        *,
        extractor: EvidenceExtractorPort,
        coverage_assessor: EvidenceCoverageAssessorPort | None = None,
    ) -> None:
        self._extractor = extractor
        self._coverage_assessor = coverage_assessor

    def extract(self, request: EvidenceExtractionRequest) -> EvidenceExtractionResult:
        result = self._extractor.extract(request)
        if self._coverage_assessor is None:
            return result
        try:
            assessment = self._coverage_assessor.assess_coverage(
                request=request,
                result=result,
            )
        except Exception:
            return result
        metadata = dict(result.metadata)
        metadata["coverage_assessment"] = {
            "coverage_status": assessment.coverage_status,
            "primary_content_detected": assessment.primary_content_detected,
            "sufficiency_for_goal_validation": assessment.sufficiency_for_goal_validation,
            "rationale": assessment.rationale,
            "missing_content_signals": list(assessment.missing_content_signals),
        }
        return replace(
            result,
            coverage_assessment=assessment,
            metadata=metadata,
        )
