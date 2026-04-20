from __future__ import annotations
#./adapters/llm/runtimes/providers/pydantic_ai_lm_studio_adapter.py
from dataclasses import dataclass

from graph_mapper_agent.adapters.llm.runtimes.base.pydantic_ai_openai_compatible_adapter import (
    PydanticAiOpenAiCompatibleAdapter,
    PydanticAiOpenAiCompatibleSettings,
)


@dataclass(frozen=True)
class PydanticAiLmStudioSettings:
    base_url: str = "http://127.0.0.1:1234"
    default_model: str = "local-model"
    api_key: str | None = None
    timeout_seconds: int = 180

    # New fields aligned with the runtime plan
    backend_name: str = "pydantic_ai_adapter"
    supports_vision: bool = False
    structured_output_mode: str = "auto"


class PydanticAiLmStudioAdapter(PydanticAiOpenAiCompatibleAdapter):
    """
    Official LM Studio runtime based on the PydanticAI family.

    This adapter does not implement all the LLM logic on its own; it only:
    - translates LM Studio specific settings
    - delegates structured execution to the openai-compatible base adapter
    """

    def __init__(self, settings: PydanticAiLmStudioSettings) -> None:
        super().__init__(
            settings=PydanticAiOpenAiCompatibleSettings(
                base_url=settings.base_url,
                default_model=settings.default_model,
                api_key=settings.api_key,
                timeout_seconds=settings.timeout_seconds,
                provider_name="lm_studio",
                backend_name=settings.backend_name,
                supports_vision=settings.supports_vision,
                reasoning_enabled=False,
                structured_output_mode=settings.structured_output_mode,
                provider_require_parameters=False,
                provider_allow_fallbacks=True,
                provider_order=(),
            ),
            fallback_runtime=None,
        )

        self._lm_studio_settings = settings
