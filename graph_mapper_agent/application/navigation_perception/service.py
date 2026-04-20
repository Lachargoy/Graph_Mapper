from __future__ import annotations

from graph_mapper_agent.application.navigation_perception.models import (
    NavigationPerceptionRequest,
    NavigationPerceptionResult,
)
from graph_mapper_agent.application.navigation_perception.ports import (
    NavigationPerceptionExecutorPort,
)


class NavigationPerceptionService:
    def __init__(self, *, executor: NavigationPerceptionExecutorPort) -> None:
        self._executor = executor

    def perceive(self, request: NavigationPerceptionRequest) -> NavigationPerceptionResult:
        return self._executor.perceive(request)
