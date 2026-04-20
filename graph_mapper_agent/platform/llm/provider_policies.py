from __future__ import annotations
#graph_mapper_agent/platform/llm/provider_policies.py
from dataclasses import dataclass

from graph_mapper_agent.platform.llm.runtime_plan import (
    ProviderKind,
    RuntimeFamily,
    StructuredOutputMode,
)


@dataclass(frozen=True)
class ProviderPolicy:
    backend_names: tuple[str, ...]
    runtime_family: RuntimeFamily
    provider: ProviderKind
    provider_name: str
    adapter_key: str
    default_base_url: str | None
    default_model: str
    requires_api_key: bool
    supports_vision: bool
    supports_reasoning: bool
    supports_provider_routing: bool
    supports_structured_output: bool
    supported_structured_output_modes: tuple[StructuredOutputMode, ...]
    default_structured_output_mode: StructuredOutputMode | None
    supports_tools: bool
    supports_structured_and_tools_together: bool


LM_STUDIO_POLICY = ProviderPolicy(
    backend_names=("pydantic_ai_adapter", "pydantic_ai_lm_studio"),
    runtime_family="pydantic_ai",
    provider="lm_studio",
    provider_name="lm_studio",
    adapter_key="pydantic_ai_lm_studio",
    default_base_url="http://192.168.1.222:1234/v1",
    default_model="local-model",
    requires_api_key=False,
    supports_vision=True,
    supports_reasoning=False,
    supports_provider_routing=False,
    supports_structured_output=True,
    supported_structured_output_modes=("auto", "prompted"),
    default_structured_output_mode="auto",
    supports_tools=True,
    supports_structured_and_tools_together=False,
)

OPENROUTER_POLICY = ProviderPolicy(
    backend_names=("pydantic_ai_openrouter",),
    runtime_family="pydantic_ai",
    provider="openrouter",
    provider_name="openrouter",
    adapter_key="pydantic_ai_openrouter",
    default_base_url="https://openrouter.ai/api/v1",
    default_model="minimax/minimax-m2.7",
    requires_api_key=True,
    supports_vision=True,
    supports_reasoning=True,
    supports_provider_routing=True,
    supports_structured_output=True,
    supported_structured_output_modes=("auto", "native", "prompted", "tool"),
    default_structured_output_mode="prompted",
    supports_tools=True,
    supports_structured_and_tools_together=False,
)

OLLAMA_POLICY = ProviderPolicy(
    backend_names=("ollama",),
    runtime_family="callable",
    provider="ollama",
    provider_name="ollama",
    adapter_key="ollama_native",
    default_base_url="http://127.0.0.1:11434",
    default_model="llava",
    requires_api_key=False,
    supports_vision=True,
    supports_reasoning=False,
    supports_provider_routing=False,
    supports_structured_output=True,
    supported_structured_output_modes=("prompted",),
    default_structured_output_mode="prompted",
    supports_tools=False,
    supports_structured_and_tools_together=False,
)

_PROVIDER_POLICIES = (
    LM_STUDIO_POLICY,
    OPENROUTER_POLICY,
    OLLAMA_POLICY,
)


def resolve_provider_policy_from_backend(backend_name: str) -> ProviderPolicy:
    for policy in _PROVIDER_POLICIES:
        if backend_name in policy.backend_names:
            return policy
    raise ValueError(f"Backend no soportado para llm_runtime: {backend_name}")


def resolve_provider_policy(
    *,
    backend_name: str | None,
    runtime_family: str | None,
    provider: str | None,
) -> ProviderPolicy:
    if runtime_family and provider:
        for policy in _PROVIDER_POLICIES:
            if policy.runtime_family == runtime_family and policy.provider == provider:
                return policy
        raise ValueError(
            f"No existe policy para runtime_family={runtime_family!r}, provider={provider!r}"
        )

    if backend_name:
        return resolve_provider_policy_from_backend(backend_name)

    raise ValueError("Se requiere backend_name o runtime_family+provider para resolver provider policy.")
