from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class FindingKind(str, Enum):
    DOCUMENT = "document"
    SESSION = "session"
    INDEX = "index"
    DATE = "date"
    PERSON = "person"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class FindingEvidence:
    source_node_id: str
    source_url: str
    edge_id: str | None = None
    snippet: str = ""


@dataclass(slots=True)
class FindingRecord:
    finding_id: str
    kind: FindingKind = FindingKind.UNKNOWN
    label: str = ""
    value: str = ""
    confidence: float = 0.0
    evidence: tuple[FindingEvidence, ...] = ()
    attributes: dict[str, object] = field(default_factory=dict)
