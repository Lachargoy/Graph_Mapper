# application/contracts/validation_state.py
from dataclasses import dataclass, field

@dataclass(slots=True)
class DocumentValidationNodeState:
    node_id: str
    can_revalidate: bool = False
    reason: str | None = None
    validation_attempts: int = 0

    last_validation_status: str | None = None
    last_matched_condition_ids: tuple[str, ...] = ()
    last_source_action: str | None = None

    last_context_signature: str | None = None
    last_evidence_signature: str | None = None
    last_pending_signature: str | None = None

    seen_validation_keys: set[str] = field(default_factory=set)
    validated_evidence_signatures: set[str] = field(default_factory=set)