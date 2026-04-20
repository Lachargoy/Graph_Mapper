from __future__ import annotations
#graph_mapper_agent/adapters/web_browser/artifacts.py
import base64
import os
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore[assignment]


_PDF_TEXT_MIN_THRESHOLD: int = 50
_PDF_CONTENT_TRUNCATE: int = 1_500
_PDF_SCREENSHOT_DPI: int = 150


def open_artifact(tool: Any, input_data: dict[str, Any]) -> dict[str, Any]:
    candidate_url = str(input_data.get("candidate_url") or "").strip()
    local_path = _resolve_local_path(input_data)

    if not local_path or not os.path.exists(local_path):
        return _artifact_error(candidate_url, f"Archivo no encontrado en: {local_path}")

    if not local_path.lower().endswith(".pdf"):
        return _artifact_non_pdf(candidate_url, local_path)

    return _open_pdf_artifact(tool, candidate_url, local_path)


def _resolve_local_path(input_data: dict[str, Any]) -> str:
    for key in ("original_path", "local_path", "storage_ref"):
        value = input_data.get(key)
        if value:
            path = str(value).strip()
            if path:
                return path
    return ""


def _open_pdf_artifact(
    tool: Any,
    candidate_url: str,
    local_path: str,
) -> dict[str, Any]:
    _require_fitz()

    try:
        probe_text = _extract_pdf_text(local_path, max_pages=1)
        if len(probe_text.strip()) > _PDF_TEXT_MIN_THRESHOLD:
            return _artifact_pdf_text(tool, candidate_url, local_path)
        return _artifact_pdf_screenshot(candidate_url, local_path)
    except Exception as exc:
        return _artifact_error(candidate_url, f"Fallo al parsear PDF: {exc}")


def _artifact_pdf_text(
    tool: Any,
    candidate_url: str,
    local_path: str,
) -> dict[str, Any]:
    max_pages = tool._settings.max_pages_to_extract
    full_text = _extract_pdf_text(local_path, max_pages=max_pages)

    truncated = len(full_text) > _PDF_CONTENT_TRUNCATE
    content = full_text[:_PDF_CONTENT_TRUNCATE]
    if truncated:
        content += "\n...[Truncado]"

    return {
        "artifact_url": candidate_url,
        "valid": True,
        "artifact_kind": "pdf_text",
        "content": content,
        "diagnostics": {
            "method": "text_extraction",
            "pages_read": max_pages,
            "truncated": truncated,
        },
    }


def _artifact_pdf_screenshot(
    candidate_url: str,
    local_path: str,
) -> dict[str, Any]:
    b64_image = _capture_pdf_screenshot(local_path, page_number=0)
    return {
        "artifact_url": candidate_url,
        "valid": True,
        "artifact_kind": "pdf_screenshot",
        "content_base64": b64_image,
        "diagnostics": {
            "method": "vision_fallback",
            "message": "Texto insuficiente. Se generó captura de pantalla.",
        },
    }


def _artifact_error(candidate_url: str, reason: str) -> dict[str, Any]:
    return {
        "artifact_url": candidate_url,
        "valid": False,
        "artifact_kind": "unknown",
        "diagnostics": {"reason": reason},
    }


def _artifact_non_pdf(candidate_url: str, path: str) -> dict[str, Any]:
    return {
        "artifact_url": candidate_url,
        "valid": True,
        "artifact_kind": "non_pdf_file",
        "content": "[Archivo en formato no soportado para lectura directa]",
        "diagnostics": {"path": path},
    }


def _require_fitz() -> None:
    if fitz is None:
        raise RuntimeError("PyMuPDF no instalado. pip install PyMuPDF")


def _extract_pdf_text(local_path: str, max_pages: int) -> str:
    doc = fitz.open(local_path)
    try:
        pages: list[str] = []
        for i in range(min(max_pages, len(doc))):
            text = doc.load_page(i).get_text("text").strip()
            if text:
                pages.append(f"--- PAGINA {i + 1} ---\n{text}")
        return "\n".join(pages)
    finally:
        doc.close()


def _capture_pdf_screenshot(
    local_path: str,
    page_number: int = 0,
    dpi: int = _PDF_SCREENSHOT_DPI,
) -> str:
    doc = fitz.open(local_path)
    try:
        pix = doc.load_page(page_number).get_pixmap(dpi=dpi)
        return base64.b64encode(pix.tobytes("png")).decode("utf-8")
    finally:
        doc.close()
