from __future__ import annotations
#graph_mapper_agent/application/services/execution/contracts.py
from dataclasses import dataclass

from graph_mapper_agent.application.local_perception.models import (
    LocalPerceptionResult,
)


@dataclass(slots=True, frozen=True)
class ActionExecutionResult:
    action: str
    status: str
    edge_id: str | None = None
    child_node_id: str | None = None
    inspection_result: dict[str, object] | None = None
    download_result: dict[str, object] | None = None
    artifact_result: dict[str, object] | None = None
    local_perception_result: LocalPerceptionResult | None = None
    search_target_id: str | None = None
    query_text: str | None = None
    reason: str | None = None
