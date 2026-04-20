from __future__ import annotations

import time
from typing import Any

from graph_mapper_agent.adapters.llm.runtimes.base.callable_llm_runtime_adapter import RawLlmResult
from graph_mapper_agent.adapters.llm.runtimes.base.serialization import (
    coerce_optional_str,
    finish_reason_from_result,
    reasoning_payload,
    response_text_from_output,
    serialize_messages,
    serialize_output,
    serialize_value,
    usage_payload,
)
from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeRequest,
    LlmRuntimeResponse,
)


def build_success_result(
    *,
    result: Any,
    request: LlmRuntimeRequest,
    model_name: str,
    output_type: type,
    image_count: int,
    started_at: float,
    settings: object,
) -> RawLlmResult:
    _ = (time.perf_counter() - started_at) * 1000.0
    output_payload = serialize_output(getattr(result, "output", None))
    agent_response = serialize_value(getattr(result, "response", None))
    agent_metadata = serialize_value(getattr(result, "metadata", None))
    all_messages = serialize_messages(result, "all_messages")
    new_messages = serialize_messages(result, "new_messages")
    reasoning = reasoning_payload(
        agent_response=agent_response,
        agent_metadata=agent_metadata,
        all_messages=all_messages,
        new_messages=new_messages,
    )
    finish_reason = finish_reason_from_result(
        agent_response=agent_response,
        new_messages=new_messages,
        all_messages=all_messages,
    )
    usage = usage_payload(getattr(result, "usage", None))

    raw_response: dict[str, Any] = {
        "provider": settings.provider_name,
        "backend": settings.backend_name,
        "model": model_name,
        "output_type": getattr(output_type, "__name__", str(output_type)),
        "structured_output_mode": settings.structured_output_mode,
        "supports_vision": settings.supports_vision,
        "reasoning_enabled": settings.reasoning_enabled,
        "reasoning_effort": settings.reasoning_effort,
        "reasoning_max_tokens": settings.reasoning_max_tokens,
        "reasoning_exclude": settings.reasoning_exclude,
        "provider_order": list(settings.provider_order),
        "image_count": image_count,
        "output": output_payload,
        "usage": usage,
        "agent_response": agent_response,
        "agent_metadata": agent_metadata,
        "all_messages": all_messages,
        "new_messages": new_messages,
    }

    response_message: dict[str, Any] = {
        "role": "assistant",
        "content": response_text_from_output(output_payload),
    }
    if reasoning is not None:
        response_message["reasoning_details"] = reasoning

    validation: dict[str, Any] = {
        "valid": True,
        "errors": [],
        "parsed_response": output_payload,
        "mode": "pydantic_ai_structured_output",
        "expected_output_name": request.expected_output_name,
        "structured_output_mode": settings.structured_output_mode,
    }

    return RawLlmResult(
        model=model_name,
        response={
            "message": response_message,
            "finish_reason": finish_reason,
            "parsed_response": output_payload,
            "reasoning_enabled": settings.reasoning_enabled,
            "reasoning_details_present": reasoning is not None,
        },
        validation=validation,
        prompt_version=coerce_optional_str(request.metadata.get("prompt_version")),
        prompt_hash=coerce_optional_str(request.metadata.get("prompt_hash")),
        structured_output_name=request.expected_output_name,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        reasoning_tokens=usage.get("reasoning_tokens"),
        cached_tokens=usage.get("cached_tokens"),
        total_tokens=usage.get("total_tokens"),
        raw_response=raw_response,
    )


def raw_result_from_response(response: LlmRuntimeResponse) -> RawLlmResult:
    meta = response.metadata
    interaction = response.interaction
    return RawLlmResult(
        model=meta.model,
        response=interaction.response,
        validation=interaction.validation,
        prompt_version=meta.prompt_version,
        prompt_hash=meta.prompt_hash,
        structured_output_name=meta.structured_output_name,
        tool_choice=meta.tool_choice,
        input_tokens=meta.input_tokens,
        output_tokens=meta.output_tokens,
        reasoning_tokens=getattr(meta, "reasoning_tokens", None),
        cached_tokens=meta.cached_tokens,
        total_tokens=meta.total_tokens,
        latency_ms=meta.latency_ms,
        raw_response=response.raw_response,
    )
