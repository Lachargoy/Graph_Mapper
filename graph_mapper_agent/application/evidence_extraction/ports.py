from __future__ import annotations

from typing import Protocol

from .models import (
    EvidenceCoverageAssessment,
    EvidenceExtractionRequest,
    EvidenceExtractionResult,
)


class EvidenceExtractorPort(Protocol):
    def extract(self, request: EvidenceExtractionRequest) -> EvidenceExtractionResult: ...


class VisualEvidenceExtractorPort(Protocol):
    def extract_visual(
        self,
        request: EvidenceExtractionRequest,
    ) -> EvidenceExtractionResult: ...


class OcrEvidenceExtractorPort(Protocol):
    def extract_ocr(
        self,
        request: EvidenceExtractionRequest,
    ) -> EvidenceExtractionResult: ...


class EvidenceCoverageAssessorPort(Protocol):
    def assess_coverage(
        self,
        *,
        request: EvidenceExtractionRequest,
        result: EvidenceExtractionResult,
    ) -> EvidenceCoverageAssessment: ...
