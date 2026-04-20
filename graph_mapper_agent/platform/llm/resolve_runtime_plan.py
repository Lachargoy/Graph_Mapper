from __future__ import annotations
#graph_mapper_agent/platform/llm/resolve_runtime_plan.py
from typing import Any

from graph_mapper_agent.platform.llm.capabilities import (
    RuntimeCapabilities,
    derive_runtime_capabilities,
)
from graph_mapper_agent.platform.llm.config import (
    LlmRuntimeConfig,
)
from graph_mapper_agent.platform.llm.output_resolution import (
    OutputResolutionInput,
    resolve_output_mode,
)
from graph_mapper_agent.platform.llm.provider_policies import (
    resolve_provider_policy,
)
from graph_mapper_agent.platform.llm.runtime_plan import (
    ResolvedProviderRouting,
    ResolvedReasoningPolicy,
    ResolvedRuntimeIdentity,
    ResolvedRuntimePlan,
)


def resolve_reasoning_policy(
    *,
    capabilities: RuntimeCapabilities,
    requested_enabled: bool,
    requested_effort: str | None,
    requested_max_tokens: int | None,
    requested_exclude: bool,
) -> ResolvedReasoningPolicy:
    if not requested_enabled:
        return ResolvedReasoningPolicy(
            requested_enabled=False,
            requested_effort=requested_effort,
            requested_max_tokens=requested_max_tokens,
            requested_exclude=requested_exclude,
            effective_enabled=False,
            effective_effort=None,
            effective_max_tokens=None,
            effective_exclude=False,
            resolution_reason="reasoning_not_requested",
        )

    if not capabilities.supports_reasoning:
        return ResolvedReasoningPolicy(
            requested_enabled=True,
            requested_effort=requested_effort,
            requested_max_tokens=requested_max_tokens,
            requested_exclude=requested_exclude,
            effective_enabled=False,
            effective_effort=None,
            effective_max_tokens=None,
            effective_exclude=False,
            resolution_reason="provider_does_not_support_reasoning",
        )

    effective_effort = (
        requested_effort if capabilities.supports_reasoning_effort else None
    )
    effective_max_tokens = (
        requested_max_tokens if capabilities.supports_reasoning_max_tokens else None
    )
    effective_exclude = (
        requested_exclude if capabilities.supports_reasoning_exclude else False
    )

    if requested_effort and not capabilities.supports_reasoning_effort:
        reason = "reasoning_enabled_but_effort_not_supported"
    elif requested_max_tokens is not None and not capabilities.supports_reasoning_max_tokens:
        reason = "reasoning_enabled_but_max_tokens_not_supported"
    elif requested_exclude and not capabilities.supports_reasoning_exclude:
        reason = "reasoning_enabled_but_exclude_not_supported"
    else:
        reason = "reasoning_enabled_supported"

    return ResolvedReasoningPolicy(
        requested_enabled=True,
        requested_effort=requested_effort,
        requested_max_tokens=requested_max_tokens,
        requested_exclude=requested_exclude,
        effective_enabled=True,
        effective_effort=effective_effort,
        effective_max_tokens=effective_max_tokens,
        effective_exclude=effective_exclude,
        resolution_reason=reason,
    )


def resolve_runtime_plan(
    config: LlmRuntimeConfig,
    *,
    expected_output_name: str | None = None,
    tools_requested: bool = False,
    requested_tool_mode: str | None = None,
) -> ResolvedRuntimePlan:
    policy = resolve_provider_policy(
        backend_name=config.backend,
        runtime_family=getattr(config, "runtime_family", None),
        provider=getattr(config, "provider", None),
    )

    capabilities = derive_runtime_capabilities(
        policy=policy,
        supports_vision_override=config.supports_vision,
    )

    output_mode = resolve_output_mode(
        policy=policy,
        capabilities=capabilities,
        output_input=OutputResolutionInput(
            expected_output_name=expected_output_name,
            requested_structured_output_mode=config.structured_output_mode,
            tools_requested=tools_requested,
            requested_tool_mode=requested_tool_mode,
        ),
    )

    model = config.default_model or policy.default_model
    base_url = config.base_url or policy.default_base_url

    if policy.requires_api_key and not config.api_key:
        raise ValueError(
            f"El provider {policy.provider!r} requiere api_key y no fue proporcionada."
        )

    provider_routing = ResolvedProviderRouting(
        order=tuple(config.provider_order or ()),
        allow_fallbacks=config.provider_allow_fallbacks,
        require_parameters=config.provider_require_parameters,
        data_collection=None,
    )

    requested_reasoning_enabled = bool(config.enable_reasoning)

    reasoning = resolve_reasoning_policy(
        capabilities=capabilities,
        requested_enabled=requested_reasoning_enabled,
        requested_effort=getattr(config, "reasoning_effort", None),
        requested_max_tokens=getattr(config, "reasoning_max_tokens", None),
        requested_exclude=getattr(config, "reasoning_exclude", False),
    )

    identity = ResolvedRuntimeIdentity(
        backend_name=config.backend,
        runtime_family=policy.runtime_family,
        provider=policy.provider,
        provider_name=policy.provider_name,
        adapter_key=policy.adapter_key,
    )

    metadata: dict[str, Any] = {
        "requested_backend": config.backend,
        "timeout_seconds": config.timeout_seconds,
        "resolved_runtime_family": policy.runtime_family,
        "resolved_provider": policy.provider,
        "resolved_provider_name": policy.provider_name,
        "resolved_adapter_key": policy.adapter_key,
        "supports_vision": capabilities.supports_vision,
        "requested_structured_output_mode": config.structured_output_mode,
        "effective_structured_output_mode": output_mode.effective_structured_output_mode,
        "tools_requested": tools_requested,
        "effective_tool_mode": output_mode.effective_tool_mode,
        "output_resolution_reason": output_mode.resolution_reason,
        "requested_reasoning_enabled": requested_reasoning_enabled,
        "requested_reasoning_effort": getattr(config, "reasoning_effort", None),
        "effective_reasoning_enabled": reasoning.effective_enabled,
        "effective_reasoning_effort": reasoning.effective_effort,
        "reasoning_resolution_reason": reasoning.resolution_reason,
    }

    return ResolvedRuntimePlan(
        identity=identity,
        model=model,
        base_url=base_url,
        api_key=config.api_key,
        supports_vision=capabilities.supports_vision,
        provider_routing=provider_routing,
        reasoning=reasoning,
        output_mode=output_mode,
        metadata=metadata,
    )
