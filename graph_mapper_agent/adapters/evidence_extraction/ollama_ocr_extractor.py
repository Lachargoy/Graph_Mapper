from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from graph_mapper_agent.application.evidence_extraction.models import (
    EvidenceExtractionRequest,
    EvidenceExtractionResult,
    EvidenceItem,
)
from graph_mapper_agent.application.evidence_extraction.ports import (
    OcrEvidenceExtractorPort,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)


class OllamaOcrEvidenceExtractor(OcrEvidenceExtractorPort):
    def __init__(self, *, runtime_config: LlmRuntimeConfig) -> None:
        self._runtime_config = runtime_config.resolve_defaults()

    def extract_ocr(
        self,
        request: EvidenceExtractionRequest,
    ) -> EvidenceExtractionResult:
        image_base64 = _resolve_ollama_image_base64(request)
        ocr_mode = _resolve_ollama_ocr_mode(request)
        if image_base64 is None:
            return EvidenceExtractionResult(
                carrier=request.artifact.infer_carrier(),
                items=(),
                metadata={
                    "source": "ollama_ocr",
                    "status": "no_visual_input",
                    "ocr_mode": ocr_mode,
                },
            )

        try:
            response_payload = _invoke_ollama_ocr(
                runtime_config=self._runtime_config,
                image_base64=image_base64,
                ocr_mode=ocr_mode,
            )
        except Exception as exc:
            return EvidenceExtractionResult(
                carrier=request.artifact.infer_carrier(),
                items=(),
                metadata={
                    "source": "ollama_ocr",
                    "status": "request_error",
                    "ocr_mode": ocr_mode,
                    "error_class": type(exc).__name__,
                    "error_message": str(exc) or repr(exc),
                },
            )

        text = _extract_ollama_response_text(response_payload)
        if not text:
            return EvidenceExtractionResult(
                carrier=request.artifact.infer_carrier(),
                items=(),
                metadata={
                    "source": "ollama_ocr",
                    "status": "empty_response",
                    "model": self._runtime_config.default_model,
                    "ocr_mode": ocr_mode,
                },
            )

        carrier = request.artifact.infer_carrier()
        return EvidenceExtractionResult(
            carrier=carrier,
            items=(
                EvidenceItem(
                    evidence_kind="inline_text",
                    carrier=carrier,
                    text=text,
                    metadata={
                        "extracted_by": "ollama_ocr",
                        "content_format": "text",
                        "model": self._runtime_config.default_model,
                        "ocr_mode": ocr_mode,
                    },
                ),
            ),
            metadata={
                "source": "ollama_ocr",
                "model": self._runtime_config.default_model,
                "ocr_mode": ocr_mode,
                "done": response_payload.get("done"),
                "prompt_eval_count": response_payload.get("prompt_eval_count"),
                "eval_count": response_payload.get("eval_count"),
            },
        )


def _invoke_ollama_ocr(
    *,
    runtime_config: LlmRuntimeConfig,
    image_base64: str,
    ocr_mode: str,
) -> dict[str, Any]:
    base_url = str(runtime_config.base_url or "").rstrip("/")
    if not base_url:
        raise ValueError("Ollama OCR requires base_url.")
    endpoint = f"{base_url}/api/chat"
    payload = {
        "model": str(runtime_config.default_model or "").strip(),
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": _ollama_ocr_prompt_for_mode(ocr_mode),
                "images": [image_base64],
            },
        ],
    }
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    timeout_seconds = int(runtime_config.timeout_seconds or 180)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama OCR HTTP {exc.code}: {body_text}") from exc
    except URLError as exc:
        raise RuntimeError(f"Ollama OCR connection error: {exc.reason}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama OCR returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Ollama OCR returned an unstructured response.")
    return parsed


def _extract_ollama_response_text(payload: dict[str, Any]) -> str | None:
    message = payload.get("message")
    if isinstance(message, dict):
        content = str(message.get("content") or "").strip()
        if content:
            return content
    response = str(payload.get("response") or "").strip()
    return response or None


def _resolve_ollama_image_base64(request: EvidenceExtractionRequest) -> str | None:
    artifact = request.artifact
    screenshot_base64 = str(artifact.screenshot_base64 or "").strip()
    if screenshot_base64:
        return screenshot_base64

    local_path = str(artifact.local_path or "").strip()
    media_type = str(artifact.media_type or "").strip().lower()
    if local_path and media_type.startswith("image/"):
        path = Path(local_path)
        if path.exists() and path.is_file():
            return base64.b64encode(path.read_bytes()).decode("ascii")
    return None


def _resolve_ollama_ocr_mode(request: EvidenceExtractionRequest) -> str:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    raw_mode = str(
        metadata.get("ocr_mode")
        or metadata.get("ollama_ocr_mode")
        or "text"
    ).strip().lower()
    if raw_mode in {"text", "text_recognition", "text recognition"}:
        return "text"
    if raw_mode in {"table", "table_recognition", "table recognition"}:
        return "table"
    if raw_mode in {"figure", "figure_recognition", "figure recognition"}:
        return "figure"
    return "text"


def _ollama_ocr_prompt_for_mode(ocr_mode: str) -> str:
    if ocr_mode == "table":
        return "Table Recognition:"
    if ocr_mode == "figure":
        return "Figure Recognition:"
    return "Text Recognition:"
