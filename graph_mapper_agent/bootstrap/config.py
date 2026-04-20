from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class GraphMapperConfig:
    entry_url: str
    goal: str
    max_hops: int = 250
    max_pages: int = 500
    decision_mode: str = "heuristic"
    allow_artifact_download: bool = True
    allow_artifact_open: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.entry_url.strip():
            raise ValueError("GraphMapperConfig.entry_url no puede ir vacío.")
        if not self.goal.strip():
            raise ValueError("GraphMapperConfig.goal no puede ir vacío.")
        if self.max_hops <= 0:
            raise ValueError("GraphMapperConfig.max_hops debe ser > 0.")
        if self.max_pages <= 0:
            raise ValueError("GraphMapperConfig.max_pages debe ser > 0.")
        if self.decision_mode not in {"heuristic", "llm"}:
            raise ValueError(
                "GraphMapperConfig.decision_mode debe ser 'heuristic' o 'llm'."
            )

    @classmethod
    def from_json_dict(cls, data: Mapping[str, Any]) -> "GraphMapperConfig":
        return cls(
            entry_url=str(data.get("entry_url") or "").strip(),
            goal=str(data.get("goal") or "").strip(),
            max_hops=int(data.get("max_hops") or 20),
            max_pages=int(data.get("max_pages") or 200),
            decision_mode=str(data.get("decision_mode") or "heuristic").strip(),
            allow_artifact_download=bool(data.get("allow_artifact_download", True)),
            allow_artifact_open=bool(data.get("allow_artifact_open", True)),
            metadata=dict(data.get("metadata") or {}),
        )


__all__ = ["GraphMapperConfig"]
