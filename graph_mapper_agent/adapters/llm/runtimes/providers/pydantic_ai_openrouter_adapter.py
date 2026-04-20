from __future__ import annotations
#aither/adapters/llm/runtimes/providers/pydantic_ai_openrouter_adapter.py
from dataclasses import dataclass

from graph_mapper_agent.adapters.llm.runtimes.base.pydantic_ai_openai_compatible_adapter import (
    PydanticAiOpenAiCompatibleAdapter,
    PydanticAiOpenAiCompatibleSettings,
)


@dataclass(frozen=True)
class PydanticAiOpenRouterSettings:
    base_url: str = "https://openrouter.ai/api/v1"
    default_model: str = "openrouter/auto"
    api_key: str | None = None
    timeout_seconds: int = 250

    backend_name: str = "pydantic_ai_openrouter"
    supports_vision: bool = False

    enable_reasoning: bool = False
    reasoning_effort: str | None = None
    reasoning_max_tokens: int | None = None
    reasoning_exclude: bool = False

    structured_output_mode: str = "auto"
    provider_require_parameters: bool = False
    provider_allow_fallbacks: bool = True
    provider_order: tuple[str, ...] = ()


class PydanticAiOpenRouterAdapter(PydanticAiOpenAiCompatibleAdapter):
    def __init__(self, settings: PydanticAiOpenRouterSettings) -> None:
        super().__init__(
            settings=PydanticAiOpenAiCompatibleSettings(
                base_url=settings.base_url,
                default_model=settings.default_model,
                api_key=settings.api_key,
                timeout_seconds=settings.timeout_seconds,
                provider_name="openrouter",
                backend_name=settings.backend_name,
                supports_vision=settings.supports_vision,
                reasoning_enabled=settings.enable_reasoning,
                reasoning_effort=settings.reasoning_effort,
                reasoning_max_tokens=settings.reasoning_max_tokens,
                reasoning_exclude=settings.reasoning_exclude,
                structured_output_mode=settings.structured_output_mode,
                provider_require_parameters=settings.provider_require_parameters,
                provider_allow_fallbacks=settings.provider_allow_fallbacks,
                provider_order=settings.provider_order,
            ),
            fallback_runtime=None,
        )
