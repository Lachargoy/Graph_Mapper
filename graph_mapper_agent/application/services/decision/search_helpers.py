from __future__ import annotations

from graph_mapper_agent.application.services.decision.normalization import (
    normalize_text,
    strip_url_fragment,
)
from graph_mapper_agent.domain.view import NodeView


from urllib.parse import urlparse

def is_authorized_search_host(current_url: str | None, anchor_url: str | None) -> bool:
    if not current_url:
        return False
    
    current_host = urlparse(current_url).netloc.lower()
    if not current_host:
        return False

    # 1. Caso explícito: Es DuckDuckGo o alguna de sus variantes (html, lite, etc.)
    # Esto cubre duckduckgo.com, html.duckduckgo.com, lite.duckduckgo.com, etc.
    if current_host == "duckduckgo.com" or current_host.endswith(".duckduckgo.com"):
        return True

    # 2. Caso genérico: Coincide con el host del Anchor definido para el carril
    if anchor_url:
        anchor_host = urlparse(anchor_url).netloc.lower()
        if anchor_host and current_host == anchor_host:
            return True

    return False


def looks_like_search_engine_boilerplate(candidate: object) -> bool:
    text = normalize_text(
        " ".join(
            filter(
                None,
                [
                    str(getattr(candidate, "label", "") or ""),
                    str(getattr(candidate, "target_url", "") or ""),
                ],
            )
        )
    )

    markers = (
        "about duckduckgo",
        "duckduckgo.com/about",
        "duckduckgo.com/feedback",
        "feedback",
        "privacy",
        "help",
        "terms",
    )
    return any(marker in text for marker in markers)


def is_same_page_self_loop_candidate(candidate: object, node_view: NodeView) -> bool:
    candidate_url = strip_url_fragment(
        normalize_text(str(getattr(candidate, "target_url", "") or ""))
    )
    node_url = strip_url_fragment(normalize_text(str(node_view.url or "") or ""))
    return bool(candidate_url and node_url and candidate_url == node_url)


def looks_external_to_current_node(candidate: object, node_view: NodeView) -> bool:
    candidate_url = normalize_text(str(getattr(candidate, "target_url", "") or ""))
    node_url = normalize_text(str(node_view.url or "") or "")
    if not candidate_url or not node_url:
        return False
    return candidate_url != node_url and "duckduckgo.com" not in candidate_url


def node_view_search_targets(node_view: NodeView) -> tuple[object, ...]:
    targets = getattr(node_view, "search_targets", ())
    if not isinstance(targets, tuple):
        try:
            targets = tuple(targets or ())
        except TypeError:
            return ()
    return targets


def node_view_search_history(node_view: NodeView) -> tuple[str, ...]:
    for attr_name in ("current_search_history", "search_history"):
        value = getattr(node_view, attr_name, ())
        if isinstance(value, tuple):
            return tuple(str(item).strip() for item in value if str(item).strip())
        try:
            return tuple(
                str(item).strip() for item in (value or ()) if str(item).strip()
            )
        except TypeError:
            continue
    return ()


def normalize_search_query_text(value: str) -> str:
    return normalize_text(" ".join(str(value or "").split()).strip())


def search_query_already_attempted(node_view: NodeView, query_text: str) -> bool:
    normalized_query = normalize_search_query_text(query_text)
    if not normalized_query:
        return False

    history = node_view_search_history(node_view)
    for previous in history:
        if normalize_search_query_text(previous) == normalized_query:
            return True
    return False


__all__ = [
    "is_same_page_self_loop_candidate",
    "looks_external_to_current_node",
    "looks_like_search_engine_boilerplate",
    "node_view_search_history",
    "node_view_search_targets",
    "normalize_search_query_text",
    "search_query_already_attempted",
]
