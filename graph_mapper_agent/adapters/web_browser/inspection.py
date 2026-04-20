from __future__ import annotations
#graph_mapper_agent/adapters/web_browser/inspection.py


import os
import time
from typing import Any

from graph_mapper_agent.adapters.web_browser.extraction import (
    extract_page_text,
    extract_raw_anchors,
    extract_search_targets,
    extract_title,
)

_PAGE_TEXT_JOIN_LIMIT: int = 2_400
_SEARCH_TARGET_LIMIT: int = 3


def inspect_page(tool: Any, input_data: dict[str, Any]) -> dict[str, Any]:
    params = _parse_inspect_params(tool, input_data)
    page = tool._driver.get_persistent_page()
    _prepare_page_timeouts(page, params["timeout_ms"])

    _stage_log(
        tool,
        "inspect.start",
        f"entry_url={params['entry_url']!r} timeout_ms={params['timeout_ms']}",
    )

    try:
        _goto_with_retry(tool, page, params["entry_url"], params["timeout_ms"], input_data)
    except Exception as exc:
        if tool._is_download_trigger(exc):
            return _handle_download_intercept(tool, input_data, params["entry_url"])
        raise

    return _build_inspect_result(tool, page, params)


def _parse_inspect_params(tool: Any, input_data: dict[str, Any]) -> dict[str, Any]:
    entry_url = str(input_data.get("entry_url") or "").strip()
    if not entry_url:
        raise ValueError("entry_url is required")

    timeout_seconds = int(input_data.get("timeout_seconds") or 30)
    metadata = input_data.get("metadata") or {}
    goal = str(input_data.get("goal") or "").strip()
    expected_kind = str(input_data.get("expected_document_kind") or "").strip()
    include_screenshot = bool(
        input_data.get("include_screenshot") or metadata.get("include_screenshot")
    )

    max_candidates_raw = input_data.get("max_candidates")
    try:
        max_candidates = (
            int(max_candidates_raw)
            if max_candidates_raw is not None
            else tool._settings.max_candidates
        )
    except (TypeError, ValueError):
        max_candidates = tool._settings.max_candidates
    max_candidates = max(1, max_candidates)

    return {
        "entry_url": entry_url,
        "timeout_ms": timeout_seconds * 1000,
        "timeout_seconds": timeout_seconds,
        "metadata": metadata,
        "goal": goal,
        "expected_kind": expected_kind,
        "include_screenshot": include_screenshot,
        "max_candidates": max_candidates,
    }


def _handle_download_intercept(
    tool: Any,
    input_data: dict[str, Any],
    entry_url: str,
) -> dict[str, Any]:
    tool._log(f"Automatic download detected: {entry_url}")

    download_payload = dict(input_data)
    download_payload["candidate_url"] = entry_url
    download_res = tool.download_candidate(download_payload)

    filename = download_res.get("filename", "unknown")
    content_type = download_res.get("content_type", "unknown")

    return {
        "entry_url": entry_url,
        "final_url": entry_url,
        "title": f"File: {filename}",
        "content": f"URL resulted in automatic download ({content_type}).",
        "text_excerpt": f"URL resulted in automatic download ({content_type}).",
        "candidates": [],
        "search_targets": [],
        "screenshot_base64": None,
        "screenshot_mime_type": None,
        "metadata": {
            "is_download_intercepted": True,
            "download_result": download_res,
            "candidate_count": 0,
            "search_target_count": 0,
        },
        "page_title": f"File: {filename}",
        "page_url": entry_url,
    }


def _debug_enabled() -> bool:
    return os.getenv("AITHER_WEB_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _prepare_page_timeouts(page: Any, timeout_ms: int) -> None:
    bounded_timeout_ms = max(1_000, int(timeout_ms or 0))
    try:
        page.set_default_timeout(bounded_timeout_ms)
    except Exception:
        pass

    try:
        page.set_default_navigation_timeout(bounded_timeout_ms)
    except Exception:
        pass


def _stage_log(tool: Any, stage: str, message: str) -> None:
    tool._log(f"[inspect.stage] {stage} {message}")


def _elapsed_ms(started_at: float) -> float:
    return (time.monotonic() - started_at) * 1000.0


def _goto_with_retry(
    tool: Any,
    page: Any,
    entry_url: str,
    timeout_ms: int,
    input_data: dict[str, Any],
) -> None:
    started = time.monotonic()
    _stage_log(tool, "goto.start", f"url={entry_url!r}")

    try:
        page.goto(
            entry_url,
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        _stage_log(
            tool,
            "goto.done",
            f"elapsed_ms={_elapsed_ms(started):.2f} final_url={getattr(page, 'url', None)!r}",
        )
        return
    except Exception as exc:
        _stage_log(tool, "goto.error", f"exc={exc!r}")

        if tool._is_download_trigger(exc):
            raise

        # Surgical retry: reset the persistent tab and try again once.
        try:
            tool._driver.reset_persistent_page(reason="inspect_goto_retry")
        except Exception:
            pass

        retry_page = tool._driver.get_persistent_page()
        _prepare_page_timeouts(retry_page, timeout_ms)

        retry_started = time.monotonic()
        _stage_log(tool, "goto.retry.start", f"url={entry_url!r}")
        retry_page.goto(
            entry_url,
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        _stage_log(
            tool,
            "goto.retry.done",
            f"elapsed_ms={_elapsed_ms(retry_started):.2f} final_url={getattr(retry_page, 'url', None)!r}",
        )


def _collect_candidates(
    tool: Any,
    page: Any,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    unique_anchors = _extract_unique_anchors(page)

    if _debug_enabled():
        tool._log(f"[debug.candidates] raw_unique_anchor_count={len(unique_anchors)}")

    if tool._projection_tool:
        projected = tool._projection_tool.project(
            page_url=page.url,
            entry_url=params["entry_url"],
            page_title=extract_title(page),
            anchors=unique_anchors,
            metadata=params["metadata"],
            goal=params["goal"],
            expected_document_kind=params["expected_kind"],
        )
        if _debug_enabled():
            tool._log(f"[debug.candidates] projected_count={len(projected)}")
        return projected

    normalized = tool._normalize_candidates(unique_anchors, page.url)
    if _debug_enabled():
        tool._log(f"[debug.candidates] normalized_count={len(normalized)}")
    return normalized


def _build_inspect_result(
    tool: Any,
    page: Any,
    params: dict[str, Any],
) -> dict[str, Any]:
    _stage_log(tool, "stability.start", f"url={getattr(page, 'url', None)!r}")
    _wait_for_page_stability(tool, page, timeout_ms=params["timeout_ms"])
    _stage_log(tool, "stability.done", f"url={getattr(page, 'url', None)!r}")

    entry_url = params["entry_url"]
    final_url = page.url
    title = extract_title(page)

    _stage_log(tool, "text.start", f"url={final_url!r}")
    text_excerpt = _extract_all_frames_text(page)
    _stage_log(tool, "text.done", f"chars={len(text_excerpt)}")

    _stage_log(tool, "candidates.start", f"url={final_url!r}")
    candidates = _collect_candidates(tool, page, params)
    _stage_log(tool, "candidates.done", f"count={len(candidates)}")

    _stage_log(tool, "search_targets.start", f"url={final_url!r}")
    search_targets = _collect_search_targets(page)
    _stage_log(tool, "search_targets.done", f"count={len(search_targets)}")

    screenshot_b64, screenshot_mime, screenshot_meta = _safe_take_screenshot(
        tool=tool,
        page=page,
        final_url=final_url,
        include_screenshot=params["include_screenshot"],
        timeout_seconds=params["timeout_seconds"],
    )

    non_main_frame_count = max(len(page.frames) - 1, 0)
    metadata: dict[str, Any] = {
        "candidate_count": len(candidates),
        "search_target_count": len(search_targets),
        "frame_count": len(page.frames),
        "non_main_frame_count": non_main_frame_count,
        "content_present": bool(text_excerpt),
        "screenshot_included": screenshot_b64 is not None,
    }
    if screenshot_meta:
        metadata["screenshot_strategy"] = screenshot_meta

    return {
        "entry_url": entry_url,
        "final_url": final_url,
        "title": title,
        "content": text_excerpt,
        "text_excerpt": text_excerpt,
        "candidates": candidates[: params["max_candidates"]],
        "search_targets": search_targets[:_SEARCH_TARGET_LIMIT],
        "screenshot_base64": screenshot_b64,
        "screenshot_mime_type": screenshot_mime,
        "metadata": metadata,
        "page_title": title,
        "page_url": final_url,
    }


def _safe_take_screenshot(
    *,
    tool: Any,
    page: Any,
    final_url: str,
    include_screenshot: bool,
    timeout_seconds: int,
) -> tuple[str | None, str | None, Any]:
    if not include_screenshot:
        _stage_log(tool, "screenshot.skip", "include_screenshot=False")
        return None, None, None

    _stage_log(tool, "screenshot.start", f"url={final_url!r}")
    started = time.monotonic()
    try:
        result = tool._take_smart_screenshot(
            page=page,
            final_url=final_url,
            include_screenshot=include_screenshot,
            timeout_seconds=timeout_seconds,
        )
        _stage_log(
            tool,
            "screenshot.done",
            f"elapsed_ms={_elapsed_ms(started):.2f}",
        )
        return result
    except Exception as exc:
        _stage_log(
            tool,
            "screenshot.error",
            f"elapsed_ms={_elapsed_ms(started):.2f} exc={exc!r}",
        )
        return None, None, {"error": repr(exc), "strategy": "screenshot_failed"}


def _wait_for_page_stability(tool: Any, page: Any, *, timeout_ms: int) -> None:
    settings = getattr(tool, "_settings", None)
    load_wait_ms = int(getattr(settings, "html_load_wait_ms", 1500) or 1500)
    networkidle_wait_ms = int(getattr(settings, "html_networkidle_wait_ms", 2500) or 2500)
    settle_wait_ms = int(getattr(settings, "html_settle_wait_ms", 900) or 900)
    bounded_timeout_ms = max(500, int(timeout_ms or 0))

    try:
        page.wait_for_load_state("load", timeout=min(load_wait_ms, bounded_timeout_ms))
    except Exception:
        pass

    try:
        page.wait_for_load_state("networkidle", timeout=min(networkidle_wait_ms, bounded_timeout_ms))
    except Exception:
        pass

    try:
        page.wait_for_timeout(min(settle_wait_ms, bounded_timeout_ms))
    except Exception:
        pass


def _collect_search_targets(page: Any) -> list[dict[str, Any]]:
    all_targets: list[dict[str, Any]] = []
    all_targets.extend(_search_targets_from_frame(page, page.url))

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            all_targets.extend(_search_targets_from_frame(frame, frame.url))
        except Exception:
            continue

    seen_ids: set[str] = set()
    unique: list[dict[str, Any]] = []

    for item in all_targets:
        if not isinstance(item, dict):
            continue
        stid = str(item.get("search_target_id") or "").strip()
        if not stid or stid in seen_ids:
            continue
        seen_ids.add(stid)
        unique.append(item)

    unique.sort(
        key=lambda item: (
            float(item.get("confidence") or 0.0),
            1 if item.get("same_host") is True else 0,
        ),
        reverse=True,
    )
    return unique[:_SEARCH_TARGET_LIMIT]


def _search_targets_from_frame(frame_like: Any, frame_url: str) -> list[dict[str, Any]]:
    try:
        return extract_search_targets(frame_like, frame_url)
    except Exception:
        return []


def _extract_all_frames_text(page: Any) -> str:
    text_parts: list[str] = []

    main_text = extract_page_text(page)
    if main_text:
        text_parts.append(main_text)

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            frame_text = extract_page_text(frame)
            if frame_text:
                text_parts.append(frame_text)
        except Exception:
            continue

    return " | ".join(text_parts)[:_PAGE_TEXT_JOIN_LIMIT]


def _extract_unique_anchors(page: Any) -> list[dict[str, Any]]:
    all_anchors: list[dict[str, Any]] = []
    all_anchors.extend(_anchors_from_frame(page, page.url))

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            all_anchors.extend(_anchors_from_frame(frame, frame.url))
        except Exception:
            continue

    seen_urls: set[str] = set()
    unique: list[dict[str, Any]] = []
    for anchor in all_anchors:
        href = str(anchor.get("href") or anchor.get("url") or "").strip()
        if href and href not in seen_urls:
            seen_urls.add(href)
            unique.append(anchor)

    return unique


def _anchors_from_frame(frame_like: Any, frame_url: str) -> list[dict[str, Any]]:
    anchors = extract_raw_anchors(frame_like)
    for anchor in anchors:
        raw_href = anchor.get("href")
        if raw_href:
            anchor["href"] = tool_urljoin(frame_url, str(raw_href))
    return anchors


def tool_urljoin(frame_url: str, raw_href: str) -> str:
    from urllib.parse import urljoin

    return urljoin(frame_url, raw_href)