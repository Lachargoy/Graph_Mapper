from __future__ import annotations

import json
from typing import Any

from graph_mapper_agent.application.contracts.evidence_coverage_models import (
    EvidenceCoverageAssessmentOutput,
)
from graph_mapper_agent.application.evidence_extraction.models import (
    EvidenceCoverageAssessment,
    EvidenceExtractionRequest,
    EvidenceExtractionResult,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimePort,
    LlmRuntimeRequest,
)


class LlmEvidenceCoverageAssessor:
    def __init__(self, *, llm_runtime: LlmRuntimePort) -> None:
        self._llm_runtime = llm_runtime

    def assess_coverage(
        self,
        *,
        request: EvidenceExtractionRequest,
        result: EvidenceExtractionResult,
    ) -> EvidenceCoverageAssessment:
        response = self._llm_runtime.invoke(
            LlmRuntimeRequest(
                operation_name="graph_mapper_evidence_coverage",
                expected_output_name="graph_mapper_evidence_coverage",
                messages=(
                    {"role": "system", "content": _system_prompt()},
                    {
                        "role": "user",
                        "content": _user_content(request=request, result=result),
                    },
                ),
                metadata={
                    "prompt_version": "evidence_coverage_v1",
                    "structured_output_name": "graph_mapper_evidence_coverage",
                },
            )
        )
        payload = _extract_llm_json_payload(response)
        parsed = EvidenceCoverageAssessmentOutput.model_validate(payload)
        return EvidenceCoverageAssessment(
            coverage_status=parsed.coverage_status,  # type: ignore[arg-type]
            primary_content_detected=parsed.primary_content_detected,
            sufficiency_for_goal_validation=parsed.sufficiency_for_goal_validation,
            rationale=parsed.rationale,
            missing_content_signals=tuple(
                item.strip()
                for item in parsed.missing_content_signals
                if isinstance(item, str) and item.strip()
            ),
        )


def _system_prompt() -> str:
    return (
        "You are a web/document evidence coverage evaluator.\n"
        "Your task is not to decide the final goal, but to judge if the extraction captured enough main content from the resource.\n"
        "Evaluate whether the content appears partial, substantial, or complete.\n"
        "Do not use rigid local heuristics; make a semantic judgment on whether the extracted text seems to represent the main body of the resource.\n"
        "If there are only fragments, boilerplate, navigation, bodyless titles, or disconnected pieces, mark partial.\n"
        "If there appears to be a substantial main body but not necessarily complete, mark substantial.\n"
        "If the content appears to reasonably cover the full main resource, mark complete.\n"
        "Also indicate if it seems sufficient for goal validation.\n"
        "Respond ONLY with valid JSON."
    )


def _user_content(
    *,
    request: EvidenceExtractionRequest,
    result: EvidenceExtractionResult,
) -> str:
    items = []
    for item in result.items[:6]:
        items.append(
            {
                "evidence_kind": item.evidence_kind,
                "carrier": item.carrier,
                "page_number": item.page_number,
                "mime_type": item.mime_type,
                "text": (item.text or "")[:2500],
                "metadata": dict(item.metadata),
            }
        )
    payload = {
        "carrier": result.carrier,
        "source_url": request.artifact.source_url,
        "filename": request.artifact.filename,
        "media_type": request.artifact.media_type,
        "request_metadata": dict(request.metadata),
        "result_metadata": dict(result.metadata),
        "items": items,
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _extract_llm_json_payload(llm_response: Any) -> dict[str, object]:
    response_payload = getattr(getattr(llm_response, "interaction", None), "response", None)
    if not isinstance(response_payload, dict):
        raise TypeError("LlmRuntimeResponse.interaction.response debe ser dict[str, object]")
    for key in (
        "parsed_response",
        "output",
        "parsed_output",
        "structured_output",
        "json_output",
        "content",
        "text",
        "response_text",
        "completion",
    ):
        payload = _coerce_to_dict(response_payload.get(key))
        if payload is not None:
            return payload
    message = response_payload.get("message")
    if isinstance(message, dict):
        payload = _coerce_to_dict(message.get("content"))
        if payload is not None:
            return payload
    raise TypeError("No se pudo extraer payload de evidence coverage")


def _coerce_to_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return None
        return dict(parsed) if isinstance(parsed, dict) else None
    return None

