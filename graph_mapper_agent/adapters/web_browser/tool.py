from __future__ import annotations
#graph_mapper_agent/adapters/web_browser/tool.py
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from graph_mapper_agent.adapters.tools.ingest_storage import (
    IngestStorage,
)
from graph_mapper_agent.adapters.web_browser.artifacts import (
    open_artifact,
)
from graph_mapper_agent.adapters.web_browser.downloads import (
    download_candidate,
)
from graph_mapper_agent.adapters.web_browser.driver import (
    PlaywrightDriver,
)
from graph_mapper_agent.adapters.web_browser.inspection import (
    inspect_page,
)
from graph_mapper_agent.adapters.web_browser.pdf_support import (
    is_pdf_url,
    take_smart_screenshot,
)
from graph_mapper_agent.adapters.web_browser.search import (
    search_with_text,
)
from graph_mapper_agent.adapters.web_browser.settings import (
    WebBrowserToolSettings,
)
from graph_mapper_agent.adapters.web_browser.content_probe import (
    probe_content,
)



from .candidate_projection import (
    BaseCandidateProjectionTool,
    DocumentCandidateProjectionEnricher,
)


_LOG_PREFIX = "[WebBrowserTool]"
_DOWNLOAD_TRIGGER_FRAGMENTS: tuple[str, ...] = (
    "Download is starting",
    "net::ERR_ABORTED",
)
_SEARCH_WAIT_SLICE_MS: int = 350
_SEARCH_MAX_POLLS: int = 10
_SEARCH_TEXT_PREVIEW_LIMIT: int = 600


class WebBrowserTool:
    def __init__(
        self,
        storage: IngestStorage | None = None,
        settings: WebBrowserToolSettings | None = None,
        projection_tool: Any | None = None,
    ) -> None:
        self._storage = storage or IngestStorage()
        self._settings = settings or WebBrowserToolSettings()
        self._driver = PlaywrightDriver(self._settings.driver_settings)

        if projection_tool:
            self._projection_tool = projection_tool
        elif BaseCandidateProjectionTool and DocumentCandidateProjectionEnricher:
            self._projection_tool = BaseCandidateProjectionTool(
                enrichers=(DocumentCandidateProjectionEnricher(),),
            )
        else:
            self._projection_tool = None

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} "
            f"max_candidates={self._settings.max_candidates}>"
        )

    def __enter__(self) -> WebBrowserTool:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self._driver.stop()

    def inspect_page(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return inspect_page(self, input_data)

    def search_with_text(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return search_with_text(self, input_data)

    def download_candidate(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return download_candidate(self, input_data)

    def open_artifact(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return open_artifact(self, input_data)

    def probe_content(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return probe_content(self, input_data)

    def _take_smart_screenshot(
        self,
        *,
        page: Any,
        final_url: str,
        include_screenshot: bool,
        timeout_seconds: int,
    ) -> tuple[str | None, str | None, dict[str, Any] | None]:
        return take_smart_screenshot(
            self,
            page=page,
            final_url=final_url,
            include_screenshot=include_screenshot,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _is_pdf_url(url: str) -> bool:
        return is_pdf_url(url)

    def _capture_search_snapshot(self, page: Any) -> dict[str, Any]:
        from graph_mapper_agent.adapters.web_browser.inspection import (
            _extract_all_frames_text,
            _extract_unique_anchors,
        )
        from graph_mapper_agent.adapters.web_browser.extraction import (
            extract_title,
        )

        title = extract_title(page)
        text_excerpt = _extract_all_frames_text(page)
        candidates = _extract_unique_anchors(page)

        candidate_urls: list[str] = []
        for item in candidates[:8]:
            href = str(item.get("href") or item.get("url") or "").strip()
            if href:
                candidate_urls.append(href)

        result_scope = self._capture_result_scope_snapshot(page)
        return {
            "url": str(page.url or "").strip(),
            "title": title or "",
            "text_excerpt": self._safe_text(text_excerpt, _SEARCH_TEXT_PREVIEW_LIMIT),
            "candidate_urls": tuple(candidate_urls),
            "candidate_count": len(candidates),
            "result_scope_kind": result_scope.get("kind"),
            "result_scope_text_excerpt": result_scope.get("text_excerpt", ""),
            "result_scope_candidate_urls": tuple(result_scope.get("candidate_urls", ())),
            "result_scope_candidate_count": int(result_scope.get("candidate_count", 0)),
        }

    def _wait_for_search_delta(
        self,
        *,
        page: Any,
        before_snapshot: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        max_polls = max(1, min(_SEARCH_MAX_POLLS, max(1, timeout_ms // max(_SEARCH_WAIT_SLICE_MS, 1))))
        after_snapshot = self._capture_search_snapshot(page)
        delta = self._compute_search_delta(before_snapshot, after_snapshot)
        if delta["state_delta_kind"] != "none":
            return delta

        for _ in range(max_polls):
            page.wait_for_timeout(_SEARCH_WAIT_SLICE_MS)
            after_snapshot = self._capture_search_snapshot(page)
            delta = self._compute_search_delta(before_snapshot, after_snapshot)
            if delta["state_delta_kind"] != "none":
                return delta
        return delta

    def _resolve_search_target(
        self,
        *,
        available_targets: list[dict[str, Any]],
        search_target_id: str,
    ) -> dict[str, Any] | None:
        wanted = str(search_target_id or "").strip()
        if not wanted:
            return None
        for item in available_targets:
            if str(item.get("search_target_id") or "").strip() == wanted:
                return item
        return None

    def _execute_search(
        self,
        *,
        page: Any,
        target: dict[str, Any],
        query_text: str,
        timeout_ms: int,
    ) -> dict[str, Any]:
        frames = self._ordered_frames_for_target(page, target)
        last_error: str | None = None
        for frame in frames:
            try:
                result = self._submit_search_in_frame(
                    frame=frame,
                    target=target,
                    query_text=query_text,
                )
            except Exception as exc:
                msg = str(exc)
                if self._looks_like_context_destroyed(msg):
                    return {
                        "ok": True,
                        "submit_method": "navigation_context_destroyed",
                        "frame_url": getattr(frame, "url", None),
                        "matched_confidence": 1.0,
                        "matched_target": {
                            "search_target_id": target.get("search_target_id"),
                        },
                    }
                last_error = msg
                continue

            if bool(result.get("ok")):
                result["frame_url"] = getattr(frame, "url", None)
                return result

            last_error = str(result.get("reason") or "search_target_not_matched")

        return {
            "ok": False,
            "reason": last_error or "search_target_not_found_in_any_frame",
            "submit_method": None,
            "matched_confidence": None,
            "matched_target": None,
        }

    @staticmethod
    def _ordered_frames_for_target(page: Any, target: dict[str, Any]) -> list[Any]:
        source_frame = str(target.get("source_frame") or "").strip()
        frames = list(page.frames)
        if not source_frame:
            return frames

        preferred: list[Any] = []
        fallback: list[Any] = []
        for frame in frames:
            frame_url = str(getattr(frame, "url", "") or "").strip()
            if frame_url == source_frame:
                preferred.append(frame)
            else:
                fallback.append(frame)
        return preferred + fallback

    def _submit_search_in_frame(
        self,
        *,
        frame: Any,
        target: dict[str, Any],
        query_text: str,
    ) -> dict[str, Any]:
        payload = {
            "target": {
                "search_target_id": str(target.get("search_target_id") or "").strip(),
                "tag": str(target.get("tag") or "input").strip().lower(),
                "input_type": str(target.get("input_type") or "text").strip().lower(),
                "name": str(target.get("name") or "").strip(),
                "id_attr": str(target.get("id_attr") or "").strip(),
                "placeholder": str(target.get("placeholder") or "").strip(),
                "aria_label": str(target.get("aria_label") or "").strip(),
                "label": str(target.get("label") or "").strip(),
                "form_action": str(target.get("form_action") or "").strip(),
            },
            "query_text": str(query_text or "").strip(),
        }
        js = Path(__file__).with_name("search_submit.js").read_text(encoding="utf-8")
        return frame.evaluate(js, payload)

    def _compute_search_delta(
        self,
        before_snapshot: dict[str, Any],
        after_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        before_url = str(before_snapshot.get("url") or "").strip()
        after_url = str(after_snapshot.get("url") or "").strip()
        before_title = str(before_snapshot.get("title") or "").strip()
        after_title = str(after_snapshot.get("title") or "").strip()
        before_text = str(before_snapshot.get("text_excerpt") or "").strip()
        after_text = str(after_snapshot.get("text_excerpt") or "").strip()
        before_candidates = tuple(before_snapshot.get("candidate_urls") or ())
        after_candidates = tuple(after_snapshot.get("candidate_urls") or ())
        before_result_text = str(before_snapshot.get("result_scope_text_excerpt") or "").strip()
        after_result_text = str(after_snapshot.get("result_scope_text_excerpt") or "").strip()
        before_result_candidates = tuple(before_snapshot.get("result_scope_candidate_urls") or ())
        after_result_candidates = tuple(after_snapshot.get("result_scope_candidate_urls") or ())

        url_changed = before_url != after_url
        title_changed = before_title != after_title
        result_scope_available = bool(before_result_candidates or after_result_candidates or before_result_text or after_result_text)

        if result_scope_available:
            content_changed = before_result_text != after_result_text
            candidate_set_changed = before_result_candidates != after_result_candidates
        else:
            content_changed = before_text != after_text
            candidate_set_changed = before_candidates != after_candidates

        if url_changed:
            kind = "navigation"
        elif candidate_set_changed or content_changed or title_changed:
            kind = "dom_mutation"
        else:
            kind = "none"

        return {
            "state_delta_kind": kind,
            "url_changed": url_changed,
            "title_changed": title_changed,
            "content_changed": content_changed,
            "candidate_set_changed": candidate_set_changed,
            "before_signature": self._snapshot_signature(before_snapshot),
            "after_signature": self._snapshot_signature(after_snapshot),
        }

    @staticmethod
    def _snapshot_signature(snapshot: dict[str, Any]) -> str:
        return "|".join(
            (
                str(snapshot.get("url") or "").strip(),
                str(snapshot.get("title") or "").strip(),
                str(len(str(snapshot.get("text_excerpt") or "").strip())),
                str(len(tuple(snapshot.get("candidate_urls") or ()))),
                *tuple(snapshot.get("candidate_urls") or ())[:5],
            )
        )

    def _search_results_detected(
        self,
        *,
        before_snapshot: dict[str, Any],
        after_result: dict[str, Any],
        delta: dict[str, Any],
    ) -> bool:
        if str(delta.get("state_delta_kind") or "") != "none":
            return True

        before_result_candidates = int(before_snapshot.get("result_scope_candidate_count") or 0)
        after_candidates = len(list(after_result.get("candidates") or []))
        before_result_text = str(before_snapshot.get("result_scope_text_excerpt") or "").strip()
        before_text = str(before_snapshot.get("text_excerpt") or "").strip()
        after_text = self._safe_text(
            after_result.get("text_excerpt") or after_result.get("content"),
            _SEARCH_TEXT_PREVIEW_LIMIT,
        )

        if before_result_candidates and after_candidates != before_result_candidates:
            return True
        if before_result_text and after_text != before_result_text:
            return True
        before_candidates = int(before_snapshot.get("candidate_count") or 0)
        if after_candidates != before_candidates:
            return True
        if after_text != before_text:
            return True
        return False

    def _capture_result_scope_snapshot(self, page: Any) -> dict[str, Any]:
        host = str(__import__("urllib.parse").parse.urlparse(str(page.url or "")).netloc or "").lower()
        selectors: list[tuple[str, str, str]] = []
        if "html.duckduckgo.com" in host:
            selectors.append(("#links", "#links a[href]", "duckduckgo_html_results"))

        for container_selector, anchor_selector, kind in selectors:
            try:
                container = page.locator(container_selector)
                if container.count() <= 0:
                    continue

                text_excerpt = self._safe_text(container.inner_text(timeout=800), _SEARCH_TEXT_PREVIEW_LIMIT)
                links = page.locator(anchor_selector)
                urls: list[str] = []
                count = min(links.count(), 12)
                for i in range(count):
                    try:
                        href = str(links.nth(i).get_attribute("href") or "").strip()
                        if href:
                            urls.append(urljoin(str(page.url or ""), href))
                    except Exception:
                        continue

                return {
                    "kind": kind,
                    "text_excerpt": text_excerpt,
                    "candidate_urls": urls,
                    "candidate_count": len(urls),
                }
            except Exception:
                continue

        return {
            "kind": "global_fallback",
            "text_excerpt": "",
            "candidate_urls": [],
            "candidate_count": 0,
        }

    @staticmethod
    def _normalize_candidates(
        raw_anchors: list[dict[str, Any]],
        base_url: str,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for anchor in raw_anchors:
            href = anchor.get("href")
            if not href:
                continue
            candidates.append(
                {
                    "url": urljoin(base_url, href),
                    "text": (anchor.get("text") or "").strip(),
                    "score": 1,
                    "metadata": anchor,
                }
            )
        return candidates

    @staticmethod
    def _looks_like_context_destroyed(message: str) -> bool:
        lowered = str(message or "").lower()
        return (
            "execution context was destroyed" in lowered
            or "most likely because of a navigation" in lowered
            or "navigation" in lowered and "destroyed" in lowered
        )

    @staticmethod
    def _is_download_trigger(exc: Exception) -> bool:
        msg = str(exc)
        return any(f in msg for f in _DOWNLOAD_TRIGGER_FRAGMENTS)

    @staticmethod
    def _safe_text(value: object, limit: int) -> str:
        text = " ".join(str(value or "").split()).strip()
        if not text:
            return ""
        return text[:limit]

    @staticmethod
    def _log(message: str) -> None:
        print(f"{_LOG_PREFIX} {message}", flush=True)


__all__ = [
    "WebBrowserTool",
    "WebBrowserToolSettings",
]
