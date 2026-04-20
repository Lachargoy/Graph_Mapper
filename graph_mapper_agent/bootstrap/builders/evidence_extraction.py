from __future__ import annotations
#graph_mapper_agent/bootstrap/builders/evidence_extraction.py
from graph_mapper_agent.adapters.goal_validation.pdf_pymupdf_reader import (
    PyMuPdfGoalValidationPdfEvidenceReader,
)
from graph_mapper_agent.adapters.evidence_extraction import (
    GlmOcrEvidenceExtractor,
    HtmlEvidenceExtractor,
    LlmEvidenceCoverageAssessor,
    OllamaOcrEvidenceExtractor,
    OcrRuntimeEvidenceExtractor,
    PyMuPdfEvidenceExtractor,
    RoutingEvidenceExtractor,
    VisionLlmEvidenceExtractor,
)
from graph_mapper_agent.application.evidence_extraction.service import (
    EvidenceExtractionService,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimePort,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)


def build_evidence_extraction_service(
    *,
    pdf_reader: PyMuPdfGoalValidationPdfEvidenceReader | None = None,
    vision_runtime: LlmRuntimePort | None = None,
    ocr_runtime: LlmRuntimePort | None = None,
    ocr_runtime_config: LlmRuntimeConfig | None = None,
    coverage_runtime: LlmRuntimePort | None = None,
) -> EvidenceExtractionService:
    shared_pdf_reader = pdf_reader or PyMuPdfGoalValidationPdfEvidenceReader()
    return EvidenceExtractionService(
        extractor=RoutingEvidenceExtractor(
            pdf_extractor=PyMuPdfEvidenceExtractor(pdf_reader=shared_pdf_reader),
            html_extractor=HtmlEvidenceExtractor(),
            visual_extractor=(
                None
                if vision_runtime is None
                else VisionLlmEvidenceExtractor(llm_runtime=vision_runtime)
            ),
            ocr_extractor=(
                _build_ocr_extractor(
                    ocr_runtime=ocr_runtime,
                    ocr_runtime_config=ocr_runtime_config,
                )
            ),
        ),
        coverage_assessor=(
            None
            if coverage_runtime is None
            else LlmEvidenceCoverageAssessor(llm_runtime=coverage_runtime)
        ),
    )


def _build_ocr_extractor(
    *,
    ocr_runtime: LlmRuntimePort | None,
    ocr_runtime_config: LlmRuntimeConfig | None,
):
    if _looks_like_ollama_runtime(ocr_runtime_config):
        return OllamaOcrEvidenceExtractor(runtime_config=ocr_runtime_config)
    if _looks_like_glm_ocr_runtime(ocr_runtime_config):
        return GlmOcrEvidenceExtractor(runtime_config=ocr_runtime_config)
    if ocr_runtime is None:
        return None
    return OcrRuntimeEvidenceExtractor(llm_runtime=ocr_runtime)


def _looks_like_glm_ocr_runtime(config: LlmRuntimeConfig | None) -> bool:
    if config is None:
        return False
    model_name = str(config.default_model or "").strip().lower()
    return model_name in {"glm-ocr", "glm_ocr"} or model_name.startswith("glm-ocr")


def _looks_like_ollama_runtime(config: LlmRuntimeConfig | None) -> bool:
    if config is None:
        return False
    return str(config.backend or "").strip().lower() == "ollama"
