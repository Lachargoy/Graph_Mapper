from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LlmInteraction:
    input: dict[str, Any] = field(default_factory=dict)
    expected_output: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "expected_output": self.expected_output,
            "response": self.response,
            "validation": self.validation,
        }
