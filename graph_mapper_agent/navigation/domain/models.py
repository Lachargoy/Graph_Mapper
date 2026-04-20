from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


NavigationAction = Literal[
    "follow_link",
    "download_artifact",
    "open_artifact",
    "go_back",
    "success",
    "fail",
]

CandidateType = Literal[
    "page",
    "artifact",
    "unknown",
]


@dataclass(frozen=True)
class NavigationCandidate:
    url: str
    text: str | None = None
    source_page_url: str | None = None
    candidate_type: CandidateType = "unknown"
    relation: str = "unknown"
    score: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    def normalized_url(self) -> str:
        return self.url.strip()

    def is_page(self) -> bool:
        return self.candidate_type == "page"

    def is_artifact(self) -> bool:
        return self.candidate_type == "artifact"

    def to_payload(self) -> dict[str, object]:
        return {
            "url": self.url,
            "text": self.text,
            "source_page_url": self.source_page_url,
            "candidate_type": self.candidate_type,
            "relation": self.relation,
            "score": self.score,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class NavigationDecision:
    action: NavigationAction
    candidate_index: int | None = None
    reason: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def has_candidate(self) -> bool:
        return self.candidate_index is not None

    def to_payload(self) -> dict[str, object]:
        return {
            "action": self.action,
            "candidate_index": self.candidate_index,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class NavigationPageObservation:
    page_url: str
    final_url: str | None = None
    title: str | None = None
    content: str | None = None
    links: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def resolved_url(self) -> str:
        return (self.final_url or self.page_url).strip()

    def to_payload(self) -> dict[str, object]:
        return {
            "page_url": self.page_url,
            "final_url": self.final_url,
            "title": self.title,
            "content": self.content,
            "links": list(self.links),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class NavigationPageAnalysis:
    page_type: str
    confidence: float
    diagnostics: dict[str, object] = field(default_factory=dict)
    candidates: list[NavigationCandidate] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "page_type": self.page_type,
            "confidence": self.confidence,
            "diagnostics": dict(self.diagnostics),
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ArtifactDownloadResult:
    source_url: str
    final_url: str | None = None
    filename: str | None = None
    content_type: str | None = None
    storage_ref: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def resolved_url(self) -> str:
        return (self.final_url or self.source_url).strip()

    def to_payload(self) -> dict[str, object]:
        return {
            "source_url": self.source_url,
            "final_url": self.final_url,
            "filename": self.filename,
            "content_type": self.content_type,
            "storage_ref": self.storage_ref,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ArtifactInspectionResult:
    artifact_url: str
    artifact_kind: str = "unknown"
    valid: bool = True
    diagnostics: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "artifact_url": self.artifact_url,
            "artifact_kind": self.artifact_kind,
            "valid": self.valid,
            "diagnostics": dict(self.diagnostics),
            "metadata": dict(self.metadata),
        }

