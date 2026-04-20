from __future__ import annotations

from graph_mapper_agent.application.evidence_extraction.models import (
    EvidenceExtractionRequest,
    EvidenceExtractionResult,
)
from graph_mapper_agent.application.evidence_extraction.ports import (
    EvidenceExtractorPort,
    OcrEvidenceExtractorPort,
    VisualEvidenceExtractorPort,
)


class RoutingEvidenceExtractor(EvidenceExtractorPort):
    def __init__(
        self,
        *,
        pdf_extractor: EvidenceExtractorPort,
        html_extractor: EvidenceExtractorPort,
        visual_extractor: VisualEvidenceExtractorPort | None = None,
        ocr_extractor: OcrEvidenceExtractorPort | None = None,
    ) -> None:
        self._pdf_extractor = pdf_extractor
        self._html_extractor = html_extractor
        self._visual_extractor = visual_extractor
        self._ocr_extractor = ocr_extractor

    def extract(self, request: EvidenceExtractionRequest) -> EvidenceExtractionResult:
        carrier = request.artifact.infer_carrier()
        if carrier == "pdf":
            return self._pdf_extractor.extract(request)
        if carrier in {"html", "text"}:
            return self._html_extractor.extract(request)
        if carrier in {"image", "screenshot"}:
            return self._extract_visual(request)
        return EvidenceExtractionResult(
            carrier=carrier,
            items=(),
            metadata={"source": "routing", "status": "unsupported_carrier"},
        )

    def _extract_visual(
        self,
        request: EvidenceExtractionRequest,
    ) -> EvidenceExtractionResult:
        strategy = request.visual_strategy
        if strategy == "prefer_ocr":
            return self._try_ocr_then_vision(request)
        if strategy == "ocr_then_vision_fallback":
            return self._try_ocr_then_vision(request)
        if strategy == "vision_then_ocr_fallback":
            return self._try_vision_then_ocr(request)
        return self._try_vision_then_ocr(request)

    def _try_vision_then_ocr(
        self,
        request: EvidenceExtractionRequest,
    ) -> EvidenceExtractionResult:
        if self._visual_extractor is not None:
            result = self._visual_extractor.extract_visual(request)
            if result.items:
                return result
        if self._ocr_extractor is not None:
            result = self._ocr_extractor.extract_ocr(request)
            if result.items:
                return result
        return EvidenceExtractionResult(
            carrier=request.artifact.infer_carrier(),
            items=(),
            metadata={"source": "routing", "status": "no_visual_backend_available"},
        )

    def _try_ocr_then_vision(
        self,
        request: EvidenceExtractionRequest,
    ) -> EvidenceExtractionResult:
        if self._ocr_extractor is not None:
            result = self._ocr_extractor.extract_ocr(request)
            if result.items:
                return result
        if self._visual_extractor is not None:
            result = self._visual_extractor.extract_visual(request)
            if result.items:
                return result
        return EvidenceExtractionResult(
            carrier=request.artifact.infer_carrier(),
            items=(),
            metadata={"source": "routing", "status": "no_visual_backend_available"},
        )
