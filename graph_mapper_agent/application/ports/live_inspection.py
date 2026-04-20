#graph_mapper_agent/application/ports/live_inspection.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class LiveInspectionRequest:
    url: str
    question: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    include_screenshot: bool = False
    max_candidates: int = 600


class LiveInspectionPort(Protocol):
    def inspect_live(
        self,
        request: LiveInspectionRequest,
    ) -> dict[str, Any]:
        ...