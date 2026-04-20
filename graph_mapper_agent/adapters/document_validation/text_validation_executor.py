from __future__ import annotations

from dataclasses import dataclass
import unicodedata

from graph_mapper_agent.application.evidence_extraction.models import (
    EvidenceArtifact,
    EvidenceExtractionRequest,
)
from graph_mapper_agent.application.evidence_extraction.service import (
    EvidenceExtractionService,
)
from graph_mapper_agent.application.document_validation.models import (
    TextPageEvidence,
)
from graph_mapper_agent.application.document_validation.pdf_evidence_reader_port import (
    PdfEvidenceReaderPort,
)
from graph_mapper_agent.application.document_validation.validation_pass_executor_port import (
    ValidationPassExecutorPort,
)
from graph_mapper_agent.application.document_validation.validation_models import (
    ValidationPass,
    ValidationRequest,
    ValidationResult,
)


@dataclass(frozen=True, slots=True)
class TextValidationExecutorSettings:
    min_chars_for_confident_text: int = 80


class DeterministicTextValidationPassExecutor(ValidationPassExecutorPort):
    def __init__(
        self,
        *,
        pdf_reader: PdfEvidenceReaderPort,
        evidence_extraction_service: EvidenceExtractionService | None = None,
        settings: TextValidationExecutorSettings | None = None,
    ) -> None:
        self._pdf_reader = pdf_reader
        self._evidence_extraction_service = evidence_extraction_service
        self._settings = settings or TextValidationExecutorSettings()

    def execute_pass(
        self,
        request: ValidationRequest,
        validation_pass: ValidationPass,
    ) -> ValidationResult:
        if validation_pass.strategy in {"first_page", "first_pages_window"}:
            return self._execute_text_window_pass(request, validation_pass)
        if validation_pass.strategy == "pattern_search":
            return self._execute_pattern_search_pass(request, validation_pass)
        if validation_pass.strategy == "visual_page":
            return self._execute_visual_page_pass(request, validation_pass)
        raise ValueError(f"Unsupported validation strategy: {validation_pass.strategy}")

    def _execute_text_window_pass(
        self,
        request: ValidationRequest,
        validation_pass: ValidationPass,
    ) -> ValidationResult:
        evidence_pages = self._read_text_evidence(
            request,
            validation_pass=validation_pass,
            for_pattern_search=False,
        )
        combined_text = "\n".join(page.text for page in evidence_pages if page.text).strip()
        page_count = len(evidence_pages)
        if not combined_text:
            return ValidationResult(
                status="needs_more_pages" if request.escalation_allowed else "inconclusive",
                validation_pass=validation_pass,
                rationale="No se extrajo texto util del rango solicitado.",
                evidence_summary="",
                pages_consumed=page_count,
                recommended_next_strategy="pattern_search" if request.pattern_hints else "visual_page",
                metadata={
                    "page_numbers": [page.page_number for page in evidence_pages],
                    "matched_condition_ids": (),
                },
            )
        if len(combined_text) >= self._settings.min_chars_for_confident_text:
            return ValidationResult(
                status="inconclusive",
                validation_pass=validation_pass,
                rationale="Se obtuvo texto suficiente para evaluar, pero aun no se resolvio la pregunta de validacion.",
                evidence_summary=combined_text[:500],
                pages_consumed=page_count,
                recommended_next_strategy="pattern_search" if request.pattern_hints else "visual_page",
                metadata={
                    "page_numbers": [page.page_number for page in evidence_pages],
                    "matched_condition_ids": (),
                },
            )
        return ValidationResult(
            status="needs_more_pages" if request.escalation_allowed else "inconclusive",
            validation_pass=validation_pass,
            rationale="El texto extraido fue demasiado corto para una validacion confiable.",
            evidence_summary=combined_text[:500],
            pages_consumed=page_count,
            recommended_next_strategy="pattern_search" if request.pattern_hints else "visual_page",
            metadata={
                "page_numbers": [page.page_number for page in evidence_pages],
                "matched_condition_ids": (),
            },
        )

    def _execute_pattern_search_pass(
        self,
        request: ValidationRequest,
        validation_pass: ValidationPass,
    ) -> ValidationResult:
        evidence_pages = self._read_text_evidence(
            request,
            validation_pass=validation_pass,
            for_pattern_search=True,
        )
        combined_text = _normalize_text("\n".join(page.text for page in evidence_pages if page.text))
        hints = tuple(_normalize_text(hint) for hint in validation_pass.pattern_hints if hint.strip())
        matched_hints = tuple(hint for hint in hints if hint in combined_text)
        if matched_hints:
            matched_condition_ids = _match_goal_conditions_from_text(request, combined_text)
            return ValidationResult(
                status="validated",
                validation_pass=validation_pass,
                rationale="Se encontraron patrones clave dentro del PDF.",
                evidence_summary=", ".join(matched_hints),
                pages_consumed=0,
                metadata={
                    "matched_hints": list(matched_hints),
                    "matched_condition_ids": matched_condition_ids,
                    "searched_pages": [page.page_number for page in evidence_pages],
                },
            )
        return ValidationResult(
            status="inconclusive",
            validation_pass=validation_pass,
            rationale="No se encontraron los patrones clave solicitados en el texto disponible.",
            evidence_summary=combined_text[:500],
            pages_consumed=0,
            recommended_next_strategy="visual_page",
            metadata={
                "matched_hints": [],
                "matched_condition_ids": (),
                "searched_pages": [page.page_number for page in evidence_pages],
            },
        )

    def _execute_visual_page_pass(
        self,
        request: ValidationRequest,
        validation_pass: ValidationPass,
    ) -> ValidationResult:
        if not self._can_read_pdf(request):
            return ValidationResult(
                status="inconclusive",
                validation_pass=validation_pass,
                rationale="No hay evidencia visual disponible para este artifact textual o HTML.",
                evidence_summary=(request.artifact.inline_text or "")[:500],
                pages_consumed=0,
            metadata={"inline_text_available": bool((request.artifact.inline_text or "").strip())},
        )
        page_number = validation_pass.page_numbers[0] if validation_pass.page_numbers else 1
        image = self._pdf_reader.render_page_image(request.artifact, page_number=page_number)
        return ValidationResult(
            status="inconclusive",
            validation_pass=validation_pass,
            rationale="Se genero evidencia visual puntual para una validacion posterior.",
            evidence_summary=f"visual_page:{page_number}",
            pages_consumed=0,
            metadata={
                "page_number": page_number,
                "mime_type": image.mime_type,
                "content_base64": image.content_base64,
                "matched_condition_ids": (),
            },
        )

    def _read_text_evidence(
        self,
        request: ValidationRequest,
        *,
        validation_pass: ValidationPass,
        for_pattern_search: bool,
    ) -> tuple[TextPageEvidence, ...]:
        inline_text = (request.artifact.inline_text or "").strip()
        if inline_text:
            return (TextPageEvidence(page_number=1, text=inline_text),)
        if not self._can_read_pdf(request):
            return ()
        if self._evidence_extraction_service is not None:
            extraction_result = self._evidence_extraction_service.extract(
                EvidenceExtractionRequest(
                    artifact=_to_evidence_artifact(request),
                    max_pages=request.max_pages if for_pattern_search else request.max_pages,
                    page_numbers=None if for_pattern_search else validation_pass.page_numbers,
                    include_text=True,
                    include_rendered_pages=False,
                    metadata={
                        "source": "goal_validation",
                        "strategy": validation_pass.strategy,
                    },
                )
            )
            extracted_pages = tuple(
                TextPageEvidence(
                    page_number=item.page_number or 1,
                    text=str(item.text or ""),
                )
                for item in extraction_result.items
                if item.evidence_kind in {"text_page", "inline_text"}
                and isinstance(item.text, str)
            )
            if extracted_pages:
                return extracted_pages
        if for_pattern_search:
            total_pages = self._pdf_reader.page_count(request.artifact)
            return self._pdf_reader.read_text_pages(
                request.artifact,
                max_pages=min(request.max_pages, total_pages),
            )
        return self._pdf_reader.read_text_pages(
            request.artifact,
            page_numbers=validation_pass.page_numbers,
        )

    @staticmethod
    def _can_read_pdf(request: ValidationRequest) -> bool:
        local_path = (request.artifact.local_path or "").strip().lower()
        return bool(local_path) and local_path.endswith(".pdf")


def _normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _to_evidence_artifact(request: ValidationRequest) -> EvidenceArtifact:
    artifact = request.artifact
    return EvidenceArtifact(
        local_path=artifact.local_path,
        source_url=artifact.source_url,
        media_type=artifact.media_type,
        filename=artifact.filename,
        inline_text=artifact.inline_text,
        screenshot_base64=artifact.screenshot_base64,
        screenshot_mime_type=artifact.screenshot_mime_type,
    )


def _match_goal_conditions_from_text(
    request: ValidationRequest,
    normalized_text: str,
) -> tuple[str, ...]:
    matched: list[str] = []
    for condition in request.goal_conditions:
        year_ok = condition.year is None or str(condition.year) in normalized_text
        if not year_ok:
            continue
        condition_text = _normalize_text(f"{condition.label} {condition.target_kind}")
        tokens = [token for token in condition_text.split() if len(token) >= 4]
        if tokens and any(token in normalized_text for token in tokens):
            matched.append(condition.condition_id)
    return tuple(matched)
