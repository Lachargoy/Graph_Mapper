from __future__ import annotations
#graph_mapper_agent/runtime/nodes/observation.py
from graph_mapper_agent.application.ports.navigation_actions import (
    InspectPageRequest,
    NavigationActionsPort,
)
from graph_mapper_agent.domain.graph import ObservedCandidate


def get_observation_for_current_node(
    *,
    state: dict[str, object],
    current_url: str,
    navigation_actions: NavigationActionsPort,
    jurisdiction_code: str,
    document_key: str,
    timeout_seconds: int,
    include_screenshot: bool,
) -> dict[str, object]:
    mock_observations = dict(state.get("mock_observations") or {})
    observation = mock_observations.get(current_url)
    if observation is not None:
        print(
            f"[nodes.observe] using mock observation for url={current_url!r}",
            flush=True,
        )
        return dict(observation)

    print(
        f"[nodes.observe] invoking inspect_page for url={current_url!r}",
        flush=True,
    )

    raw = navigation_actions.inspect_page(
        InspectPageRequest(
            jurisdiction_code=jurisdiction_code,
            document_key=document_key,
            entry_url=current_url,
            timeout_seconds=timeout_seconds,
            include_screenshot=include_screenshot,
            metadata={
                "include_screenshot": include_screenshot,
            },
        )
    )

    if not isinstance(raw, dict):
        raise TypeError("inspect_page(...) debe regresar dict[str, object]")

    print(
        "[nodes.observe] inspect_page returned "
        f"candidate_count={len(list(raw.get('candidates') or []))} "
        f"search_target_count={len(list(raw.get('search_targets') or []))}",
        flush=True,
    )

    return {
        "candidates": list(raw.get("candidates") or []),
        "search_targets": list(raw.get("search_targets") or []),
        "page_url": str(raw.get("page_url") or current_url),
        "final_url": raw.get("final_url"),
        "title": raw.get("title") or raw.get("page_title"),
        "content": raw.get("content"),
        "text_excerpt": raw.get("text_excerpt"),
        "screenshot_base64": raw.get("screenshot_base64"),
        "screenshot_mime_type": raw.get("screenshot_mime_type"),
        "inspection_metadata": dict(
            raw.get("inspection_metadata")
            or raw.get("metadata")
            or {}
        ),
        "metadata": dict(raw.get("metadata") or {}),
        "frame_summaries": list(raw.get("frame_summaries") or []),
    }


def build_observed_candidate(
    candidate: dict[str, object],
    *,
    source_channel: str,
) -> ObservedCandidate:
    metadata = (
        candidate.get("metadata") if isinstance(candidate.get("metadata"), dict) else {}
    )
    source_frame = optional_str(
        candidate.get("source_frame")
        or candidate.get("frame_name")
        or metadata.get("source_frame")
        or metadata.get("frame_name")
    )
    return ObservedCandidate(
        target_url=str(candidate.get("url") or "").strip(),
        label=str(
            candidate.get("semantic_label")
            or candidate.get("label")
            or candidate.get("text")
            or candidate.get("url")
            or ""
        ).strip(),
        relation=str(candidate.get("relation") or "unknown"),
        candidate_type=str(candidate.get("candidate_type") or "unknown"),
        resource_kind=optional_str(
            candidate.get("resource_kind") or metadata.get("resource_kind")
        ),
        delivery_mode=optional_str(
            candidate.get("delivery_mode") or metadata.get("delivery_mode")
        ),
        semantic_label=optional_str(
            candidate.get("semantic_label") or metadata.get("semantic_label")
        ),
        table_heading=optional_str(
            candidate.get("table_heading") or metadata.get("table_heading")
        ),
        adjacent_cell_text=optional_str(
            candidate.get("adjacent_cell_text") or metadata.get("adjacent_cell_text")
        ),
        same_host=optional_bool(
            candidate.get("same_host")
            if candidate.get("same_host") is not None
            else metadata.get("same_host")
        ),
        base_score=optional_float(candidate.get("score")),
        source_channel=source_channel,
        source_frame=source_frame,
        metadata=dict(metadata),
    )


def optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "build_observed_candidate",
    "get_observation_for_current_node",
    "optional_bool",
    "optional_float",
    "optional_str",
]
