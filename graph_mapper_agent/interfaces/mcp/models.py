from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class McpAgentRequest:
    method_name: str
    input_data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.method_name.strip():
            raise ValueError("McpAgentRequest requiere `method_name` no vacio.")


@dataclass(frozen=True)
class McpAgentResponse:
    output_data: dict[str, Any]
    raw_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class McpAgentError(Exception):
    error_class: str
    message: str
    retryable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.error_class.strip():
            raise ValueError("McpAgentError requiere `error_class` no vacio.")
        if not self.message.strip():
            raise ValueError("McpAgentError requiere `message` no vacio.")

    def __str__(self) -> str:
        return f"{self.error_class}: {self.message}"
