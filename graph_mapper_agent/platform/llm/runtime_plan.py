from __future__ import annotations
#graph_mapper_agent/platform/llm/runtime_plan.py
from dataclasses import dataclass, field
from typing import Any, Literal


RuntimeFamily = Literal["pydantic_ai", "callable"]
ProviderKind = Literal["lm_studio", "openrouter", "ollama"]
AdapterKey = Literal["pydantic_ai_lm_studio", "pydantic_ai_openrouter", "ollama_native"]

StructuredOutputMode = Literal["auto", "native", "prompted", "tool"]
EffectiveToolMode = Literal["disabled", "native"]
OutputCombination = Literal[
    "plain_text",
    "structured_only",
    "tools_only",
    "incompatible",
]


@dataclass(frozen=True)
class ResolvedProviderRouting:
    order: tuple[str, ...] = ()
    allow_fallbacks: bool = True
    require_parameters: bool = False
    data_collection: str | None = None


@dataclass(frozen=True)
class ResolvedReasoningPolicy:
    requested_enabled: bool = False
    requested_effort: str | None = None
    requested_max_tokens: int | None = None
    requested_exclude: bool = False
    effective_enabled: bool = False
    effective_effort: str | None = None
    effective_max_tokens: int | None = None
    effective_exclude: bool = False
    resolution_reason: str = "reasoning_not_requested"


@dataclass(frozen=True)
class ResolvedOutputMode:
    structured_output_requested: bool
    expected_output_name: str | None
    requested_structured_output_mode: StructuredOutputMode | None
    tools_requested: bool
    requested_tool_mode: str | None
    effective_structured_output_mode: StructuredOutputMode | None
    effective_tool_mode: EffectiveToolMode
    combination: OutputCombination
    resolution_reason: str


@dataclass(frozen=True)
class ResolvedRuntimeIdentity:
    backend_name: str
    runtime_family: RuntimeFamily
    provider: ProviderKind
    provider_name: str
    adapter_key: AdapterKey


@dataclass(frozen=True)
class ResolvedRuntimePlan:
    identity: ResolvedRuntimeIdentity
    model: str
    base_url: str | None
    api_key: str | None
    supports_vision: bool
    provider_routing: ResolvedProviderRouting
    reasoning: ResolvedReasoningPolicy
    output_mode: ResolvedOutputMode
    metadata: dict[str, Any] = field(default_factory=dict)
