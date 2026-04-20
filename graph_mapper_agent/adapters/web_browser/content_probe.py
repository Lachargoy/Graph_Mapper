from __future__ import annotations
#graph_mapper_agent/adapters/web_browser/content_probe.py
import time
from typing import Any, Literal


ResourceKind = Literal["pdf", "html", "json", "image", "binary", "unknown"]

_MIN_STAGE_TIMEOUT_MS = 750
_HEAD_TIMEOUT_CAP_MS = 8_000
_GET_TIMEOUT_CAP_MS = 12_000


def probe_content(tool: Any, input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Only classifies the remote resource.
    Does NOT navigate visually.
    Does NOT download.
    Does NOT decide action policy.

    Strategy:
    1) HEAD first
    2) if HEAD is not enough, fallback to a short GET
    3) classifies by content-type and, in fallback, by magic bytes / HTML bytes

    Hardened for:
    - per-stage logs
    - timeout based on remaining budget
    - not depending on the default persistent tab
    - returning a controlled result if the probe fails
    """
    params = _parse_probe_params(tool, input_data)

    provided_page = input_data.get("page")
    owns_page = provided_page is None
    page = provided_page or tool._driver.new_page()

    _prepare_page_timeouts(page, params["timeout_ms"])
    request_ctx = page.request
    deadline_at = time.monotonic() + (params["timeout_ms"] / 1000.0)

    _stage_log(
        tool,
        "probe.start",
        f"url={params['url']!r} timeout_ms={params['timeout_ms']} "
        f"max_redirects={params['max_redirects']} owns_page={owns_page!r}",
    )

    try:
        head_error: str | None = None

        # 1) HEAD first
        head_timeout_ms = _stage_timeout_ms(deadline_at, _HEAD_TIMEOUT_CAP_MS)
        if head_timeout_ms > 0:
            _stage_log(
                tool,
                "probe.head.start",
                f"url={params['url']!r} timeout_ms={head_timeout_ms}",
            )
            head_started = time.monotonic()

            try:
                head_resp = request_ctx.head(
                    params["url"],
                    timeout=head_timeout_ms,
                    max_redirects=params["max_redirects"],
                )
                try:
                    head_result = _build_probe_result(
                        original_url=params["url"],
                        response=head_resp,
                        via_method="HEAD",
                        include_body_sniff=False,
                    )

                    _stage_log(
                        tool,
                        "probe.head.done",
                        f"elapsed_ms={_elapsed_ms(head_started):.2f} "
                        f"status={head_result.get('status')} "
                        f"resource_kind={head_result.get('resource_kind')!r} "
                        f"final_url={head_result.get('final_url')!r}",
                    )

                    if _head_is_conclusive(head_result):
                        metadata = dict(head_result.get("metadata") or {})
                        metadata["probe_completed_via"] = "HEAD"
                        head_result["metadata"] = metadata
                        return head_result
                finally:
                    _safe_dispose(head_resp)

            except Exception as exc:
                head_error = repr(exc)
                _stage_log(
                    tool,
                    "probe.head.error",
                    f"elapsed_ms={_elapsed_ms(head_started):.2f} exc={exc!r}",
                )
        else:
            head_error = "probe_head_skipped_budget_exhausted"
            _stage_log(
                tool,
                "probe.head.skip",
                f"remaining_ms={_remaining_ms(deadline_at)}",
            )

        # 2) GET fallback with short body
        get_timeout_ms = _stage_timeout_ms(deadline_at, _GET_TIMEOUT_CAP_MS)
        if get_timeout_ms <= 0:
            _stage_log(
                tool,
                "probe.get.skip",
                f"remaining_ms={_remaining_ms(deadline_at)}",
            )
            return _build_probe_unknown_result(
                original_url=params["url"],
                reason="probe_timeout_budget_exhausted_before_get",
                head_error=head_error,
            )

        _stage_log(
            tool,
            "probe.get.start",
            f"url={params['url']!r} timeout_ms={get_timeout_ms}",
        )
        get_started = time.monotonic()

        try:
            get_resp = request_ctx.get(
                params["url"],
                timeout=get_timeout_ms,
                max_redirects=params["max_redirects"],
                headers={"Range": "bytes=0-2047"},
            )
        except Exception as exc:
            _stage_log(
                tool,
                "probe.get.error",
                f"elapsed_ms={_elapsed_ms(get_started):.2f} exc={exc!r}",
            )
            return _build_probe_unknown_result(
                original_url=params["url"],
                reason="probe_get_failed",
                head_error=head_error,
                get_error=repr(exc),
            )

        try:
            result = _build_probe_result(
                original_url=params["url"],
                response=get_resp,
                via_method="GET",
                include_body_sniff=True,
            )
            metadata = dict(result.get("metadata") or {})
            metadata["probe_completed_via"] = "GET"
            if head_error:
                metadata["head_error"] = head_error
            result["metadata"] = metadata

            _stage_log(
                tool,
                "probe.get.done",
                f"elapsed_ms={_elapsed_ms(get_started):.2f} "
                f"status={result.get('status')} "
                f"resource_kind={result.get('resource_kind')!r} "
                f"final_url={result.get('final_url')!r}",
            )
            return result
        finally:
            _safe_dispose(get_resp)

    finally:
        if owns_page:
            _safe_close_page(tool, page, reason="probe_complete")


def _parse_probe_params(tool: Any, input_data: dict[str, Any]) -> dict[str, Any]:
    url = str(input_data.get("url") or input_data.get("entry_url") or "").strip()
    if not url:
        raise ValueError("url is required")

    timeout_seconds = input_data.get("timeout_seconds")
    timeout_ms = input_data.get("timeout_ms")

    if timeout_ms is None:
        try:
            timeout_ms = int(timeout_seconds or 30) * 1000
        except (TypeError, ValueError):
            timeout_ms = 30_000

    max_redirects = input_data.get("max_redirects")
    try:
        max_redirects = int(max_redirects) if max_redirects is not None else 10
    except (TypeError, ValueError):
        max_redirects = 10
    max_redirects = max(0, max_redirects)

    return {
        "url": url,
        "timeout_ms": max(1_000, int(timeout_ms)),
        "max_redirects": max_redirects,
    }


def _build_probe_result(
    *,
    original_url: str,
    response: Any,
    via_method: str,
    include_body_sniff: bool,
) -> dict[str, Any]:
    headers = _extract_headers(response)
    raw_content_type = headers.get("content-type", "")
    normalized_content_type = _normalize_content_type(raw_content_type)
    resource_kind = _classify_content_type(normalized_content_type)

    is_pdf_magic = False
    looks_like_html = False
    body_preview_len = 0

    if include_body_sniff:
        try:
            body = response.body()
        except Exception:
            body = b""
        preview = body[:2048]
        body_preview_len = len(preview)
        is_pdf_magic = preview.startswith(b"%PDF-")
        looks_like_html = _looks_like_html_bytes(preview)

        if resource_kind in {"unknown", "binary"}:
            if is_pdf_magic:
                resource_kind = "pdf"
            elif looks_like_html:
                resource_kind = "html"

    return {
        "original_url": original_url,
        "final_url": _extract_response_url(response),
        "status": _extract_response_status(response),
        "content_type_raw": raw_content_type,
        "content_type": normalized_content_type,
        "resource_kind": resource_kind,
        "via_method": via_method,
        "is_pdf_magic": is_pdf_magic,
        "looks_like_html": looks_like_html,
        "headers": {
            "content-type": raw_content_type,
            "content-disposition": headers.get("content-disposition", ""),
            "content-length": headers.get("content-length", ""),
        },
        "metadata": {
            "body_preview_len": body_preview_len,
        },
    }


def _build_probe_unknown_result(
    *,
    original_url: str,
    reason: str,
    head_error: str | None = None,
    get_error: str | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "probe_reason": reason,
        "body_preview_len": 0,
    }
    if head_error:
        metadata["head_error"] = head_error
    if get_error:
        metadata["get_error"] = get_error

    return {
        "original_url": original_url,
        "final_url": original_url,
        "status": 0,
        "content_type_raw": "",
        "content_type": "",
        "resource_kind": "unknown",
        "via_method": "NONE",
        "is_pdf_magic": False,
        "looks_like_html": False,
        "headers": {
            "content-type": "",
            "content-disposition": "",
            "content-length": "",
        },
        "metadata": metadata,
    }


def _head_is_conclusive(result: dict[str, Any]) -> bool:
    kind = str(result.get("resource_kind") or "").strip().lower()
    return kind in {"pdf", "html", "json", "image"}


def _normalize_content_type(value: str | None) -> str:
    if not value:
        return ""
    return value.split(";", 1)[0].strip().lower()


def _classify_content_type(content_type: str) -> ResourceKind:
    if content_type == "application/pdf":
        return "pdf"
    if content_type == "text/html":
        return "html"
    if content_type == "application/json":
        return "json"
    if content_type.startswith("image/"):
        return "image"
    if content_type in {"application/octet-stream", "binary/octet-stream"}:
        return "binary"
    return "unknown"


def _looks_like_html_bytes(data: bytes) -> bool:
    if not data:
        return False
    stripped = data.lstrip().lower()
    return (
        stripped.startswith(b"<!doctype html")
        or stripped.startswith(b"<html")
        or stripped.startswith(b"<head")
        or stripped.startswith(b"<body")
    )


def _extract_headers(response: Any) -> dict[str, str]:
    headers_attr = getattr(response, "headers", None)
    if isinstance(headers_attr, dict):
        return {str(k).lower(): str(v) for k, v in headers_attr.items()}
    if callable(headers_attr):
        try:
            value = headers_attr()
            if isinstance(value, dict):
                return {str(k).lower(): str(v) for k, v in value.items()}
        except Exception:
            pass
    return {}


def _extract_response_url(response: Any) -> str:
    url_attr = getattr(response, "url", "")
    if callable(url_attr):
        try:
            return str(url_attr() or "").strip()
        except Exception:
            return ""
    return str(url_attr or "").strip()


def _extract_response_status(response: Any) -> int:
    status_attr = getattr(response, "status", 0)
    if callable(status_attr):
        try:
            return int(status_attr() or 0)
        except Exception:
            return 0
    try:
        return int(status_attr or 0)
    except Exception:
        return 0


def _safe_dispose(response: Any) -> None:
    dispose = getattr(response, "dispose", None)
    if callable(dispose):
        try:
            dispose()
        except Exception:
            pass


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


def _remaining_ms(deadline_at: float) -> int:
    return max(0, int((deadline_at - time.monotonic()) * 1000.0))


def _stage_timeout_ms(deadline_at: float, preferred_ms: int) -> int:
    remaining = _remaining_ms(deadline_at)
    if remaining <= 0:
        return 0
    return max(_MIN_STAGE_TIMEOUT_MS, min(preferred_ms, remaining))


def _elapsed_ms(started_at: float) -> float:
    return (time.monotonic() - started_at) * 1000.0


def _stage_log(tool: Any, stage: str, message: str) -> None:
    logger = getattr(tool, "_log", None)
    if callable(logger):
        logger(f"[probe.stage] {stage} {message}")
    else:
        print(f"[probe.stage] {stage} {message}", flush=True)


def _safe_close_page(tool: Any, page: Any, *, reason: str) -> None:
    try:
        is_closed = getattr(page, "is_closed", None)
        if callable(is_closed) and is_closed():
            return
    except Exception:
        pass

    try:
        _stage_log(tool, "page.close", f"reason={reason!r}")
        page.close()
    except Exception as exc:
        _stage_log(tool, "page.close.error", f"reason={reason!r} exc={exc!r}")


__all__ = [
    "probe_content",
]