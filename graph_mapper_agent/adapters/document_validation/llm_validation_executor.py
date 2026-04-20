from __future__ import annotations
#graph_mapper_agent/adapters/document_validation/llm_validation_executor.py
from datetime import datetime
from dataclasses import dataclass, replace
from typing import Any, Literal

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
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeError,
    LlmRuntimePort,
    LlmRuntimeRequest,
)
from graph_mapper_agent.ledger.application.invoke_llm_with_ledger_use_case import (
    InvokeLlmWithLedgerUseCase,
)
from graph_mapper_agent.ledger.domain.actor_kind import ActorKind
from graph_mapper_agent.ledger.domain.run_correlation import (
    RunCorrelation,
)
from graph_mapper_agent.ledger.domain.target_ref import TargetRef


RecommendedNextStrategy = Literal[
    "first_page",
    "first_pages_window",
    "pattern_search",
    "visual_page",
]


@dataclass(frozen=True, slots=True)
class LlmValidationExecutorSettings:
    prompt_version: str = "document_validation_v3_en"
    image_detail: str = "auto"
    supports_vision: bool = False


class LlmBackedValidationPassExecutor(ValidationPassExecutorPort):
    def __init__(
        self,
        *,
        pdf_reader: PdfEvidenceReaderPort,
        evidence_extraction_service: EvidenceExtractionService | None = None,
        llm_runtime: LlmRuntimePort,
        invoke_llm_use_case: InvokeLlmWithLedgerUseCase | None = None,
        ledger_run: RunCorrelation | None = None,
        ledger_actor: ActorKind | None = None,
        ledger_target: TargetRef | None = None,
        settings: LlmValidationExecutorSettings | None = None,
    ) -> None:
        self._pdf_reader = pdf_reader
        self._evidence_extraction_service = evidence_extraction_service
        self._llm_runtime = llm_runtime
        self._invoke_llm_use_case = invoke_llm_use_case
        self._ledger_run = ledger_run
        self._ledger_actor = ledger_actor
        self._ledger_target = ledger_target
        self._settings = settings or LlmValidationExecutorSettings()

    def execute_pass(
        self,
        request: ValidationRequest,
        validation_pass: ValidationPass,
    ) -> ValidationResult:
        if validation_pass.strategy == "visual_page":
            return self._execute_visual_pass(request, validation_pass)
        return self._execute_textual_pass(request, validation_pass)

    def _execute_textual_pass(
        self,
        request: ValidationRequest,
        validation_pass: ValidationPass,
    ) -> ValidationResult:
        request = self._with_pending_conditions_only(request)
        if not request.goal_conditions:
            return ValidationResult(
                status="validated",
                validation_pass=validation_pass,
                rationale="There are no pending goal_conditions for this evidence.",
                evidence_summary="",
                pages_consumed=0,
                metadata={
                    "page_numbers": (),
                    "matched_condition_ids": (),
                    "skipped_no_pending_conditions": True,
                },
            )

        evidence_pages = self._read_text_evidence(request, validation_pass)

        combined_text = "\n".join(page.text for page in evidence_pages if page.text).strip()
        user_text = self._text_user_content(
            request,
            validation_pass,
            evidence_pages,
            combined_text,
        )

        user_content: str | list[dict[str, object]] = user_text
        screenshot_base64 = (request.artifact.screenshot_base64 or "").strip()
        screenshot_mime_type = (request.artifact.screenshot_mime_type or "").strip() or "image/png"

        if screenshot_base64 and self._settings.supports_vision:
            user_content = [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{screenshot_mime_type};base64,{screenshot_base64}",
                        "detail": self._settings.image_detail,
                    },
                },
            ]

        try:
            payload = self._invoke_llm(
                messages=(
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": user_content},
                )
            )
        except LlmRuntimeError as error:
            if not (
                isinstance(user_content, list)
                and self._should_retry_without_images(error)
            ):
                raise
            payload = self._invoke_llm(
                messages=(
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": user_text},
                )
            )

        payload = self._normalize_validation_payload(payload)

        return ValidationResult(
            status=payload["status"],
            validation_pass=validation_pass,
            rationale=str(payload["rationale"]),
            evidence_summary=str(payload.get("evidence_summary") or ""),
            pages_consumed=len(evidence_pages) if validation_pass.strategy != "pattern_search" else 0,
            recommended_next_strategy=payload.get("recommended_next_strategy"),
            metadata={
                "page_numbers": [page.page_number for page in evidence_pages],
                "matched_condition_ids": tuple(
                    str(item)
                    for item in (payload.get("matched_condition_ids") or [])
                    if str(item).strip()
                ),
                "validated_document_family": payload.get("validated_document_family"),
                "validated_year": payload.get("validated_year"),
                "validated_carrier": payload.get("validated_carrier"),
                "carrier_requirement_assessment": payload.get("carrier_requirement_assessment"),
                "validation_scope_assessment": payload.get("validation_scope_assessment"),
                "llm_validation": payload,
            },
        )

    def _execute_visual_pass(
        self,
        request: ValidationRequest,
        validation_pass: ValidationPass,
    ) -> ValidationResult:
        request = self._with_pending_conditions_only(request)
        if not request.goal_conditions:
            return ValidationResult(
                status="validated",
                validation_pass=validation_pass,
                rationale="There are no pending goal_conditions for this evidence.",
                evidence_summary="",
                pages_consumed=0,
                metadata={
                    "matched_condition_ids": (),
                    "skipped_no_pending_conditions": True,
                },
            )

        if not self._settings.supports_vision:
            return ValidationResult(
                status="inconclusive",
                validation_pass=validation_pass,
                rationale="The current runtime does not support visual validation.",
                evidence_summary=(request.artifact.inline_text or "")[:500],
                pages_consumed=0,
                recommended_next_strategy="first_page",
                metadata={
                    "vision_supported": False,
                    "inline_text_available": bool((request.artifact.inline_text or "").strip()),
                },
            )

        if not self._can_render_visual(request):
            return ValidationResult(
                status="inconclusive",
                validation_pass=validation_pass,
                rationale="There is no renderable page for visual validation; only inline textual evidence is available.",
                evidence_summary=(request.artifact.inline_text or "")[:500],
                pages_consumed=0,
                metadata={
                    "vision_supported": True,
                    "inline_text_available": bool((request.artifact.inline_text or "").strip()),
                },
            )

        page_number = validation_pass.page_numbers[0] if validation_pass.page_numbers else 1
        image = self._pdf_reader.render_page_image(request.artifact, page_number=page_number)

        visual_user_text = self._visual_user_content(request, validation_pass, page_number)
        try:
            payload = self._invoke_llm(
                messages=(
                    {"role": "system", "content": self._system_prompt()},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": visual_user_text,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{image.mime_type};base64,{image.content_base64}",
                                    "detail": self._settings.image_detail,
                                },
                            },
                        ],
                    },
                )
            )
        except LlmRuntimeError as error:
            if not self._should_retry_without_images(error):
                raise
            payload = self._invoke_llm(
                messages=(
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": visual_user_text},
                )
            )

        payload = self._normalize_validation_payload(payload)

        return ValidationResult(
            status=payload["status"],
            validation_pass=validation_pass,
            rationale=str(payload["rationale"]),
            evidence_summary=str(payload.get("evidence_summary") or ""),
            pages_consumed=0,
            recommended_next_strategy=payload.get("recommended_next_strategy"),
            metadata={
                "page_number": page_number,
                "mime_type": image.mime_type,
                "content_base64": image.content_base64,
                "vision_supported": True,
                "matched_condition_ids": tuple(
                    str(item)
                    for item in (payload.get("matched_condition_ids") or [])
                    if str(item).strip()
                ),
                "validated_document_family": payload.get("validated_document_family"),
                "validated_year": payload.get("validated_year"),
                "validated_carrier": payload.get("validated_carrier"),
                "carrier_requirement_assessment": payload.get("carrier_requirement_assessment"),
                "validation_scope_assessment": payload.get("validation_scope_assessment"),
                "llm_validation": payload,
            },
        )

    def _read_text_evidence(
        self,
        request: ValidationRequest,
        validation_pass: ValidationPass,
    ) -> tuple[TextPageEvidence, ...]:
        inline_text = (request.artifact.inline_text or "").strip()

        # Prefer PDF text extraction first; use inline_text only as fallback.
        if self._can_read_pdf(request):
            if self._evidence_extraction_service is not None:
                extraction_result = self._evidence_extraction_service.extract(
                    EvidenceExtractionRequest(
                        artifact=_to_evidence_artifact(request),
                        max_pages=request.max_pages,
                        page_numbers=None
                        if validation_pass.strategy == "pattern_search"
                        else validation_pass.page_numbers,
                        include_text=True,
                        include_rendered_pages=False,
                        metadata={
                            "source": "document_validation_llm",
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

            if validation_pass.strategy == "pattern_search":
                pages = self._pdf_reader.read_text_pages(
                    request.artifact,
                    max_pages=request.max_pages,
                )
            else:
                pages = self._pdf_reader.read_text_pages(
                    request.artifact,
                    page_numbers=validation_pass.page_numbers,
                )

            if pages:
                return pages

        if inline_text:
            return (TextPageEvidence(page_number=1, text=inline_text),)

        return ()

    @staticmethod
    def _can_read_pdf(request: ValidationRequest) -> bool:
        local_path = (request.artifact.local_path or "").strip().lower()
        return bool(local_path) and local_path.endswith(".pdf")

    @staticmethod
    def _can_render_visual(request: ValidationRequest) -> bool:
        local_path = (request.artifact.local_path or "").strip().lower()
        return bool(local_path) and local_path.endswith(".pdf")

    def _invoke_llm(self, *, messages: tuple[dict[str, Any], ...]) -> dict[str, Any]:
        llm_request = LlmRuntimeRequest(
            operation_name="goal_validation",
            messages=messages,
            expected_output_name="goal_validation_output",
            metadata={
                "prompt_version": self._settings.prompt_version,
                "structured_output_name": "goal_validation_output",
            },
        )

        if (
            self._invoke_llm_use_case is not None
            and self._ledger_run is not None
            and self._ledger_actor is not None
        ):
            response = self._invoke_llm_use_case.execute(
                run=self._ledger_run,
                actor=self._ledger_actor,
                request=llm_request,
                target=self._ledger_target,
                metadata={
                    "prompt_version": self._settings.prompt_version,
                    "structured_output_name": "goal_validation_output",
                },
            )
        else:
            response = self._llm_runtime.invoke(llm_request)

        interaction = getattr(response, "interaction", None)
        if interaction is None:
            raise TypeError("LlmRuntimeResponse does not contain interaction")

        validation = getattr(interaction, "validation", None)
        if not isinstance(validation, dict):
            raise TypeError("LlmRuntimeResponse.interaction.validation must be dict[str, object]")

        payload = validation.get("parsed_response")
        if not isinstance(payload, dict):
            raise TypeError(
                "LlmRuntimeResponse.interaction.validation.parsed_response must be dict[str, object]"
            )

        return payload

    @staticmethod
    def _should_retry_without_images(error: LlmRuntimeError) -> bool:
        text = f"{error.error_class} {error.message}".lower()
        return (
            "image input" in text
            or "support image" in text
            or "supports image" in text
            or "vision not found" in text
            or "vision unsupported" in text
            or ("vision" in text and "not found" in text)
        )

    @staticmethod
    def _normalize_validation_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)

        raw_strategy = normalized.get("recommended_next_strategy")
        if isinstance(raw_strategy, str):
            candidate = raw_strategy.strip().lower()
            if candidate in {"", "null", "none", "n/a", "na"}:
                normalized["recommended_next_strategy"] = None
            elif candidate in {
                "first_page",
                "first_pages_window",
                "pattern_search",
                "visual_page",
            }:
                normalized["recommended_next_strategy"] = candidate

        raw_status = normalized.get("status")
        if isinstance(raw_status, str):
            normalized["status"] = raw_status.strip().lower()

        return normalized

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are a bounded goal-condition validator. "
            f"Current system date: {datetime.now().astimezone().strftime('%Y-%m-%d')}. "
            "You receive local evidence and one or more pending goal_conditions. "
            "Your task is to decide whether the current evidence satisfies any condition, contradicts it, or remains inconclusive. "
            "Do not browse or explore freely; evaluate only the evidence provided. "

            "The unit of validation is not the file format by itself, but whether the current evidence satisfies one or more pending goal_conditions. "
            "Always distinguish between: "
            "(a) the requested document family or deliverable type, "
            "(b) the visible carrier or format of the current evidence (pdf, terminal html, inline text, image, etc.), "
            "and (c) whether the current node is the final document or only a hub, listing, calendar, or intermediate page. "

            "Do not close conditions from indexes, hubs, listings, calendars, or intermediate pages, "
            "unless the visible evidence is clearly the final document or a terminal HTML page that already contains the substantive content of the deliverable. "

            "If the evidence looks like an index, hub, or intermediate page, explicitly set validation_scope_assessment=index_or_hub "
            "and explain that validation should not be closed from here yet. "

            "If the local evidence is insufficient even though the node looks promising, use validation_scope_assessment=insufficient_local_evidence. "

            "If the visible evidence already clearly corresponds to the final deliverable in HTML or inline text, "
            "use validation_scope_assessment=final_document_inline. "

            "If the visible evidence already clearly corresponds to the final deliverable in a final artifact or file, "
            "use validation_scope_assessment=final_document_artifact. "

            "If the visible evidence already clearly corresponds to the requested final deliverable, respond with status=validated "
            "and return matched_condition_ids. Do not use inconclusive out of caution when the match is direct. "

            "If the visible evidence clearly matches the correct document family and year, "
            "but the carrier does not match a strict carrier requirement, use validation_scope_assessment=carrier_mismatch_but_final_content. "
            "In that case do not mark it as validated unless the condition allows that carrier. "

            "Do not assume that target_kind=pdf_document automatically means strict PDF carrier. "
            "Only treat the carrier as strictly required if the condition says strict_carrier_required=true, "
            "or if preferred_carrier and accepted_carriers define a clearly closed restriction. "

            "If the visible year, document type, or scope contradict the condition, do not validate it. "
            "Do not rely only on filename or URL when the visible evidence does not support that assumption. "
            "Prioritize matched_condition_ids whenever the evidence is strong enough to support a specific condition. "
            "If you cannot support any specific condition, respond with status=inconclusive or status=needs_more_pages. "

            "recommended_next_strategy rules: "
            "You must output either one of these exact values: "
            "'first_page', 'first_pages_window', 'pattern_search', 'visual_page', "
            "or JSON null if no next strategy is needed. "
            "Never output the string 'null'. Never output an empty string. "

            "Respond only with structured output."
        )

    @staticmethod
    def _text_user_content(
        request: ValidationRequest,
        validation_pass: ValidationPass,
        evidence_pages: tuple[Any, ...],
        combined_text: str,
    ) -> str:
        page_numbers = [page.page_number for page in evidence_pages]
        conditions_text = LlmBackedValidationPassExecutor._goal_conditions_text(request)
        metadata_lines = LlmBackedValidationPassExecutor._metadata_lines(request)

        return (
            f"goal_validation_task: {request.validation_goal}\n"
            f"strategy: {validation_pass.strategy}\n"
            f"reason: {validation_pass.reason}\n"
            f"page_numbers: {page_numbers}\n"
            f"pattern_hints: {list(validation_pass.pattern_hints)}\n"
            f"node_context:\n{metadata_lines}\n"
            f"goal_conditions:\n{conditions_text}\n"
            "Interpret the goal_conditions against the currently visible evidence only.\n"
            "Important: document_family defines the deliverable type; preferred_carrier and accepted_carriers describe carrier preference or restriction.\n"
            "Do not assume strict PDF carrier unless strict_carrier_required=true or accepted_carriers clearly exclude html_inline and text_inline.\n"
            "If the currently visible evidence clearly already contains the final document in terminal HTML or inline text, you may validate it even if it is not a downloaded PDF, as long as the condition allows that carrier.\n"
            "If the current evidence only lists or distributes child documents, do not validate from here; use validation_scope_assessment=index_or_hub.\n"
            "If the current evidence already is the requested final document, respond with status=validated and return matched_condition_ids.\n"
            "If the evidence matches document family and year but fails only because of a strict carrier requirement, do not mark it as validated; use carrier_mismatch_but_final_content.\n"
            "If one or more conditions are satisfied, return matched_condition_ids.\n"
            "If the evidence is not sufficient to support any condition, or it is only a hub/intermediate page, respond with status=inconclusive or status=needs_more_pages as appropriate.\n"
            "recommended_next_strategy must be one of: first_page, first_pages_window, pattern_search, visual_page, or JSON null if not needed.\n"
            "Never output the string 'null'.\n"
            f"evidence_text:\n{combined_text}"
        )

    @staticmethod
    def _visual_user_content(
        request: ValidationRequest,
        validation_pass: ValidationPass,
        page_number: int,
    ) -> str:
        conditions_text = LlmBackedValidationPassExecutor._goal_conditions_text(request)
        metadata_lines = LlmBackedValidationPassExecutor._metadata_lines(request)

        return (
            f"goal_validation_task: {request.validation_goal}\n"
            f"strategy: {validation_pass.strategy}\n"
            f"reason: {validation_pass.reason}\n"
            f"page_number: {page_number}\n"
            f"node_context:\n{metadata_lines}\n"
            f"goal_conditions:\n{conditions_text}\n"
            "Evaluate the image of this page and decide whether the visible evidence satisfies any pending goal_condition.\n"
            "Important: document_family defines the deliverable type; preferred_carrier and accepted_carriers describe carrier preference or restriction.\n"
            "Do not assume strict PDF carrier unless strict_carrier_required=true or accepted_carriers clearly exclude html_inline and text_inline.\n"
            "If the image clearly shows the final document in terminal HTML, inline text, or a final artifact, you may validate it if the condition allows that carrier.\n"
            "If the image matches the correct document family and year but fails only because of strict carrier requirements, use carrier_mismatch_but_final_content.\n"
            "If the image looks like an index, hub, or insufficient evidence, say so explicitly in validation_scope_assessment.\n"
            "If the image already clearly shows the final deliverable, respond with status=validated and return matched_condition_ids.\n"
            "If applicable, return matched_condition_ids.\n"
            "recommended_next_strategy must be one of: first_page, first_pages_window, pattern_search, visual_page, or JSON null if not needed.\n"
            "Never output the string 'null'."
        )

    @staticmethod
    def _goal_conditions_text(request: ValidationRequest) -> str:
        lines: list[str] = []
        for condition in request.goal_conditions:
            document_family = getattr(condition, "document_family", None) or getattr(condition, "target_kind", None)
            preferred_carrier = getattr(condition, "preferred_carrier", None)
            accepted_carriers = tuple(getattr(condition, "accepted_carriers", ()) or ())
            strict_carrier_required = bool(getattr(condition, "strict_carrier_required", False))

            lines.append(
                f"- condition_id={condition.condition_id} | "
                f"label={condition.label} | "
                f"target_kind={condition.target_kind} | "
                f"document_family={document_family} | "
                f"year={condition.year} | "
                f"requiredness={condition.requiredness} | "
                f"preferred_carrier={preferred_carrier} | "
                f"accepted_carriers={list(accepted_carriers)} | "
                f"strict_carrier_required={strict_carrier_required}"
            )
        return "\n".join(lines) or "- none"

    @staticmethod
    def _metadata_lines(request: ValidationRequest) -> str:
        return "\n".join(
            f"- {key}={value}"
            for key, value in sorted((request.metadata or {}).items())
            if value is not None
        ) or "- none"

    @staticmethod
    def _with_pending_conditions_only(request: ValidationRequest) -> ValidationRequest:
        pending_conditions = tuple(
            condition
            for condition in request.goal_conditions
            if getattr(condition, "status", "pending") != "satisfied"
        )
        if pending_conditions == tuple(request.goal_conditions):
            return request
        return replace(request, goal_conditions=pending_conditions)


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
