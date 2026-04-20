from __future__ import annotations
#graph_mapper_agent/adapters/web_browser/downloads.py
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from graph_mapper_agent.adapters.tools.ingest_storage import (
    StorageScope,
)
from graph_mapper_agent.adapters.web_browser.driver import (
    DownloadResult,
)


def download_candidate(tool: Any, input_data: dict[str, Any]) -> dict[str, Any]:
    candidate_url = str(input_data.get("candidate_url") or "").strip()
    jurisdiction_code = str(input_data.get("jurisdiction_code") or "default")
    document_key = str(input_data.get("document_key") or "temp")
    storage_namespace = str(
        input_data.get("storage_namespace") or "graph_mapper_agent"
    ).strip() or "graph_mapper_agent"
    session_id = str(input_data.get("session_id") or "").strip() or None
    run_id = str(input_data.get("run_id") or "").strip() or None
    timeout_seconds = int(input_data.get("timeout_seconds") or 60)

    if not candidate_url:
        raise ValueError("candidate_url is required")

    tool._log(f"download url={candidate_url}")

    result = _download_resource(tool, candidate_url, timeout_seconds)
    content = Path(result.path).read_bytes()

    try:
        sha256 = hashlib.sha256(content).hexdigest()
        saved = tool._storage.save_original_bytes(
            jurisdiction_code=jurisdiction_code,
            document_key=document_key,
            filename=result.suggested_filename or "downloaded_file",
            content=content,
            source_url=candidate_url,
            scope=StorageScope(
                namespace=storage_namespace,
                session_id=session_id,
                run_id=run_id,
                jurisdiction_code=jurisdiction_code,
                document_key=document_key,
            ),
        )
    finally:
        Path(result.path).unlink(missing_ok=True)

    tool._log(
        f"saved filename={saved.filename} "
        f"path={saved.original_path} size={len(content)}"
    )

    return {
        "download_url": candidate_url,
        "final_url": result.url,
        "filename": saved.filename,
        "original_path": saved.original_path,
        "content_type": saved.content_type,
        "sha256": sha256,
        "size_bytes": len(content),
        "metadata": {
            "suggested_filename": result.suggested_filename,
        },
    }


def _download_resource(
    tool: Any,
    url: str,
    timeout_seconds: int,
) -> DownloadResult:
    if tool._is_pdf_url(url):
        tool._log("PDF directo detectado -> HTTP download")
        return _download_direct_http(tool, url, timeout_seconds)

    tool._log("No es PDF directo -> Playwright download")
    return tool._driver.download_file(url, timeout_ms=timeout_seconds * 1000)


def _download_direct_http(
    tool: Any,
    url: str,
    timeout_seconds: int,
) -> DownloadResult:
    req = Request(
        url,
        headers={"User-Agent": tool._settings.driver_settings.user_agent},
    )

    with urlopen(req, timeout=timeout_seconds) as response:
        content = response.read()

    parsed_path = os.path.basename(url.split("?")[0].split("#")[0]) or "downloaded_file"

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(content)
        target_path = tmp.name

    return DownloadResult(
        path=target_path,
        filename=parsed_path,
        url=url,
        suggested_filename=parsed_path,
    )
