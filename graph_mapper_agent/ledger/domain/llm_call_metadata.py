from dataclasses import dataclass


@dataclass(frozen=True)
class LlmCallMetadata:
    provider: str
    model: str
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
