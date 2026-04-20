from __future__ import annotations
#graph_mapper_agent/adapters/web_browser/search.py
from typing import Any

from graph_mapper_agent.adapters.web_browser.inspection import (
    _build_inspect_result,
    _collect_search_targets,
    _handle_download_intercept,
    _parse_inspect_params,
)


def search_with_text(tool: Any, input_data: dict[str, Any]) -> dict[str, Any]:
    params = _parse_search_params(tool, input_data)
    page = tool._driver.get_persistent_page()

    try:
        page.goto(
            params["entry_url"],
            wait_until="domcontentloaded",
            timeout=params["timeout_ms"],
        )
    except Exception as exc:
        if tool._is_download_trigger(exc):
            result = _handle_download_intercept(tool, input_data, params["entry_url"])
            result["search_metadata"] = {
                "status": "download_intercepted",
                "search_target_id": params["search_target_id"],
                "query_text": params["query_text"],
            }
            return result
        raise

    final_url = str(page.url or params["entry_url"]).strip()
    if tool._is_pdf_url(final_url):
        result = _build_inspect_result(tool, page, params)
        result["search_metadata"] = {
            "status": "search_not_supported_on_pdf_view",
            "search_target_id": params["search_target_id"],
            "query_text": params["query_text"],
            "results_detected": False,
            "state_delta_kind": "none",
        }
        result.setdefault("metadata", {})
        result["metadata"]["search_not_supported"] = True
        return result

    before_snapshot = tool._capture_search_snapshot(page)
    available_targets = _collect_search_targets(page)
    selected_target = tool._resolve_search_target(
        available_targets=available_targets,
        search_target_id=params["search_target_id"],
    )

    if selected_target is None:
        result = _build_inspect_result(tool, page, params)
        result["search_metadata"] = {
            "status": "target_not_found",
            "search_target_id": params["search_target_id"],
            "query_text": params["query_text"],
            "results_detected": False,
            "state_delta_kind": "none",
            "available_search_target_ids": [
                str(item.get("search_target_id") or "").strip()
                for item in available_targets
                if str(item.get("search_target_id") or "").strip()
            ],
        }
        result.setdefault("metadata", {})
        result["metadata"]["search_target_count"] = len(available_targets)
        return result

    interaction = tool._execute_search(
        page=page,
        target=selected_target,
        query_text=params["query_text"],
        timeout_ms=params["timeout_ms"],
    )

    delta = tool._wait_for_search_delta(
        page=page,
        before_snapshot=before_snapshot,
        timeout_ms=params["timeout_ms"],
    )

    result = _build_inspect_result(tool, page, params)
    candidate_count = len(list(result.get("candidates") or []))
    after_text = _safe_text(
        result.get("text_excerpt") or result.get("content"),
        _SEARCH_TEXT_PREVIEW_LIMIT,
    )

    result["search_metadata"] = {
        "status": "ok" if interaction.get("ok") else "interaction_failed",
        "search_target_id": params["search_target_id"],
        "query_text": params["query_text"],
        "submitted_via": interaction.get("submit_method"),
        "target_frame_url": interaction.get("frame_url"),
        "matched_confidence": interaction.get("matched_confidence"),
        "matched_target": interaction.get("matched_target"),
        "results_detected": tool._search_results_detected(
            before_snapshot=before_snapshot,
            after_result=result,
            delta=delta,
        ),
        "state_delta_kind": delta.get("state_delta_kind"),
        "url_changed": delta.get("url_changed"),
        "title_changed": delta.get("title_changed"),
        "content_changed": delta.get("content_changed"),
        "candidate_set_changed": delta.get("candidate_set_changed"),
        "before_url": before_snapshot.get("url"),
        "after_url": result.get("page_url"),
        "candidate_count_after": candidate_count,
        "after_text_preview": after_text,
    }

    result.setdefault("metadata", {})
    result["metadata"]["search_interaction"] = {
        "ok": bool(interaction.get("ok")),
        "submit_method": interaction.get("submit_method"),
        "matched_confidence": interaction.get("matched_confidence"),
        "frame_url": interaction.get("frame_url"),
        "delta": delta,
    }
    return result


def _parse_search_params(tool: Any, input_data: dict[str, Any]) -> dict[str, Any]:
    base = _parse_inspect_params(tool, input_data)
    search_target_id = str(input_data.get("search_target_id") or "").strip()
    query_text = str(input_data.get("query_text") or "").strip()

    if not search_target_id:
        raise ValueError("search_target_id is required")
    if not query_text:
        raise ValueError("query_text is required")

    return {
        **base,
        "search_target_id": search_target_id,
        "query_text": query_text,
    }


_SEARCH_TEXT_PREVIEW_LIMIT: int = 600


def _safe_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[:limit]
