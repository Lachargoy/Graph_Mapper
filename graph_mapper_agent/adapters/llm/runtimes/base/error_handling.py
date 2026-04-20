from __future__ import annotations

import json
from typing import Any, Callable, NamedTuple


NON_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({400, 401, 403, 404, 422})

PROVIDER_ERROR_ORIGINS: dict[str, str] = {
    "ModelHTTPError": "provider_response",
    "BadRequestError": "provider_response",
    "APIStatusError": "provider_response",
    "APITimeoutError": "provider_transport",
    "APIConnectionError": "provider_transport",
}


class ProviderErrorInfo(NamedTuple):
    provider_name: str | None = None
    provider_message: str | None = None
    provider_code: str | None = None


def build_failure_details(
    exc: Exception,
    *,
    serialize_value: Callable[[object], Any],
) -> dict[str, Any]:
    body = getattr(exc, "body", None)
    status_code = getattr(exc, "status_code", None)
    cause = exc.__cause__

    provider_info = (
        extract_provider_error_info(body)
        if isinstance(body, dict)
        else ProviderErrorInfo()
    )

    return {
        "origin": classify_error_origin(exc),
        "message": str(exc),
        "status_code": status_code,
        "provider_name": provider_info.provider_name,
        "provider_message": provider_info.provider_message,
        "provider_code": provider_info.provider_code,
        "cause_type": type(cause).__name__ if cause is not None else None,
        "cause_message": str(cause) if cause is not None else None,
        "exception_payload": serialize_value(getattr(exc, "__dict__", {})),
    }


def extract_provider_error_info(body: dict[str, Any]) -> ProviderErrorInfo:
    provider_name: str | None = None
    provider_message: str | None = None
    provider_code: str | None = None

    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        provider_name = metadata.get("provider_name")
        raw_str = metadata.get("raw")
        if isinstance(raw_str, str):
            try:
                raw_parsed = json.loads(raw_str)
            except (json.JSONDecodeError, TypeError, ValueError):
                raw_parsed = None
            if isinstance(raw_parsed, dict):
                raw_error = raw_parsed.get("error")
                if isinstance(raw_error, dict):
                    provider_message = raw_error.get("message")
                    provider_code = raw_error.get("code")

    body_error = body.get("error")
    err_msg = body_error.get("message") if isinstance(body_error, dict) else None
    err_code = body_error.get("code") if isinstance(body_error, dict) else None

    provider_message = err_msg or body.get("message") or provider_message
    provider_code = err_code or body.get("code") or provider_code

    return ProviderErrorInfo(
        provider_name=provider_name,
        provider_message=provider_message,
        provider_code=provider_code,
    )


def classify_error_origin(exc: Exception) -> str:
    origin = PROVIDER_ERROR_ORIGINS.get(type(exc).__name__)
    if origin is not None:
        return origin

    if isinstance(exc, (AssertionError, TypeError, ValueError)):
        return "local_mapping"

    return "unknown"


def is_retryable(failure: dict[str, Any]) -> bool:
    if failure["origin"] == "local_mapping":
        return False

    status_code = failure.get("status_code")
    if status_code is not None and status_code in NON_RETRYABLE_STATUS_CODES:
        return False

    return True

