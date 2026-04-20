from __future__ import annotations
#graph_mapper_agent/runtime/state/navigation.py
from dataclasses import dataclass

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import GraphMapperState


@dataclass(slots=True)
class NavigationPerceptionRefineState:
    node_id: str
    explicit_runs: int = 0
    last_context_signature: str | None = None
    last_result_signature: str | None = None
    last_explicit_refine_useful: bool | None = None
    can_refine: bool = True
    reason: str | None = None


def ensure_navigation_perception_refine_state(
    *,
    runtime: GraphMapperState,
    node_id: str,
    current_context_signature: str,
) -> NavigationPerceptionRefineState:
    refine_state = runtime.navigation_perception_refine_state_by_node.get(node_id)
    if refine_state is None:
        refine_state = NavigationPerceptionRefineState(
            node_id=node_id,
            can_refine=True,
            reason="refine_navigation_perception_disponible",
        )
        runtime.navigation_perception_refine_state_by_node[node_id] = refine_state
        return refine_state

    if (
        refine_state.last_context_signature
        and refine_state.last_context_signature != current_context_signature
    ):
        refine_state.can_refine = True
        refine_state.reason = (
            "el_contexto_estructural_del_nodo_cambio_desde_el_ultimo_refine"
        )

    if refine_state.last_context_signature is None:
        refine_state.last_context_signature = current_context_signature

    return refine_state


__all__ = [
    "NavigationPerceptionRefineState",
    "ensure_navigation_perception_refine_state",
]
