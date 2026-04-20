from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider

from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeError,
    LlmRuntimeRequest,
)


def build_model_settings(
    *,
    request: LlmRuntimeRequest,
    settings: object,
) -> tuple[OpenAIChatModelSettings | None, dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    raw_settings: dict[str, Any] = {}
    extra_body: dict[str, Any] = {}

    if request.temperature is not None:
        raw_settings["temperature"] = request.temperature

    reasoning = build_reasoning_body(settings)
    provider = build_provider_body(settings)

    if reasoning:
        extra_body["reasoning"] = reasoning
    if provider:
        extra_body["provider"] = provider
    if extra_body:
        raw_settings["extra_body"] = extra_body

    if not raw_settings:
        return None, {}, reasoning, provider

    model_settings = OpenAIChatModelSettings(**raw_settings)
    try:
        dumped = model_settings.model_dump(exclude_none=True)
    except Exception:
        dumped = str(model_settings)
    return model_settings, dumped, reasoning, provider


def build_reasoning_body(settings: object) -> dict[str, Any] | None:
    if not getattr(settings, "reasoning_enabled", False):
        return None

    payload: dict[str, Any] = {"enabled": True}

    reasoning_effort = getattr(settings, "reasoning_effort", None)
    reasoning_max_tokens = getattr(settings, "reasoning_max_tokens", None)
    reasoning_exclude = getattr(settings, "reasoning_exclude", False)

    if reasoning_effort:
        payload["effort"] = reasoning_effort
    if reasoning_max_tokens is not None:
        payload["max_tokens"] = reasoning_max_tokens
    if reasoning_exclude:
        payload["exclude"] = True

    return payload


def build_provider_body(settings: object) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}

    if getattr(settings, "provider_require_parameters", False):
        payload["require_parameters"] = True
    if not getattr(settings, "provider_allow_fallbacks", True):
        payload["allow_fallbacks"] = False
    provider_order = getattr(settings, "provider_order", ())
    if provider_order:
        payload["order"] = list(provider_order)

    return payload or None


def build_model(
    *,
    model_name: str,
    settings: object,
    client_cache: dict[str, AsyncOpenAI],
) -> OpenAIChatModel:
    client = get_or_create_client(settings=settings, client_cache=client_cache)
    provider = OpenAIProvider(openai_client=client)
    return OpenAIChatModel(model_name, provider=provider)


def get_or_create_client(
    *,
    settings: object,
    client_cache: dict[str, AsyncOpenAI],
) -> AsyncOpenAI:
    base_url = normalized_base_url(settings)
    api_key = getattr(settings, "api_key", None) or ""
    cache_key = f"{base_url}|{api_key}"

    cached = client_cache.get(cache_key)
    if cached is not None:
        return cached

    timeout_seconds = getattr(settings, "timeout_seconds", None)
    timeout = float(timeout_seconds) if timeout_seconds else None

    client = AsyncOpenAI(
        api_key=getattr(settings, "api_key", None) or "not-needed",
        base_url=base_url,
        timeout=timeout,
    )

    client_cache[cache_key] = client
    return client


def normalized_base_url(settings: object) -> str:
    base_url = getattr(settings, "base_url", None)
    if not base_url:
        raise LlmRuntimeError(
            error_class="ConfigurationError",
            message="PydanticAiOpenAiCompatibleSettings.base_url is required.",
            retryable=False,
        )

    normalized = str(base_url).rstrip("/")
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"
