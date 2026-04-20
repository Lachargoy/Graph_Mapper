from __future__ import annotations


def unpack_classification_payload(
    state: dict[str, object],
) -> tuple[list[dict[str, object]], dict[str, object], list[object]]:
    payload = dict(state.get("_inspection_payload") or {})
    candidates = list(payload.get("candidates") or [])
    inspection_metadata = dict(payload.get("inspection_metadata") or {})
    frame_summaries = list(payload.get("frame_summaries") or [])
    return candidates, inspection_metadata, frame_summaries


def classify_current_node(
    *,
    page_classifier,
    node,
    candidates: list[dict[str, object]],
    inspection_metadata: dict[str, object],
    frame_summaries: list[object],
):
    return page_classifier.classify(
        page_url=node.canonical_url,
        candidates=candidates,
        inspection_metadata=inspection_metadata,
        frame_summaries=frame_summaries,
    )


def apply_node_classification(
    *,
    node,
    classification,
) -> None:
    node.set_page_classification(
        page_type=classification.page_type,
        confidence=classification.confidence,
        diagnostics=classification.diagnostics,
    )


def log_node_classification(
    *,
    node,
    classification,
) -> None:
    print(
        "[classify_node_helpers] "
        f"node_id={node.node_id!r} "
        f"page_type={classification.page_type!r} "
        f"confidence={classification.confidence} "
        f"diagnostics={classification.diagnostics!r}",
        flush=True,
    )


__all__ = [
    "apply_node_classification",
    "classify_current_node",
    "log_node_classification",
    "unpack_classification_payload",
]
