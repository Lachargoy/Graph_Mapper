#./adapters/llm/composition/runtime_factory.py
from __future__ import annotations

from dataclasses import dataclass

from graph_mapper_agent.platform.llm.runtime_plan import (
    ResolvedRuntimePlan,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimePort,
)

from graph_mapper_agent.adapters.llm.runtimes.providers.pydantic_ai_lm_studio_adapter import (
    PydanticAiLmStudioAdapter,
    PydanticAiLmStudioSettings,
)
from graph_mapper_agent.adapters.llm.runtimes.providers.pydantic_ai_openrouter_adapter import (
    PydanticAiOpenRouterAdapter,
    PydanticAiOpenRouterSettings,
)
from graph_mapper_agent.adapters.llm.runtimes.providers.ollama_native_adapter import (
    OllamaNativeAdapter,
    OllamaNativeSettings,
)


def _debug(msg: str) -> None:
    print(f"[runtime_factory] {msg}", flush=True)


@dataclass(frozen=True)
class LlmRuntimeFactoryResult:
    runtime: LlmRuntimePort
    backend: str
    provider_name: str
    runtime_family: str
    adapter_key: str
    plan: ResolvedRuntimePlan


def build_llm_runtime(plan: ResolvedRuntimePlan) -> LlmRuntimeFactoryResult:
    _debug(
        "build_llm_runtime "
        f"backend={plan.identity.backend_name!r} "
        f"provider={plan.identity.provider!r} "
        f"provider_name={plan.identity.provider_name!r} "
        f"adapter_key={plan.identity.adapter_key!r} "
        f"model={plan.model!r} "
        f"base_url={plan.base_url!r} "
        f"supports_vision={plan.supports_vision!r} "
        f"structured_output_mode={plan.output_mode.effective_structured_output_mode!r} "
        f"output_combination={plan.output_mode.combination!r} "
        f"reasoning_enabled={plan.reasoning.effective_enabled!r} "
        f"reasoning_effort={plan.reasoning.effective_effort!r} "
        f"reasoning_max_tokens={plan.reasoning.effective_max_tokens!r} "
        f"reasoning_exclude={plan.reasoning.effective_exclude!r} "
        f"provider_order={tuple(plan.provider_routing.order)!r} "
        f"provider_require_parameters={plan.provider_routing.require_parameters!r} "
        f"provider_allow_fallbacks={plan.provider_routing.allow_fallbacks!r}"
    )

    _validate_plan_for_factory(plan)

    adapter_key = plan.identity.adapter_key

    if adapter_key == "pydantic_ai_lm_studio":
        runtime = _build_pydantic_ai_lm_studio_runtime(plan)
    elif adapter_key == "pydantic_ai_openrouter":
        runtime = _build_pydantic_ai_openrouter_runtime(plan)
    elif adapter_key == "ollama_native":
        runtime = _build_ollama_native_runtime(plan)
    else:
        raise ValueError(
            f"Adapter key not supported by runtime_factory: {adapter_key!r}"
        )

    _debug(
        "build_llm_runtime_done "
        f"adapter_key={plan.identity.adapter_key!r} "
        f"provider_name={plan.identity.provider_name!r}"
    )

    return LlmRuntimeFactoryResult(
        runtime=runtime,
        backend=plan.identity.backend_name,
        provider_name=plan.identity.provider_name,
        runtime_family=plan.identity.runtime_family,
        adapter_key=plan.identity.adapter_key,
        plan=plan,
    )


def _validate_plan_for_factory(plan: ResolvedRuntimePlan) -> None:
    _debug(
        "_validate_plan_for_factory "
        f"backend={plan.identity.backend_name!r} "
        f"provider={plan.identity.provider!r} "
        f"adapter_key={plan.identity.adapter_key!r} "
        f"model={plan.model!r}"
    )

    if not plan.identity.backend_name.strip():
        raise ValueError("ResolvedRuntimePlan.identity.backend_name cannot be empty.")

    if not plan.identity.provider.strip():
        raise ValueError("ResolvedRuntimePlan.identity.provider cannot be empty.")

    if not plan.identity.adapter_key.strip():
        raise ValueError("ResolvedRuntimePlan.identity.adapter_key cannot be empty.")

    if not plan.model.strip():
        raise ValueError("ResolvedRuntimePlan.model cannot be empty.")

    if plan.output_mode.combination == "incompatible":
        raise ValueError(
            "ResolvedRuntimePlan arrived with incompatible output_mode. "
            f"reason={plan.output_mode.resolution_reason!r}"
        )

    if (
        plan.identity.provider == "openrouter"
        and (plan.api_key is None or not str(plan.api_key).strip())
    ):
        raise ValueError("OpenRouter requires api_key in the resolved plan.")


def _build_pydantic_ai_lm_studio_runtime(
    plan: ResolvedRuntimePlan,
) -> LlmRuntimePort:
    settings = PydanticAiLmStudioSettings(
        backend_name=plan.identity.backend_name,
        base_url=plan.base_url,
        default_model=plan.model,
        supports_vision=plan.supports_vision,
        structured_output_mode=(
            plan.output_mode.effective_structured_output_mode or "auto"
        ),
    )

    _debug(
        "_build_pydantic_ai_lm_studio_runtime "
        f"settings={settings!r}"
    )

    return PydanticAiLmStudioAdapter(settings)


def _build_pydantic_ai_openrouter_runtime(
    plan: ResolvedRuntimePlan,
) -> LlmRuntimePort:
    settings = PydanticAiOpenRouterSettings(
        base_url=plan.base_url or "https://openrouter.ai/api/v1",
        default_model=plan.model,
        api_key=plan.api_key,
        backend_name=plan.identity.backend_name,
        supports_vision=plan.supports_vision,
        structured_output_mode=(
            plan.output_mode.effective_structured_output_mode or "auto"
        ),
        enable_reasoning=plan.reasoning.effective_enabled,
        reasoning_effort=plan.reasoning.effective_effort,
        reasoning_max_tokens=plan.reasoning.effective_max_tokens,
        reasoning_exclude=plan.reasoning.effective_exclude,
        provider_order=tuple(plan.provider_routing.order),
        provider_require_parameters=plan.provider_routing.require_parameters,
        provider_allow_fallbacks=plan.provider_routing.allow_fallbacks,
    )

    _debug(
        "_build_pydantic_ai_openrouter_runtime "
        f"base_url={settings.base_url!r} "
        f"default_model={settings.default_model!r} "
        f"backend_name={settings.backend_name!r} "
        f"supports_vision={settings.supports_vision!r} "
        f"structured_output_mode={settings.structured_output_mode!r} "
        f"enable_reasoning={settings.enable_reasoning!r} "
        f"reasoning_effort={settings.reasoning_effort!r} "
        f"reasoning_max_tokens={settings.reasoning_max_tokens!r} "
        f"reasoning_exclude={settings.reasoning_exclude!r} "
        f"provider_order={settings.provider_order!r} "
        f"provider_require_parameters={settings.provider_require_parameters!r} "
        f"provider_allow_fallbacks={settings.provider_allow_fallbacks!r}"
    )

    return PydanticAiOpenRouterAdapter(settings)


def _build_ollama_native_runtime(
    plan: ResolvedRuntimePlan,
) -> LlmRuntimePort:
    settings = OllamaNativeSettings(
        base_url=plan.base_url or "http://127.0.0.1:11434",
        default_model=plan.model,
        api_key=plan.api_key,
        timeout_seconds=int(plan.metadata.get("timeout_seconds") or 180),
        backend_name=plan.identity.backend_name,
        supports_vision=plan.supports_vision,
        structured_output_mode=(
            plan.output_mode.effective_structured_output_mode or "prompted"
        ),
    )
    _debug(
        "_build_ollama_native_runtime "
        f"base_url={settings.base_url!r} "
        f"default_model={settings.default_model!r} "
        f"backend_name={settings.backend_name!r} "
        f"supports_vision={settings.supports_vision!r} "
        f"structured_output_mode={settings.structured_output_mode!r}"
    )
    return OllamaNativeAdapter(settings)
