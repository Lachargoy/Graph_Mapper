from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.platform.llm.capabilities import (
    RuntimeCapabilities,
)
from graph_mapper_agent.platform.llm.provider_policies import (
    ProviderPolicy,
)
from graph_mapper_agent.platform.llm.runtime_plan import (
    EffectiveToolMode,
    OutputCombination,
    ResolvedOutputMode,
    StructuredOutputMode,
)


@dataclass(frozen=True)
class OutputResolutionInput:
    expected_output_name: str | None
    requested_structured_output_mode: StructuredOutputMode | None
    tools_requested: bool = False
    requested_tool_mode: str | None = None


def resolve_output_mode(
    *,
    policy: ProviderPolicy,
    capabilities: RuntimeCapabilities,
    output_input: OutputResolutionInput,
) -> ResolvedOutputMode:
    structured_requested = output_input.expected_output_name is not None

    requested_structured_mode = output_input.requested_structured_output_mode
    if structured_requested and requested_structured_mode is None:
        requested_structured_mode = policy.default_structured_output_mode

    if structured_requested and not capabilities.supports_structured_output:
        return ResolvedOutputMode(
            structured_output_requested=True,
            expected_output_name=output_input.expected_output_name,
            requested_structured_output_mode=requested_structured_mode,
            tools_requested=output_input.tools_requested,
            requested_tool_mode=output_input.requested_tool_mode,
            effective_structured_output_mode=None,
            effective_tool_mode="disabled",
            combination="incompatible",
            resolution_reason="structured_output_not_supported_by_runtime",
        )

    if output_input.tools_requested and not capabilities.supports_tools:
        return ResolvedOutputMode(
            structured_output_requested=structured_requested,
            expected_output_name=output_input.expected_output_name,
            requested_structured_output_mode=requested_structured_mode,
            tools_requested=True,
            requested_tool_mode=output_input.requested_tool_mode,
            effective_structured_output_mode=None if structured_requested else None,
            effective_tool_mode="disabled",
            combination="incompatible",
            resolution_reason="tools_not_supported_by_runtime",
        )

    if structured_requested and output_input.tools_requested:
        if not capabilities.supports_structured_and_tools_together:
            return ResolvedOutputMode(
                structured_output_requested=True,
                expected_output_name=output_input.expected_output_name,
                requested_structured_output_mode=requested_structured_mode,
                tools_requested=True,
                requested_tool_mode=output_input.requested_tool_mode,
                effective_structured_output_mode=None,
                effective_tool_mode="disabled",
                combination="incompatible",
                resolution_reason="structured_output_and_tools_not_supported_together",
            )

    effective_structured_mode = None
    if structured_requested:
        if requested_structured_mode in capabilities.supported_structured_output_modes:
            effective_structured_mode = requested_structured_mode
            resolution_reason = "requested_structured_output_mode_supported"
        else:
            effective_structured_mode = policy.default_structured_output_mode
            resolution_reason = "requested_structured_output_mode_degraded_to_provider_default"
    else:
        resolution_reason = "plain_text_mode"

    effective_tool_mode: EffectiveToolMode = (
        "native" if output_input.tools_requested else "disabled"
    )

    if structured_requested and not output_input.tools_requested:
        combination: OutputCombination = "structured_only"
    elif not structured_requested and output_input.tools_requested:
        combination = "tools_only"
    elif not structured_requested and not output_input.tools_requested:
        combination = "plain_text"
    else:
        combination = "incompatible"

    return ResolvedOutputMode(
        structured_output_requested=structured_requested,
        expected_output_name=output_input.expected_output_name,
        requested_structured_output_mode=requested_structured_mode,
        tools_requested=output_input.tools_requested,
        requested_tool_mode=output_input.requested_tool_mode,
        effective_structured_output_mode=effective_structured_mode,
        effective_tool_mode=effective_tool_mode,
        combination=combination,
        resolution_reason=resolution_reason,
    )

