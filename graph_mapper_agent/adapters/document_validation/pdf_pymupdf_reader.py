from __future__ import annotations

import base64
from pathlib import Path

import fitz

from graph_mapper_agent.application.document_validation.models import (
    ArtifactReference,
    RenderedPageEvidence,
    TextPageEvidence,
)
from graph_mapper_agent.application.document_validation.pdf_evidence_reader_port import (
    PdfEvidenceReaderPort,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_AGENT_ROOT = REPO_ROOT / "aither" / "aither_agents"


class PyMuPdfPdfEvidenceReader(PdfEvidenceReaderPort):
    def page_count(self, artifact: ArtifactReference) -> int:
        path = self._resolve_path(artifact)
        with fitz.open(path) as doc:
            return len(doc)

    def read_text_pages(
        self,
        artifact: ArtifactReference,
        *,
        page_numbers: tuple[int, ...] | None = None,
        max_pages: int | None = None,
    ) -> tuple[TextPageEvidence, ...]:
        path = self._resolve_path(artifact)
        with fitz.open(path) as doc:
            selected_pages = self._selected_page_numbers(
                total_pages=len(doc),
                page_numbers=page_numbers,
                max_pages=max_pages,
            )
            evidence: list[TextPageEvidence] = []
            for page_number in selected_pages:
                page = doc.load_page(page_number - 1)
                text = page.get_text("text").strip()
                evidence.append(TextPageEvidence(page_number=page_number, text=text))
            return tuple(evidence)

    def render_page_image(
        self,
        artifact: ArtifactReference,
        *,
        page_number: int,
        dpi: int = 100,
    ) -> RenderedPageEvidence:
        if dpi <= 0:
            raise ValueError('dpi must be positive')
        path = self._resolve_path(artifact)
        with fitz.open(path) as doc:
            self._validate_page_number(page_number, total_pages=len(doc))
            pix = doc.load_page(page_number - 1).get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes('png')
        return RenderedPageEvidence(
            page_number=page_number,
            mime_type='image/png',
            content_base64=base64.b64encode(img_bytes).decode('utf-8'),
        )

    def _resolve_path(self, artifact: ArtifactReference) -> str:
        local_path = (artifact.local_path or "").strip()
        if not local_path:
            raise FileNotFoundError("Artifact local_path is empty")

        path = Path(local_path)
        candidates = [path]
        if not path.is_absolute():
            candidates.append(REPO_ROOT / path)
            candidates.append(LEGACY_AGENT_ROOT / path)

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        raise FileNotFoundError(f'Artifact not found: {artifact.local_path}')

    def _selected_page_numbers(
        self,
        *,
        total_pages: int,
        page_numbers: tuple[int, ...] | None,
        max_pages: int | None,
    ) -> tuple[int, ...]:
        if total_pages <= 0:
            return ()
        if page_numbers is not None and max_pages is not None:
            raise ValueError('page_numbers and max_pages are mutually exclusive')
        if page_numbers is not None:
            normalized = tuple(dict.fromkeys(page_numbers))
            for page_number in normalized:
                self._validate_page_number(page_number, total_pages=total_pages)
            return normalized
        limit = total_pages if max_pages is None else min(max_pages, total_pages)
        if limit < 0:
            raise ValueError('max_pages must be non-negative')
        return tuple(range(1, limit + 1))

    def _validate_page_number(self, page_number: int, *, total_pages: int) -> None:
        if page_number < 1 or page_number > total_pages:
            raise ValueError(
                f'page_number {page_number} out of range for document with {total_pages} pages'
            )
