#graph_mapper_agent/application/ports/inspection_source.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class InspectionSourceRequest:
    url: str | None
    question: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    include_screenshot: bool = False
    max_candidates: int = 600


class InspectionSourcePort(Protocol):
    def resolve_for_perception(
        self,
        request: InspectionSourceRequest,
    ) -> dict[str, Any]:
        ...