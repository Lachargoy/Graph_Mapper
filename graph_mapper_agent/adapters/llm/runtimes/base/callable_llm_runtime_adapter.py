from __future__ import annotations
#aither/adapters/llm/runtimes/base/callable_llm_runtime_adapter.py
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping

from graph_mapper_agent.domain.ports.llm_runtime_port import (
    LlmRuntimeError,
    LlmRuntimePort,
    LlmRuntimeRequest,
    LlmRuntimeResponse,
)
from graph_mapper_agent.ledger.domain.llm_call_metadata import (
    LlmCallMetadata,
)
from graph_mapper_agent.ledger.domain.llm_interaction import (
    LlmInteraction,
)


@dataclass(frozen=True)
class RawLlmResult:
    """
    Normalized raw result before being converted to domain objects.

    This shape lives in adapters because it already describes the edge with a
    concrete implementation. The domain should not depend on it.
    """

    model: str
    response: Mapping[str, Any]
    validation: Mapping[str, Any] | None = None
    prompt_version: str | None = None
    prompt_hash: str | None = None
    structured_output_name: str | None = None
    tool_choice: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    cached_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    raw_response: Mapping[str, Any] | None = None


class CallableLlmRuntimeAdapter(LlmRuntimePort):
    """
    Minimal LLM lane adapter based on an injected function.

    Serves as the first real implementation of `LlmRuntimePort` without
    coupling Aither to a specific SDK yet. The injected function
    can be a test fake, an OpenAI wrapper, or a later integration
    with PydanticAI.
    """

    def __init__(
        self,
        provider_name: str,
        invoke_callable: Callable[[LlmRuntimeRequest], RawLlmResult],
    ) -> None:
        if not provider_name.strip():
            raise ValueError("CallableLlmRuntimeAdapter requires a non-empty `provider_name`.")
        self._provider_name = provider_name
        self._invoke_callable = invoke_callable

    def invoke(
        self,
        request: LlmRuntimeRequest,
    ) -> LlmRuntimeResponse:
        started_at = perf_counter()

        try:
            result = self._invoke_callable(request)
        except LlmRuntimeError:
            raise
        except Exception as exc:  # pragma: no cover - defensive boundary
            raise LlmRuntimeError(
                error_class=exc.__class__.__name__,
                message=str(exc) or "Unhandled error from the LLM adapter.",
                retryable=False,
            ) from exc

        latency_ms = result.latency_ms
        if latency_ms is None:
            latency_ms = int((perf_counter() - started_at) * 1000)

        interaction = LlmInteraction(
            input={
                "messages": [dict(message) for message in request.messages],
                "metadata": dict(request.metadata),
            },
            expected_output={
                "name": request.expected_output_name,
            },
            response=dict(result.response),
            validation=dict(result.validation or {}),
        )

        metadata = LlmCallMetadata(
            provider=self._provider_name,
            model=result.model,
            prompt_version=result.prompt_version,
            prompt_hash=result.prompt_hash,
            structured_output_name=(
                result.structured_output_name or request.expected_output_name
            ),
            tool_choice=result.tool_choice,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            reasoning_tokens=result.reasoning_tokens,
            cached_tokens=result.cached_tokens,
            total_tokens=result.total_tokens,
            latency_ms=latency_ms,
        )

        raw_response = (
            None if result.raw_response is None else dict(result.raw_response)
        )

        return LlmRuntimeResponse(
            interaction=interaction,
            metadata=metadata,
            raw_response=raw_response,
        )
