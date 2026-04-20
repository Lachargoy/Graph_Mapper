from __future__ import annotations

from graph_mapper_agent.adapters.goal_validation.pdf_pymupdf_reader import (
    PyMuPdfGoalValidationPdfEvidenceReader,
)
from graph_mapper_agent.application.evidence_extraction.models import (
    EvidenceArtifact,
    EvidenceExtractionRequest,
    EvidenceExtractionResult,
    EvidenceItem,
)
from graph_mapper_agent.application.evidence_extraction.ports import (
    EvidenceExtractorPort,
)
from graph_mapper_agent.application.document_validation.models import (
    ArtifactReference,
)


class PyMuPdfEvidenceExtractor(EvidenceExtractorPort):
    def __init__(self, *, pdf_reader: PyMuPdfGoalValidationPdfEvidenceReader | None = None) -> None:
        self._pdf_reader = pdf_reader or PyMuPdfGoalValidationPdfEvidenceReader()

    def extract(self, request: EvidenceExtractionRequest) -> EvidenceExtractionResult:
        artifact = request.artifact
        carrier = artifact.infer_carrier()

        if artifact.inline_text and request.include_text:
            return EvidenceExtractionResult(
                carrier=carrier,
                items=(
                    EvidenceItem(
                        evidence_kind="inline_text",
                        carrier=carrier,
                        text=artifact.inline_text,
                    ),
                ),
                metadata={"source": "inline"},
            )

        if carrier != "pdf":
            return EvidenceExtractionResult(
                carrier=carrier,
                items=(),
                metadata={"source": "unsupported_for_pymupdf"},
            )

        pdf_artifact = ArtifactReference(
            local_path=artifact.local_path,
            source_url=artifact.source_url,
            media_type=artifact.media_type,
            filename=artifact.filename,
            inline_text=artifact.inline_text,
            screenshot_base64=artifact.screenshot_base64,
            screenshot_mime_type=artifact.screenshot_mime_type,
        )

        items: list[EvidenceItem] = []
        if request.include_text:
            pages = self._pdf_reader.read_text_pages(
                pdf_artifact,
                page_numbers=request.page_numbers,
                max_pages=request.max_pages if request.page_numbers is None else None,
            )
            for page in pages:
                items.append(
                    EvidenceItem(
                        evidence_kind="text_page",
                        carrier="pdf",
                        page_number=page.page_number,
                        text=page.text,
                    )
                )

        if request.include_rendered_pages:
            page_numbers = request.page_numbers or tuple(range(1, request.max_pages + 1))
            for page_number in page_numbers:
                rendered = self._pdf_reader.render_page_image(
                    pdf_artifact,
                    page_number=page_number,
                )
                items.append(
                    EvidenceItem(
                        evidence_kind="rendered_page",
                        carrier="pdf",
                        page_number=rendered.page_number,
                        mime_type=rendered.mime_type,
                        content_base64=rendered.content_base64,
                    )
                )

        return EvidenceExtractionResult(
            carrier="pdf",
            items=tuple(items),
            metadata={"source": "pymupdf"},
        )
