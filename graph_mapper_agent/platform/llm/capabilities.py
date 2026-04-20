from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.platform.llm.provider_policies import (
    ProviderPolicy,
)
from graph_mapper_agent.platform.llm.runtime_plan import (
    StructuredOutputMode,
)


@dataclass(frozen=True)
class RuntimeCapabilities:
    supports_vision: bool
    supports_reasoning: bool
    supports_reasoning_effort: bool
    supports_reasoning_max_tokens: bool
    supports_reasoning_exclude: bool
    supports_provider_routing: bool
    supports_structured_output: bool
    supported_structured_output_modes: tuple[StructuredOutputMode, ...]
    supports_tools: bool
    supports_structured_and_tools_together: bool


def derive_runtime_capabilities(
    *,
    policy: ProviderPolicy,
    supports_vision_override: bool | None,
) -> RuntimeCapabilities:
    supports_vision = (
        supports_vision_override
        if supports_vision_override is not None
        else policy.supports_vision
    )

    if policy.provider == "openrouter":
        supports_reasoning = True
        supports_reasoning_effort = True
        supports_reasoning_max_tokens = True
        supports_reasoning_exclude = True
    else:
        supports_reasoning = False
        supports_reasoning_effort = False
        supports_reasoning_max_tokens = False
        supports_reasoning_exclude = False

    return RuntimeCapabilities(
        supports_vision=supports_vision,
        supports_reasoning=supports_reasoning,
        supports_reasoning_effort=supports_reasoning_effort,
        supports_reasoning_max_tokens=supports_reasoning_max_tokens,
        supports_reasoning_exclude=supports_reasoning_exclude,
        supports_provider_routing=policy.supports_provider_routing,
        supports_structured_output=policy.supports_structured_output,
        supported_structured_output_modes=policy.supported_structured_output_modes,
        supports_tools=policy.supports_tools,
        supports_structured_and_tools_together=policy.supports_structured_and_tools_together,
    )

