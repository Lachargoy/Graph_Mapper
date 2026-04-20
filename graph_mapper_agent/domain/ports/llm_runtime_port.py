from dataclasses import dataclass, field
from typing import Any, Protocol

from graph_mapper_agent.ledger.domain.llm_call_metadata import (
    LlmCallMetadata,
)
from graph_mapper_agent.ledger.domain.llm_interaction import (
    LlmInteraction,
)


@dataclass(frozen=True)
class LlmRuntimeRequest:
    """
    Input contract for an LLM call within Aither.

    This object does not yet represent a specific provider. Its function
    is to express, from the domain layer, what operation Aither is trying to execute,
    with which messages and what minimum output expectation.
    """

    # Semantic name of the operation Aither is trying to resolve.
    operation_name: str

    # Effective messages to be sent to the model.
    messages: tuple[dict[str, Any], ...]

    # Name of the expected contract when the output should be
    # structured.
    expected_output_name: str | None = None

    # Optional suggestion for the model to use.
    model_hint: str | None = None

    # Common technical sampling parameter.
    temperature: float | None = None

    # Auxiliary space for prompt versions, hashes, artifact IDs, etc.
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.operation_name.strip():
            raise ValueError("LlmRuntimeRequest requires a non-empty 'operation_name'.")
        if not self.messages:
            raise ValueError("LlmRuntimeRequest requires at least one message.")


@dataclass(frozen=True)
class LlmRuntimeResponse:
    """
    Normalized output of an LLM call in Aither.
    """

    # Input, expected output, observed response, and validation.
    interaction: LlmInteraction

    # Provider, model, prompt hash, tokens, and latency.
    metadata: LlmCallMetadata

    # Optional raw response from the provider.
    raw_response: dict[str, Any] | None = None


@dataclass
class LlmRuntimeError(Exception):
    """
    Normalized error from the LLM track.
    """

    error_class: str
    message: str
    retryable: bool = False

    def __post_init__(self) -> None:
        if not self.error_class.strip():
            raise ValueError("LlmRuntimeError requires a non-empty 'error_class'.")
        if not self.message.strip():
            raise ValueError("LlmRuntimeError requires a non-empty 'message'.")

    def __str__(self) -> str:
        return f"{self.error_class}: {self.message}"


class LlmRuntimePort(Protocol):
    """
    Abstract contract for executing an LLM call in Aither.
    """

    def invoke(
        self,
        request: LlmRuntimeRequest,
    ) -> LlmRuntimeResponse:
        """
        Executes a normalized LLM call.
        """
        ...