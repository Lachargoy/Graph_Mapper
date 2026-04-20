from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TargetRef:
    target_kind: str
    target_id: str
    context: dict[str, Any] = field(default_factory=dict)
