from __future__ import annotations

from graph_mapper_agent.domain.exploration_scope import (
    ExplorationScopeState,
)
from graph_mapper_agent.runtime.state import GraphMapperState


def get_runtime_state(state: dict[str, object]) -> GraphMapperState:
    runtime = state.get("runtime")
    if not isinstance(runtime, GraphMapperState):
        from graph_mapper_agent.domain.graph import GraphMemory

        runtime = GraphMapperState(
            graph=GraphMemory(),
            max_steps=int(state.get("max_steps") or 256),
        )
        state["runtime"] = runtime
    return runtime


def require_active_scope(runtime: GraphMapperState) -> ExplorationScopeState:
    scope = runtime.get_active_scope()
    if scope is None:
        raise ValueError("graph_mapper has no active scope")
    return scope


def require_current_node(runtime: GraphMapperState):
    if not runtime.current_node_id:
        raise ValueError("graph_mapper has no current_node_id")
    node = runtime.graph.get_node(runtime.current_node_id)
    if node is None:
        raise ValueError(f"Current node does not exist: {runtime.current_node_id}")
    return node


__all__ = [
    "get_runtime_state",
    "require_active_scope",
    "require_current_node",
]
