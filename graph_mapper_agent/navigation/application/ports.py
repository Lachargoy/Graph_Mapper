from __future__ import annotations

from typing import Protocol

from graph_mapper_agent.navigation.domain.models import (
    ArtifactDownloadResult,
    ArtifactInspectionResult,
    NavigationCandidate,
    NavigationPageAnalysis,
    NavigationPageObservation,
)


class NavigationSupportPort(Protocol):
    def inspect_page(
        self,
        *,
        page_url: str,
    ) -> NavigationPageObservation: ...

    def download_artifact(
        self,
        *,
        candidate: NavigationCandidate,
    ) -> ArtifactDownloadResult: ...

    def open_artifact(
        self,
        *,
        download_result: ArtifactDownloadResult,
    ) -> ArtifactInspectionResult: ...


class NavigationClassifierPort(Protocol):
    def classify_page(
        self,
        *,
        observation: NavigationPageObservation,
    ) -> NavigationPageAnalysis: ...


class NavigationLedgerPort(Protocol):
    def append_event(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> object: ...

