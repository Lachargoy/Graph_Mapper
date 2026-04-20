from __future__ import annotations
#graph_mapper_agent/adapters/web_browser/pdf_support.py
import base64
import os
import struct
import tempfile
import zlib
from typing import Any
from urllib.parse import parse_qsl, urlparse
from urllib.request import Request, urlopen

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore[assignment]


_PDF_SCREENSHOT_DPI: int = 150
_BLANK_VARIANCE_THRESHOLD: float = 180.0
_BLANK_SAMPLE_STEP: int = 17
_PDF_URL_SUFFIXES: tuple[str, ...] = (".pdf",)
_PDF_QUERY_MARKERS: tuple[tuple[str, str], ...] = (
    ("format", "pdf"),
    ("output", "pdf"),
    ("mime", "application/pdf"),
    ("content_type", "application/pdf"),
    ("content-type", "application/pdf"),
)


def take_smart_screenshot(
    tool: Any,
    *,
    page: Any,
    final_url: str,
    include_screenshot: bool,
    timeout_seconds: int,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    if not include_screenshot:
        return None, None, None

    is_pdf = is_pdf_url(final_url)
    if not is_pdf:
        _wait_for_html_stability(tool, page, timeout_seconds=timeout_seconds)
        return take_browser_screenshot(page, tool=tool, strategy="html_direct")

    tool._log(f"PDF detected for screenshot: {final_url}")

    if tool._settings.pdf_screenshot_prefer_fitz and fitz is not None:
        fitz_result = try_fitz_screenshot(
            tool,
            url=final_url,
            timeout_seconds=timeout_seconds,
        )
        if fitz_result is not None:
            return fitz_result
        tool._log("fitz screenshot failed, falling back to browser screenshot")

    return take_pdf_browser_screenshot(
        tool,
        page=page,
        pdf_url=final_url,
        timeout_seconds=timeout_seconds,
    )


def try_fitz_screenshot(
    tool: Any,
    *,
    url: str,
    timeout_seconds: int,
) -> tuple[str, str, dict[str, Any]] | None:
    if fitz is None:
        return None

    try:
        temp_path = download_pdf_to_temp(tool, url, timeout_seconds)
    except Exception as exc:
        tool._log(f"Could not download PDF for fitz: {exc}")
        return None

    try:
        b64 = capture_pdf_screenshot(
            temp_path,
            page_number=0,
            dpi=tool._settings.pdf_screenshot_dpi,
        )
        meta: dict[str, Any] = {
            "method": "fitz_direct_render",
            "dpi": tool._settings.pdf_screenshot_dpi,
            "source_url": url,
        }
        tool._log("PDF screenshot generated via PyMuPDF")
        return b64, "image/png", meta
    except Exception as exc:
        tool._log(f"fitz render failed: {exc}")
        return None
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def download_pdf_to_temp(tool: Any, url: str, timeout_seconds: int) -> str:
    req = Request(
        url,
        headers={"User-Agent": tool._settings.driver_settings.user_agent},
    )
    with urlopen(req, timeout=timeout_seconds) as response:
        content = response.read()

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf",
        prefix="aither_pdf_screenshot_",
    ) as tmp:
        tmp.write(content)
        return tmp.name


def take_pdf_browser_screenshot(
    tool: Any,
    *,
    page: Any,
    pdf_url: str,
    timeout_seconds: int,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    wait_ms = tool._settings.pdf_browser_wait_ms
    max_retries = tool._settings.pdf_browser_max_retries
    retry_wait_ms = tool._settings.pdf_browser_retry_wait_ms

    tool._log(f"Waiting {wait_ms}ms for PDF viewer render")
    page.wait_for_timeout(wait_ms)

    best_b64: str | None = None
    was_blank = False

    for attempt in range(1, max_retries + 1):
        screenshot_bytes = page.screenshot(type="png", full_page=False)
        b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        if not tool._settings.blank_detection_enabled:
            tool._log(f"PDF screenshot taken (attempt {attempt}, without blank detection)")
            return b64, "image/png", {
                "method": "browser_pdf",
                "attempt": attempt,
                "wait_ms": wait_ms,
                "blank_detection": False,
            }

        is_blank = is_blank_screenshot(screenshot_bytes)
        if not is_blank:
            tool._log(f"Valid PDF screenshot (attempt {attempt})")
            return b64, "image/png", {
                "method": "browser_pdf",
                "attempt": attempt,
                "wait_ms": wait_ms,
                "was_blank_before": was_blank,
            }

        was_blank = True
        best_b64 = b64

        if attempt < max_retries:
            tool._log(
                f"Blank PDF screenshot (attempt {attempt}/{max_retries}), "
                f"waiting another {retry_wait_ms}ms..."
            )
            page.wait_for_timeout(retry_wait_ms)

    tool._log(f"PDF screenshot remains blank after {max_retries} attempts")

    if fitz is not None:
        tool._log("Attempting final fallback with PyMuPDF")
        fitz_result = try_fitz_screenshot(
            tool,
            url=pdf_url,
            timeout_seconds=timeout_seconds,
        )
        if fitz_result is not None:
            b64, mime, meta = fitz_result
            meta["was_browser_blank_fallback"] = True
            meta["browser_attempts"] = max_retries
            return b64, mime, meta

    tool._log("Returning browser screenshot (possibly blank)")
    return best_b64, "image/png", {
        "method": "browser_pdf_blank",
        "attempts": max_retries,
        "total_wait_ms": wait_ms + (retry_wait_ms * (max_retries - 1)),
        "is_likely_blank": True,
    }


def take_browser_screenshot(
    page: Any,
    *,
    tool: Any | None = None,
    strategy: str = "direct",
) -> tuple[str, str, dict[str, Any]]:
    if tool is not None:
        pre_wait_ms = int(getattr(getattr(tool, "_settings", None), "html_pre_screenshot_wait_ms", 700) or 700)
        try:
            page.wait_for_timeout(max(0, pre_wait_ms))
        except Exception:
            pass
    screenshot_bytes = page.screenshot(type="png", full_page=False)
    b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    return b64, "image/png", {"method": strategy}


def _wait_for_html_stability(tool: Any, page: Any, *, timeout_seconds: int) -> None:
    settings = getattr(tool, "_settings", None)
    total_timeout_ms = max(500, int(timeout_seconds * 1000))
    load_wait_ms = int(getattr(settings, "html_load_wait_ms", 1500) or 1500)
    networkidle_wait_ms = int(getattr(settings, "html_networkidle_wait_ms", 2500) or 2500)
    settle_wait_ms = int(getattr(settings, "html_settle_wait_ms", 900) or 900)

    try:
        page.wait_for_load_state("load", timeout=min(load_wait_ms, total_timeout_ms))
    except Exception:
        pass

    try:
        page.wait_for_load_state("networkidle", timeout=min(networkidle_wait_ms, total_timeout_ms))
    except Exception:
        pass

    try:
        page.wait_for_timeout(min(settle_wait_ms, total_timeout_ms))
    except Exception:
        pass


def is_blank_screenshot(png_bytes: bytes) -> bool:
    try:
        width, height, pixel_data = decode_png_pixels(png_bytes)
    except Exception:
        return False

    if not pixel_data or width == 0 or height == 0:
        return True

    return luminance_variance_is_low(
        pixel_data=pixel_data,
        width=width,
        height=height,
    )


def decode_png_pixels(png_bytes: bytes) -> tuple[int, int, bytes]:
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG")

    width = 0
    height = 0
    bit_depth = 0
    color_type = 0
    idat_chunks: list[bytes] = []

    pos = 8
    while pos < len(png_bytes):
        if pos + 8 > len(png_bytes):
            break

        chunk_len = struct.unpack(">I", png_bytes[pos:pos + 4])[0]
        chunk_type = png_bytes[pos + 4:pos + 8]
        chunk_data = png_bytes[pos + 8:pos + 8 + chunk_len]

        if chunk_type == b"IHDR":
            width = struct.unpack(">I", chunk_data[0:4])[0]
            height = struct.unpack(">I", chunk_data[4:8])[0]
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
        elif chunk_type == b"IDAT":
            idat_chunks.append(chunk_data)
        elif chunk_type == b"IEND":
            break

        pos += 12 + chunk_len

    if not idat_chunks or width == 0:
        return 0, 0, b""

    compressed = b"".join(idat_chunks)
    raw = zlib.decompress(compressed)

    if color_type == 2:
        bpp = 3
    elif color_type == 6:
        bpp = 4
    else:
        bpp = max(1, bit_depth // 8)

    stride = 1 + width * bpp
    pixels = bytearray()
    for y in range(height):
        offset = y * stride + 1
        pixels.extend(raw[offset:offset + width * bpp])

    return width, height, bytes(pixels)


def luminance_variance_is_low(
    *,
    pixel_data: bytes,
    width: int,
    height: int,
    threshold: float = _BLANK_VARIANCE_THRESHOLD,
    sample_step: int = _BLANK_SAMPLE_STEP,
) -> bool:
    total_pixels = width * height
    data_len = len(pixel_data)

    if total_pixels == 0:
        return True

    bpp = data_len // total_pixels
    if bpp < 3:
        bpp = 3

    samples: list[float] = []
    for i in range(0, data_len - bpp + 1, bpp * sample_step):
        r = pixel_data[i]
        g = pixel_data[i + 1]
        b = pixel_data[i + 2]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        samples.append(lum)

    if len(samples) < 10:
        return True

    mean = sum(samples) / len(samples)
    variance = sum((s - mean) ** 2 for s in samples) / len(samples)
    return variance < threshold


def is_pdf_url(url: str) -> bool:
    raw = str(url or "").strip()
    if not raw:
        return False

    parsed = urlparse(raw)
    path = (parsed.path or "").lower().strip()
    if any(path.endswith(suffix) for suffix in _PDF_URL_SUFFIXES):
        return True

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    normalized_pairs = [(k.lower().strip(), v.lower().strip()) for k, v in query_pairs]

    for expected_key, expected_value in _PDF_QUERY_MARKERS:
        for key, value in normalized_pairs:
            if key == expected_key and value == expected_value:
                return True

    return False
