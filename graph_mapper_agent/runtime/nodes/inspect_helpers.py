from __future__ import annotations
#graph_mapper_agent/runtime/nodes/inspect_helpers.py
from graph_mapper_agent.application.ports.navigation_actions import (
    NavigationActionsPort,
)
from graph_mapper_agent.runtime.nodes.observation import (
    build_observed_candidate,
    get_observation_for_current_node,
)
from graph_mapper_agent.runtime.state import GraphMapperState


def resolve_node_observation(
    *,
    state: dict[str, object],
    runtime: GraphMapperState,
    node,
    navigation_actions: NavigationActionsPort,
    jurisdiction_code: str,
    document_key: str,
    timeout_seconds: int,
    include_screenshot: bool,
) -> tuple[dict[str, object] | None, bool]:
    snapshot = runtime.resolve_node_observation_snapshot(node.node_id)
    has_snapshot = isinstance(snapshot, dict) and bool(snapshot)

    if node.inspected and not has_snapshot:
        return None, False

    if has_snapshot:
        observation = dict(snapshot)
        runtime.inspection_result_by_node[node.node_id] = dict(observation)
        print(
            f"[inspect_node_helpers] using frozen snapshot for {node.node_id!r}",
            flush=True,
        )
        return observation, True

    observation = get_observation_for_current_node(
        state=state,
        current_url=node.canonical_url,
        navigation_actions=navigation_actions,
        jurisdiction_code=jurisdiction_code,
        document_key=document_key,
        timeout_seconds=timeout_seconds,
        include_screenshot=include_screenshot,
    )
    runtime.inspection_result_by_node[node.node_id] = dict(observation)
    return observation, True


def unpack_inspection_payload(
    observation: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, object], list[object]]:
    candidates_raw = list(observation.get("candidates") or [])
    inspection_metadata = dict(
        observation.get("inspection_metadata")
        or observation.get("metadata")
        or {}
    )
    frame_summaries = list(observation.get("frame_summaries") or [])
    return candidates_raw, inspection_metadata, frame_summaries


def merge_observed_candidates(
    *,
    runtime: GraphMapperState,
    node,
    candidate_merge_policy,
    candidates_raw: list[dict[str, object]],
) -> tuple[tuple[str, ...], int]:
    observed_candidates = tuple(
        build_observed_candidate(candidate, source_channel="inspect_node")
        for candidate in candidates_raw
        if str(candidate.get("url") or "").strip()
    )

    merge_result = candidate_merge_policy.merge(
        graph=runtime.graph,
        node=node,
        observed_candidates=observed_candidates,
        observed_step=runtime.step_count,
    )
    edge_ids = tuple(merge_result.edge_ids)

    node.mark_inspected()
    return edge_ids, len(observed_candidates)


def build_empty_inspection_payload() -> dict[str, object]:
    return {
        "candidates": [],
        "inspection_metadata": {},
        "frame_summaries": [],
        "discovered_edge_ids": (),
    }


def build_inspection_payload(
    *,
    candidates_raw: list[dict[str, object]],
    inspection_metadata: dict[str, object],
    frame_summaries: list[object],
    edge_ids: tuple[str, ...],
) -> dict[str, object]:
    return {
        "candidates": candidates_raw,
        "inspection_metadata": inspection_metadata,
        "frame_summaries": frame_summaries,
        "discovered_edge_ids": edge_ids,
    }


__all__ = [
    "build_empty_inspection_payload",
    "build_inspection_payload",
    "merge_observed_candidates",
    "resolve_node_observation",
    "unpack_inspection_payload",
]
