from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GoalValidationArtifact:
    local_path: str | None = None
    source_url: str | None = None
    media_type: str | None = None
    filename: str | None = None
    inline_text: str | None = None
    screenshot_base64: str | None = None
    screenshot_mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class TextPageEvidence:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class RenderedPageEvidence:
    page_number: int
    mime_type: str
    content_base64: str
