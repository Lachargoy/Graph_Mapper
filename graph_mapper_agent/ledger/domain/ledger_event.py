from dataclasses import dataclass, field
from datetime import datetime, timezone
#graph_mapper_agent/ledger/domain/ledger_event.py
from .actor_kind import ActorKind
from .event_payloads import EventPayload, validate_payload_for_event
from .event_type import EventType
from .llm_call_metadata import LlmCallMetadata
from .llm_interaction import LlmInteraction
from .run_correlation import RunCorrelation
from .target_ref import TargetRef


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    event_type: EventType
    run: RunCorrelation
    actor: ActorKind
    payload: EventPayload
    target: TargetRef | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    llm: LlmCallMetadata | None = None
    llm_io: LlmInteraction | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("LedgerEvent requiere `event_id` no vacio.")
        validate_payload_for_event(self.event_type, self.payload)
