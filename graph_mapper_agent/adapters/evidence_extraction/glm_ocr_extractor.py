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


class GlmOcrEvidenceExtractor(OcrEvidenceExtractorPort):
    def __init__(self, *, runtime_config: LlmRuntimeConfig) -> None:
        self._runtime_config = runtime_config.resolve_defaults()

    def extract_ocr(
        self,
        request: EvidenceExtractionRequest,
    ) -> EvidenceExtractionResult:
        file_payload = _resolve_glm_ocr_file(request)
        if file_payload is None:
            return EvidenceExtractionResult(
                carrier=request.artifact.infer_carrier(),
                items=(),
                metadata={"source": "glm_ocr", "status": "no_supported_input"},
            )

        try:
            response_payload = _invoke_glm_ocr(
                runtime_config=self._runtime_config,
                file_payload=file_payload,
                request=request,
            )
        except Exception as exc:
            return EvidenceExtractionResult(
                carrier=request.artifact.infer_carrier(),
                items=(),
                metadata={
                    "source": "glm_ocr",
                    "status": "request_error",
                    "error_class": type(exc).__name__,
                    "error_message": str(exc) or repr(exc),
                },
            )

        markdown_text = str(response_payload.get("md_results") or "").strip()
        if not markdown_text:
            return EvidenceExtractionResult(
                carrier=request.artifact.infer_carrier(),
                items=(),
                metadata={
                    "source": "glm_ocr",
                    "status": "empty_response",
                    "layout_details": response_payload.get("layout_details"),
                    "data_info": response_payload.get("data_info"),
                },
            )

        return EvidenceExtractionResult(
            carrier=request.artifact.infer_carrier(),
            items=(
                EvidenceItem(
                    evidence_kind="inline_text",
                    carrier=request.artifact.infer_carrier(),
                    text=markdown_text,
                    metadata={
                        "extracted_by": "glm_ocr",
                        "content_format": "markdown",
                        "layout_details": response_payload.get("layout_details"),
                        "layout_visualization": response_payload.get("layout_visualization"),
                        "data_info": response_payload.get("data_info"),
                        "request_id": response_payload.get("request_id"),
                    },
                ),
            ),
            metadata={
                "source": "glm_ocr",
                "model": response_payload.get("model") or self._runtime_config.default_model,
                "request_id": response_payload.get("request_id"),
                "data_info": response_payload.get("data_info"),
                "usage": response_payload.get("usage"),
            },
        )


def _invoke_glm_ocr(
    *,
    runtime_config: LlmRuntimeConfig,
    file_payload: str,
    request: EvidenceExtractionRequest,
) -> dict[str, Any]:
    base_url = str(runtime_config.base_url or "").rstrip("/")
    if not base_url:
        raise ValueError("GLM-OCR requires base_url.")
    api_key = str(runtime_config.api_key or "").strip()
    if not api_key:
        raise ValueError("GLM-OCR requires api_key.")

    endpoint = (
        base_url[:-3] + "/layout_parsing"
        if base_url.endswith("/v1")
        else base_url + "/layout_parsing"
    )
    body: dict[str, Any] = {
        "model": str(runtime_config.default_model or "glm-ocr"),
        "file": file_payload,
        "need_layout_visualization": False,
        "return_crop_images": False,
    }
    max_pages = max(int(request.max_pages or 1), 1)
    artifact_path = str(request.artifact.local_path or "").lower()
    if artifact_path.endswith(".pdf"):
        body["start_page_id"] = 1
        body["end_page_id"] = max_pages

    payload = json.dumps(body).encode("utf-8")
    http_request = Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    timeout_seconds = int(runtime_config.timeout_seconds or 180)
    try:
        with urlopen(http_request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GLM-OCR HTTP {exc.code}: {body_text}") from exc
    except URLError as exc:
        raise RuntimeError(f"GLM-OCR connection error: {exc.reason}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GLM-OCR returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("GLM-OCR returned an unstructured response.")
    return parsed


def _resolve_glm_ocr_file(request: EvidenceExtractionRequest) -> str | None:
    artifact = request.artifact
    source_url = str(artifact.source_url or "").strip()
    if source_url.lower().startswith(("http://", "https://")):
        return source_url

    local_path = str(artifact.local_path or "").strip()
    if local_path:
        path = Path(local_path)
        if path.exists() and path.is_file():
            return base64.b64encode(path.read_bytes()).decode("ascii")

    screenshot_base64 = str(artifact.screenshot_base64 or "").strip()
    if screenshot_base64:
        return screenshot_base64
    return None
