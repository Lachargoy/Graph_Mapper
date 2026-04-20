#graph_mapper_agent/application/ports/navigation_actions.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class InspectPageRequest:
    jurisdiction_code: str
    document_key: str
    entry_url: str
    timeout_seconds: int
    include_screenshot: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SearchWithTextRequest:
    jurisdiction_code: str
    document_key: str
    entry_url: str
    search_target_id: str
    query_text: str
    timeout_seconds: int
    include_screenshot: bool = False


@dataclass(frozen=True)
class DownloadArtifactRequest:
    jurisdiction_code: str
    document_key: str
    candidate_url: str
    timeout_seconds: int
    storage_namespace: str | None = None
    session_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ProbeContentRequest:
    jurisdiction_code: str
    document_key: str
    url: str
    timeout_seconds: int = 30
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class OpenArtifactRequest:
    candidate_url: str
    original_path: str | None = None
    storage_ref: str | None = None


@dataclass(frozen=True)
class LiveInspectionRequest:
    url: str
    question: str = ""
    include_screenshot: bool = False
    max_candidates: int | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


class NavigationActionsPort(Protocol):
    def inspect_page(self, request: InspectPageRequest) -> dict[str, object]:
        ...

    def search_with_text(self, request: SearchWithTextRequest) -> dict[str, object]:
        ...

    def download_artifact(self, request: DownloadArtifactRequest) -> dict[str, object]:
        ...

    def open_artifact(self, request: OpenArtifactRequest) -> dict[str, object]:
        ...

    def probe_content(self, request: ProbeContentRequest) -> dict[str, object]:
        ...