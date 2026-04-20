from __future__ import annotations

from typing import Protocol

from graph_mapper_agent.application.navigation_perception.models import (
    NavigationPerceptionRequest,
    NavigationPerceptionResult,
)


class NavigationPerceptionExecutorPort(Protocol):
    def perceive(self, request: NavigationPerceptionRequest) -> NavigationPerceptionResult: ...
