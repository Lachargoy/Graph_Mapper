from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from graph_mapper_agent.navigation.domain.models import (
    NavigationCandidate,
    NavigationDecision,
    NavigationPageAnalysis,
    NavigationPageObservation,
)
from graph_mapper_agent.navigation.domain.state import (
    NavigationAgentState,
)


@dataclass
class NavigationStepContext:
    agent_state: NavigationAgentState
    current_page_url: str | None = None
    current_hop_depth: int = 0
    inspection_metadata: dict[str, Any] = field(default_factory=dict)
    frame_summaries: list[dict[str, Any]] = field(default_factory=list)
    strategy_state: object | None = None


@runtime_checkable
class NavigationStrategy(Protocol):
    def initial_strategy_state(self) -> object | None: ...

    def on_page_observed(
        self,
        *,
        context: NavigationStepContext,
        page_content: str,
        inspection_metadata: dict[str, Any],
    ) -> tuple[object | None, str | None]: ...

    def on_no_page_stack(
        self,
        *,
        context: NavigationStepContext,
    ) -> tuple[object | None, str]: ...

    def on_no_candidates(
        self,
        *,
        context: NavigationStepContext,
    ) -> tuple[object | None, str]: ...

    def on_repeated_state(
        self,
        *,
        context: NavigationStepContext,
        repeat_count: int,
    ) -> tuple[object | None, str]: ...

    def filter_candidates(
        self,
        *,
        context: NavigationStepContext,
        candidates: list[dict[str, Any]],
    ) -> tuple[object | None, list[dict[str, Any]], str | None]: ...

    def select_candidate(
        self,
        *,
        context: NavigationStepContext,
        filtered_candidates: list[dict[str, Any]],
    ) -> tuple[object | None, str, dict[str, Any] | None, str]: ...

    def follow_candidate(
        self,
        *,
        context: NavigationStepContext,
        candidate: dict[str, Any],
    ) -> tuple[object | None, str, object | None, str]: ...

    def handle_download_exception(
        self,
        *,
        context: NavigationStepContext,
        candidate: dict[str, Any],
        error: Exception,
    ) -> tuple[object | None, str, str]: ...

    def validate_download(
        self,
        *,
        context: NavigationStepContext,
        candidate: dict[str, Any],
        download_result: dict[str, Any],
    ) -> tuple[object | None, bool, str]: ...

    def go_back(
        self,
        *,
        context: NavigationStepContext,
    ) -> tuple[object | None, str]: ...


@dataclass
class RichNavigationStepContext:
    agent_state: NavigationAgentState
    current_page_url: str | None = None
    current_hop_depth: int = 0
    observation: NavigationPageObservation | None = None
    page_analysis: NavigationPageAnalysis | None = None
    strategy_state: object | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class RichNavigationStrategy(Protocol):
    def initial_strategy_state(self) -> object | None: ...

    def decide_next_action(
        self,
        *,
        context: RichNavigationStepContext,
        candidates: list[NavigationCandidate],
    ) -> NavigationDecision: ...

