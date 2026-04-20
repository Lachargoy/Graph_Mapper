from dataclasses import dataclass
#bootstrap/dto.py
from .config import GraphMapperConfig
from .execution_config import GuidedGraphMapperConfig


@dataclass(frozen=True)
class RunGraphMapperInput:
    request: GraphMapperConfig
    execution: GuidedGraphMapperConfig
    mock_observations: dict[str, dict[str, object]] | None = None
