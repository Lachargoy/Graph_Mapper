from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from graph_mapper_agent.application.evidence_extraction.models import (
    EvidenceExtractionRequest,
    EvidenceExtractionResult,
    EvidenceItem,
)
from graph_mapper_agent.application.evidence_extraction.ports import (
    OcrEvidenceExtractorPort,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimePort,
    LlmRuntimeRequest,
)


class OcrRuntimeEvidenceExtractor(OcrEvidenceExtractorPort):
    def __init__(self, *, llm_runtime: LlmRuntimePort) -> None:
        self._llm_runtime = llm_runtime

    def extract_ocr(
        self,
        request: EvidenceExtractionRequest,
    ) -> EvidenceExtractionResult:
        data_url = _resolve_image_data_url(request)
        if data_url is None:
            return EvidenceExtractionResult(
                carrier=request.artifact.infer_carrier(),
                items=(),
                metadata={"source": "ocr_runtime", "status": "no_visual_input"},
            )

        response = self._llm_runtime.invoke(
            LlmRuntimeRequest(
                operation_name="evidence_extraction_ocr",
                messages=(
                    {
                        "role": "system",
                        "content": (
                            "You are a strict OCR extractor. "
                            "Your task is to faithfully transcribe the visible text from the image. "
                            "Do not summarize or invent content. Preserve useful structure such as titles, dates, lists, and headings when possible."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Apply OCR to this image and return only the useful extracted text. "
                                    "Prioritize accuracy, dates, proper names, documentary identifiers, and legible content."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": data_url,
                                },
                            },
                        ],
                    },
                ),
                metadata={
                    **dict(request.metadata),
                    "evidence_extraction_kind": "ocr",
                },
            )
        )
        text = _extract_response_text(response)
        if not text:
            return EvidenceExtractionResult(
                carrier=request.artifact.infer_carrier(),
                items=(),
                metadata={"source": "ocr_runtime", "status": "empty_response"},
            )

        carrier = request.artifact.infer_carrier()
        return EvidenceExtractionResult(
            carrier=carrier,
            items=(
                EvidenceItem(
                    evidence_kind="inline_text",
                    carrier=carrier,
                    text=text,
                    metadata={"extracted_by": "ocr_runtime"},
                ),
            ),
            metadata={"source": "ocr_runtime"},
        )


def _resolve_image_data_url(request: EvidenceExtractionRequest) -> str | None:
    artifact = request.artifact
    screenshot_base64 = str(artifact.screenshot_base64 or "").strip()
    screenshot_mime = str(artifact.screenshot_mime_type or "").strip() or "image/png"
    if screenshot_base64:
        return f"data:{screenshot_mime};base64,{screenshot_base64}"

    local_path = str(artifact.local_path or "").strip()
    media_type = str(artifact.media_type or "").strip() or _mime_from_path(local_path)
    if local_path and media_type.startswith("image/"):
        path = Path(local_path)
        if path.exists() and path.is_file():
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:{media_type};base64,{encoded}"
    return None


def _mime_from_path(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".jpg") or lower.endswith(".jpeg"):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"


def _extract_response_text(response: Any) -> str | None:
    interaction = getattr(response, "interaction", None)
    payload = None if interaction is None else getattr(interaction, "response", None)
    if not isinstance(payload, dict):
        return None

    for key in ("text", "response_text", "content", "completion"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text") or "").strip()
                    if text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)

    return None
