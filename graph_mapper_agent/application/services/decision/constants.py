from __future__ import annotations


ALLOWED_ACTIONS: frozenset[str] = frozenset(
    {
        "refine_navigation_perception",
        "validate_current_content",
        "follow_edge",
        "download_artifact",
        "open_artifact",
        "search_with_text",
        "mark_exhausted",
        "success",
    }
)

EDGE_REQUIRING_ACTIONS: frozenset[str] = frozenset(
    {
        "follow_edge",
        "download_artifact",
        "open_artifact",
    }
)

RESUME_MARKERS: tuple[str, ...] = (
    "pivot",
    "reanudar",
    "resume",
    "backtrack",
    "choice point",
    "choice_point",
    "recoverable",
    "puente",
    "bridge",
    "volver",
    "regresar",
)


__all__ = [
    "ALLOWED_ACTIONS",
    "EDGE_REQUIRING_ACTIONS",
    "RESUME_MARKERS",
]
