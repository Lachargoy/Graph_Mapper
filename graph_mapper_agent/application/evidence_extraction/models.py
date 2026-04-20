from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


EvidenceCarrier = Literal["pdf", "html", "text", "image", "screenshot", "unknown"]
EvidenceKind = Literal["text_page", "rendered_page", "inline_text", "unknown"]
VisualExtractionStrategy = Literal[
    "prefer_vision",
    "prefer_ocr",
    "vision_then_ocr_fallback",
    "ocr_then_vision_fallback",
]

CoverageStatus = Literal["partial", "substantial", "complete"]


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    local_path: str | None = None
    source_url: str | None = None
    media_type: str | None = None
    filename: str | None = None
    inline_text: str | None = None
    screenshot_base64: str | None = None
    screenshot_mime_type: str | None = None

    def infer_carrier(self) -> EvidenceCarrier:
        local_path = (self.local_path or "").strip().lower()
        media_type = (self.media_type or "").strip().lower()
        if local_path.endswith(".pdf") or media_type == "application/pdf":
            return "pdf"
        if self.inline_text:
            if "html" in media_type:
                return "html"
            return "text"
        if self.screenshot_base64:
            return "screenshot"
        if media_type.startswith("image/"):
            return "image"
        return "unknown"


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_kind: EvidenceKind
    carrier: EvidenceCarrier
    page_number: int | None = None
    text: str | None = None
    mime_type: str | None = None
    content_base64: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceCoverageAssessment:
    coverage_status: CoverageStatus
    primary_content_detected: bool
    sufficiency_for_goal_validation: bool
    rationale: str
    missing_content_signals: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceExtractionRequest:
    artifact: EvidenceArtifact
    max_pages: int = 3
    page_numbers: tuple[int, ...] | None = None
    include_text: bool = True
    include_rendered_pages: bool = False
    visual_strategy: VisualExtractionStrategy = "prefer_vision"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvidenceExtractionResult:
    carrier: EvidenceCarrier
    items: tuple[EvidenceItem, ...] = ()
    coverage_assessment: EvidenceCoverageAssessment | None = None
    metadata: dict[str, object] = field(default_factory=dict)
