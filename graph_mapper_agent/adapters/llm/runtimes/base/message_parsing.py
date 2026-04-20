from __future__ import annotations

import json
from typing import Any

from pydantic_ai.messages import ImageUrl

from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeError,
)


def parse_messages(
    messages: list[dict[str, Any]],
    *,
    supports_vision: bool,
) -> tuple[str | None, str | list[Any], int]:
    system_prompts: list[str] = []
    conversation_messages: list[dict[str, Any]] = []

    for message in messages:
        role = str(message.get("role", "")).strip().lower()
        content = message.get("content")

        if role == "system":
            text = extract_system_text(content)
            if text:
                system_prompts.append(text)
        else:
            conversation_messages.append(message)

    user_prompt, image_count = extract_user_prompt(
        conversation_messages,
        supports_vision=supports_vision,
    )
    system_prompt_text = "\n\n".join(sp for sp in system_prompts if sp) or None
    return system_prompt_text, user_prompt, image_count


def extract_system_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_fragments: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_fragments.append(str(part.get("text", "")).strip())
        return "\n".join(text_fragments)

    return ""


def extract_user_prompt(
    conversation_messages: list[dict[str, Any]],
    *,
    supports_vision: bool,
) -> tuple[str | list[Any], int]:
    if not conversation_messages:
        return "{}", 0

    content = conversation_messages[-1].get("content") or ""

    if isinstance(content, str):
        return content or "{}", 0

    if not isinstance(content, list):
        return "{}", 0

    has_image = any(
        isinstance(item, dict) and item.get("type") == "image_url"
        for item in content
    )

    if not has_image:
        text = join_text_parts(content)
        return text or "{}", 0

    return build_multimodal_prompt(content, supports_vision=supports_vision)


def join_text_parts(content: list[Any]) -> str:
    text_parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text_parts.append(item)
        elif isinstance(item, dict) and item.get("type") == "text":
            text_parts.append(str(item.get("text", "")))
    return "\n\n".join(tp for tp in text_parts if tp)


def build_multimodal_prompt(
    content: list[Any],
    *,
    supports_vision: bool,
) -> tuple[list[Any], int]:
    if not supports_vision:
        raise LlmRuntimeError(
            error_class="VisionNotSupported",
            message=(
                "An image was received in request.messages, but the resolved "
                "runtime does not support vision."
            ),
            retryable=False,
        )

    multimodal_parts: list[Any] = []
    image_count = 0

    for item in content:
        if not isinstance(item, dict):
            multimodal_parts.append(str(item))
            continue

        part_type = item.get("type")

        if part_type == "text":
            multimodal_parts.append(str(item.get("text", "")))
        elif part_type == "image_url":
            img_url = validated_image_url(item)
            multimodal_parts.append(ImageUrl(url=img_url))
            image_count += 1

    return multimodal_parts, image_count


def validated_image_url(item: dict[str, Any]) -> str:
    image_payload = item.get("image_url", {})
    if not isinstance(image_payload, dict):
        raise LlmRuntimeError(
            error_class="InvalidImagePart",
            message="image_url is not a valid dictionary.",
            retryable=False,
        )

    img_url = image_payload.get("url", "")
    if not img_url:
        raise LlmRuntimeError(
            error_class="InvalidImagePart",
            message="The image_url part does not contain a valid url.",
            retryable=False,
        )

    return img_url


def parse_json_object_from_text(text: str) -> dict[str, Any]:
    candidate = _strip_markdown_fence(text.strip())

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        candidate = _extract_first_json_object(candidate)
        parsed = json.loads(candidate)

    if not isinstance(parsed, dict):
        raise ValueError("The structured output is not a JSON object.")

    return parsed


def _strip_markdown_fence(text: str) -> str:
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if len(lines) < 3:
        return text

    first_line = lines[0].strip()
    last_line = lines[-1].strip()
    if not last_line.startswith("```"):
        return text
    if first_line.startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return text


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in the response.")

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            depth += 1
            continue

        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("Could not isolate a balanced JSON object in the response.")
