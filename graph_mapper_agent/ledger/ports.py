from typing import Protocol
#graph_mapper_agent/ledger/ports.py
from .domain.actor_kind import ActorKind
from .domain.event_payloads import (
    LlmCalledPayload,
    LlmCompletedPayload,
    LlmValidationFailedPayload,
    NodeExecutedPayload,
    OverrideAppliedPayload,
    RetryScheduledPayload,
    RunCompletedPayload,
    RunFailedPayload,
    RunStartedPayload,
    ToolFailedPayload,
)
from .domain.ledger_event import LedgerEvent
from .domain.llm_call_metadata import LlmCallMetadata
from .domain.llm_interaction import LlmInteraction
from .domain.run_correlation import RunCorrelation
from .domain.target_ref import TargetRef


class LedgerWritePort(Protocol):
    def append_event(self, event: LedgerEvent | None = None, **kwargs: object) -> object: ...

    def record_run_started(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: RunStartedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_run_completed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: RunCompletedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_run_failed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: RunFailedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_node_executed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: NodeExecutedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_llm_called(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: LlmCalledPayload,
        llm: LlmCallMetadata,
        llm_io: LlmInteraction | None = None,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_llm_completed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: LlmCompletedPayload,
        llm: LlmCallMetadata,
        llm_io: LlmInteraction | None = None,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_llm_validation_failed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: LlmValidationFailedPayload,
        llm: LlmCallMetadata,
        llm_io: LlmInteraction | None = None,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_tool_failed(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: ToolFailedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_retry_scheduled(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: RetryScheduledPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    def record_override_applied(
        self,
        event_id: str,
        run: RunCorrelation,
        actor: ActorKind,
        payload: OverrideAppliedPayload,
        target: TargetRef | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None: ...
