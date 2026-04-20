from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, ClassVar, Protocol
#graph_mapper_agent/ledger/domain/event_payloads.py
from .event_type import EventType


class EventPayload(Protocol):
    event_type: ClassVar[EventType]

    def to_dict(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class _EventPayloadBase:
    def to_dict(self) -> dict[str, Any]:
        return {
            item.name: _serialize_value(getattr(self, item.name))
            for item in fields(self)
        }


def _serialize_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: _serialize_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class RunStartedPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.RUN_STARTED
    trigger: str
    initial_phase: str = "queued"
    input_channels: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RunCompletedPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.RUN_COMPLETED
    final_phase: str
    summary: str
    suggestions_count: int = 0
    review_items_count: int = 0


@dataclass(frozen=True)
class RunFailedPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.RUN_FAILED
    error_class: str
    error_message: str
    failed_phase: str | None = None
    retriable: bool = False


@dataclass(frozen=True)
class NodeExecutedPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.NODE_EXECUTED
    node_name: str
    from_phase: str
    to_phase: str | None = None
    duration_ms: int | None = None
    produced_candidates: int = 0
    produced_suggestions: int = 0
    produced_review_items: int = 0


@dataclass(frozen=True)
class LlmCalledPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.LLM_CALLED
    operation_name: str
    request_kind: str
    expected_output_contract: str | None = None


@dataclass(frozen=True)
class LlmCompletedPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.LLM_COMPLETED
    operation_name: str
    finish_reason: str
    response_format_valid: bool
    retryable: bool = False


@dataclass(frozen=True)
class LlmValidationFailedPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.LLM_VALIDATION_FAILED
    operation_name: str
    validation_stage: str
    error_message: str
    retryable: bool = False


@dataclass(frozen=True)
class ToolFailedPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.TOOL_FAILED
    tool_name: str
    error_class: str
    error_message: str
    retryable: bool = False


@dataclass(frozen=True)
class RetryScheduledPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.RETRY_SCHEDULED
    reason: str
    next_attempt: int


@dataclass(frozen=True)
class OverrideAppliedPayload(_EventPayloadBase):
    event_type: ClassVar[EventType] = EventType.OVERRIDE_APPLIED
    override_kind: str
    note: str | None = None


def validate_payload_for_event(event_type: EventType, payload: EventPayload) -> None:
    payload_type = getattr(payload, "event_type", None)
    if payload_type != event_type:
        raise ValueError(
            f"Payload/event mismatch: {payload_type!r} != {event_type!r}"
        )
