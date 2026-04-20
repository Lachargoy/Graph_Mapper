from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

MAX_SERIALIZATION_DEPTH: int = 30
MAX_NESTED_SEARCH_DEPTH: int = 30


def serialize_output(output: object) -> Any:
    if output is None:
        return None
    if hasattr(output, "model_dump"):
        try:
            return output.model_dump(mode="json")
        except TypeError:
            return output.model_dump()
    if isinstance(output, dict):
        return dict(output)
    if dataclasses.is_dataclass(output) and not isinstance(output, type):
        try:
            return dataclasses.asdict(output)
        except (TypeError, ValueError):
            return str(output)
    return output


def response_text_from_output(output_payload: Any) -> str:
    if output_payload is None:
        return ""
    if isinstance(output_payload, str):
        return output_payload
    try:
        return json.dumps(output_payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(output_payload)


def serialize_messages(result: object, method_name: str) -> list[dict[str, Any]] | None:
    method = getattr(result, method_name, None)
    if method is None:
        return None
    try:
        messages = method()
    except TypeError:
        return None
    serialized = serialize_value(messages)
    return serialized if isinstance(serialized, list) else None


def serialize_value(value: object, _depth: int = 0) -> Any:
    if _depth > MAX_SERIALIZATION_DEPTH:
        return f"<max depth {MAX_SERIALIZATION_DEPTH}>"
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return repr(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return {
                key: serialize_value(val, _depth + 1)
                for key, val in dataclasses.asdict(value).items()
            }
        except (TypeError, ValueError):
            return repr(value)
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="json")
        except TypeError:
            dumped = value.model_dump()
        return serialize_value(dumped, _depth + 1)
    if isinstance(value, dict):
        return {str(key): serialize_value(val, _depth + 1) for key, val in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [serialize_value(item, _depth + 1) for item in value]
    if hasattr(value, "__dict__"):
        try:
            return serialize_value(vars(value), _depth + 1)
        except TypeError:
            return repr(value)
    return repr(value)


def reasoning_payload(*, agent_response: Any, agent_metadata: Any, all_messages: Any, new_messages: Any) -> Any:
    for payload in (agent_response, agent_metadata, new_messages, all_messages):
        found = find_nested_key(payload, "reasoning_details")
        if found is not None:
            return found
    return None


def find_nested_key(value: Any, target_key: str, _depth: int = 0) -> Any:
    if _depth > MAX_NESTED_SEARCH_DEPTH:
        return None
    if isinstance(value, dict):
        if target_key in value:
            return value[target_key]
        for item in value.values():
            found = find_nested_key(item, target_key, _depth + 1)
            if found is not None:
                return found
        return None
    if isinstance(value, list):
        for item in value:
            found = find_nested_key(item, target_key, _depth + 1)
            if found is not None:
                return found
    return None


def finish_reason_from_result(*, agent_response: Any, new_messages: Any, all_messages: Any) -> str:
    for payload in (agent_response, new_messages, all_messages):
        finish_reason = find_nested_key(payload, "finish_reason")
        if finish_reason is not None:
            text = str(finish_reason).strip()
            if text:
                return text
    return "stop"


def usage_payload(usage: object) -> dict[str, int | None]:
    get = usage_int
    return {
        "input_tokens": get(usage, "input_tokens", "request_tokens", "prompt_tokens"),
        "output_tokens": get(usage, "output_tokens", "response_tokens", "completion_tokens"),
        "reasoning_tokens": get(usage, "reasoning_tokens"),
        "cached_tokens": get(usage, "cached_tokens"),
        "total_tokens": get(usage, "total_tokens"),
    }


def usage_int(usage: object, *names: str) -> int | None:
    if usage is None:
        return None
    for name in names:
        value = getattr(usage, name, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


def coerce_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

