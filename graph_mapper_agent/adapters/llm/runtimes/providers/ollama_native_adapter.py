from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from graph_mapper_agent.adapters.llm.outputs.structured_output_registry import (
    resolve_output_type,
)
from graph_mapper_agent.adapters.llm.runtimes.base.callable_llm_runtime_adapter import (
    CallableLlmRuntimeAdapter,
    RawLlmResult,
)
from graph_mapper_agent.adapters.llm.runtimes.base.structured_output import (
    parse_structured_output_text,
    prepare_structured_output_payload,
    validate_prepared_output,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeError,
    LlmRuntimeRequest,
)


@dataclass(frozen=True)
class OllamaNativeSettings:
    base_url: str = "http://127.0.0.1:11434"
    default_model: str = "llava"
    api_key: str | None = None
    timeout_seconds: int = 180
    backend_name: str = "ollama"
    supports_vision: bool = True
    structured_output_mode: str = "prompted"


class OllamaNativeAdapter(CallableLlmRuntimeAdapter):
    def __init__(self, settings: OllamaNativeSettings) -> None:
        self._settings = settings
        super().__init__(
            provider_name="ollama",
            invoke_callable=self._invoke_ollama,
        )

    def _invoke_ollama(
        self,
        request: LlmRuntimeRequest,
    ) -> RawLlmResult:
        output_type = resolve_output_type(request.expected_output_name)
        messages = _build_ollama_messages(
            request.messages,
            supports_vision=self._settings.supports_vision,
            structured_output_name=request.expected_output_name,
            output_type=output_type,
        )
        payload: dict[str, Any] = {
            "model": request.model_hint or self._settings.default_model,
            "stream": False,
            "messages": messages,
        }
        if request.temperature is not None:
            payload["options"] = {"temperature": float(request.temperature)}
        if output_type is not None:
            payload["format"] = output_type.model_json_schema()

        response_payload = _post_ollama_chat(
            base_url=self._settings.base_url,
            timeout_seconds=self._settings.timeout_seconds,
            payload=payload,
            api_key=self._settings.api_key,
        )
        response_text = _extract_ollama_text(response_payload)
        validation: dict[str, Any] | None = None
        result_response: dict[str, Any]
        raw_parsed_json: dict[str, Any] | None = None
        raw_prepared_json: dict[str, Any] | None = None

        if output_type is not None:
            parsed_json = _parse_json_response(response_text)
            raw_parsed_json = dict(parsed_json)
            preparation = prepare_structured_output_payload(
                expected_output_name=request.expected_output_name,
                parsed_payload=parsed_json,
            )
            raw_prepared_json = dict(preparation.prepared_payload)
            try:
                validated = validate_prepared_output(
                    output_type=output_type,
                    prepared_payload=preparation.prepared_payload,
                )
            except ValidationError as exc:
                _debug_validation_failure(
                    expected_output_name=request.expected_output_name,
                    output_type=output_type,
                    response_text=response_text,
                    parsed_json=parsed_json,
                    prepared_json=preparation.prepared_payload,
                    repair_notes=preparation.repair_notes,
                    response_payload=response_payload,
                    error=exc,
                )
                raise
            parsed_payload = validated.model_dump(mode="json")
            validation = {
                "parsed_response": parsed_payload,
                "status": "validated",
                "structured_output_name": request.expected_output_name,
                "repair_applied": preparation.repair_applied,
                "repair_notes": list(preparation.repair_notes),
            }
            result_response = {
                "parsed_response": parsed_payload,
                "output": parsed_payload,
                "content": json.dumps(parsed_payload, ensure_ascii=False),
                "message": {
                    "role": "assistant",
                    "content": json.dumps(parsed_payload, ensure_ascii=False),
                },
                "finish_reason": _extract_finish_reason(response_payload),
            }
        else:
            result_response = {
                "text": response_text,
                "content": response_text,
                "message": {
                    "role": "assistant",
                    "content": response_text,
                },
                "finish_reason": _extract_finish_reason(response_payload),
            }

        prompt_eval_count = _optional_int(response_payload.get("prompt_eval_count"))
        eval_count = _optional_int(response_payload.get("eval_count"))
        total_tokens = None
        if prompt_eval_count is not None or eval_count is not None:
            total_tokens = (prompt_eval_count or 0) + (eval_count or 0)

        return RawLlmResult(
            model=str(request.model_hint or self._settings.default_model),
            response=result_response,
            validation=validation,
            structured_output_name=request.expected_output_name,
            input_tokens=prompt_eval_count,
            output_tokens=eval_count,
            total_tokens=total_tokens,
            raw_response={
                "output": result_response.get("output"),
                "parsed_json": raw_parsed_json,
                "prepared_json": raw_prepared_json,
                "parsed_response": None if validation is None else validation.get("parsed_response"),
                "response_payload": response_payload,
            },
        )


def _debug_validation_failure(
    *,
    expected_output_name: str | None,
    output_type: type,
    response_text: str,
    parsed_json: dict[str, Any],
    prepared_json: dict[str, Any],
    repair_notes: tuple[str, ...],
    response_payload: dict[str, Any],
    error: ValidationError,
) -> None:
    print(
        "[ollama_native_adapter] structured output validation failed",
        flush=True,
    )
    print(
        f"[ollama_native_adapter] expected_output_name={expected_output_name!r} "
        f"schema={output_type.__name__!r}",
        flush=True,
    )
    print(
        f"[ollama_native_adapter] validation_error={str(error)}",
        flush=True,
    )
    print(
        "[ollama_native_adapter] raw_response_text_begin",
        flush=True,
    )
    print(response_text, flush=True)
    print(
        "[ollama_native_adapter] raw_response_text_end",
        flush=True,
    )
    print(
        "[ollama_native_adapter] parsed_json_begin",
        flush=True,
    )
    print(
        json.dumps(parsed_json, ensure_ascii=False, indent=2, default=str),
        flush=True,
    )
    print(
        "[ollama_native_adapter] parsed_json_end",
        flush=True,
    )
    print(
        f"[ollama_native_adapter] repair_notes={list(repair_notes)!r}",
        flush=True,
    )
    print(
        "[ollama_native_adapter] prepared_json_begin",
        flush=True,
    )
    print(
        json.dumps(prepared_json, ensure_ascii=False, indent=2, default=str),
        flush=True,
    )
    print(
        "[ollama_native_adapter] prepared_json_end",
        flush=True,
    )
    print(
        "[ollama_native_adapter] response_payload_begin",
        flush=True,
    )
    print(
        json.dumps(response_payload, ensure_ascii=False, indent=2, default=str),
        flush=True,
    )
    print(
        "[ollama_native_adapter] response_payload_end",
        flush=True,
    )
    print(
        "[ollama_native_adapter] expected_schema_json_begin",
        flush=True,
    )
    print(
        json.dumps(output_type.model_json_schema(), ensure_ascii=False, indent=2, default=str),
        flush=True,
    )
    print(
        "[ollama_native_adapter] expected_schema_json_end",
        flush=True,
    )


def _build_ollama_messages(
    messages: tuple[dict[str, Any], ...],
    *,
    supports_vision: bool,
    structured_output_name: str | None,
    output_type: type | None,
) -> list[dict[str, Any]]:
    ollama_messages: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user").strip().lower() or "user"
        content = message.get("content")
        text_parts: list[str] = []
        image_inputs: list[str] = []

        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                    continue
                if not isinstance(part, dict):
                    text_parts.append(str(part))
                    continue
                part_type = str(part.get("type") or "").strip().lower()
                if part_type == "text":
                    text_parts.append(str(part.get("text") or ""))
                elif part_type == "image_url":
                    if not supports_vision:
                        raise LlmRuntimeError(
                            error_class="VisionNotSupported",
                            message="The resolved Ollama runtime does not support vision.",
                            retryable=False,
                        )
                    image_url = part.get("image_url")
                    if not isinstance(image_url, dict):
                        raise LlmRuntimeError(
                            error_class="InvalidImagePart",
                            message="image_url is not a valid dictionary.",
                            retryable=False,
                        )
                    normalized = _normalize_ollama_image_input(str(image_url.get("url") or "").strip())
                    if normalized:
                        image_inputs.append(normalized)

        ollama_message: dict[str, Any] = {
            "role": _normalize_ollama_role(role),
            "content": "\n\n".join(part for part in text_parts if part).strip(),
        }
        if image_inputs:
            ollama_message["images"] = image_inputs
        ollama_messages.append(ollama_message)

    if output_type is not None:
        schema_text = json.dumps(output_type.model_json_schema(), ensure_ascii=False, indent=2)
        ollama_messages.append(
            {
                "role": "system",
                "content": (
                    "Respond only with a single valid JSON object that exactly matches this schema. "
                    "Do not use markdown, fences, or additional text.\n\n"
                    f"structured_output_name={structured_output_name or 'unknown'}\n"
                    f"{schema_text}"
                ),
            }
        )

    return ollama_messages


def _post_ollama_chat(
    *,
    base_url: str,
    timeout_seconds: int,
    payload: dict[str, Any],
    api_key: str | None,
) -> dict[str, Any]:
    normalized_base_url = str(base_url or "").rstrip("/")
    if normalized_base_url.endswith("/v1"):
        normalized_base_url = normalized_base_url[:-3]
    endpoint = f"{normalized_base_url}/api/chat"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=int(timeout_seconds or 180)) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise LlmRuntimeError(
            error_class="OllamaHttpError",
            message=f"Ollama returned HTTP {exc.code}: {body_text}",
            retryable=exc.code >= 500,
        ) from exc
    except URLError as exc:
        raise LlmRuntimeError(
            error_class="OllamaConnectionError",
            message=f"Could not connect to Ollama: {exc.reason}",
            retryable=True,
        ) from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LlmRuntimeError(
            error_class="OllamaInvalidJson",
            message="Ollama returned invalid JSON.",
            retryable=False,
        ) from exc
    if not isinstance(parsed, dict):
        raise LlmRuntimeError(
            error_class="OllamaInvalidResponse",
            message="Ollama returned an unstructured response.",
            retryable=False,
        )
    return parsed


def _extract_ollama_text(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, dict):
        content = str(message.get("content") or "").strip()
        if content:
            return content
    response = str(payload.get("response") or "").strip()
    if response:
        return response
    raise LlmRuntimeError(
        error_class="OllamaEmptyResponse",
        message="Ollama did not return any response content.",
        retryable=False,
    )


def _parse_json_response(text: str) -> dict[str, Any]:
    try:
        parsed = parse_structured_output_text(text)
    except ValueError as exc:
        raise LlmRuntimeError(
            error_class="StructuredOutputParseError",
            message="Ollama did not return a valid JSON for structured output.",
            retryable=False,
        ) from exc
    return parsed


def _normalize_ollama_role(role: str) -> str:
    if role in {"system", "assistant", "user", "tool"}:
        return role
    return "user"


def _normalize_ollama_image_input(url: str) -> str | None:
    if not url:
        return None
    lower = url.lower()
    if lower.startswith("data:image/") and ";base64," in lower:
        return url.split(",", 1)[1].strip() or None
    return url


def _extract_finish_reason(payload: dict[str, Any]) -> str:
    done_reason = str(payload.get("done_reason") or "").strip()
    return done_reason or "stop"


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
