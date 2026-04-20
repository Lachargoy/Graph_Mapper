from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphMapperResult:
    final_state: dict[str, object]
    final_status: str | None


__all__ = ["GraphMapperResult"]
