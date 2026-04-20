from __future__ import annotations

from typing import Protocol

from graph_mapper_agent.application.local_perception.models import (
    LocalPerceptionRequest,
    LocalPerceptionResult,
)


class LocalPerceptionServicePort(Protocol):
    def perceive(self, request: LocalPerceptionRequest) -> LocalPerceptionResult: ...
