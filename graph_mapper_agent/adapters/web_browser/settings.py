from __future__ import annotations

from dataclasses import dataclass, field

from graph_mapper_agent.adapters.web_browser.driver import (
    DriverSettings,
)


@dataclass(frozen=True)
class WebBrowserToolSettings:
    driver_settings: DriverSettings = field(default_factory=DriverSettings)
    max_candidates: int = 15
    store_downloads: bool = True
    max_pages_to_extract: int = 15
    html_load_wait_ms: int = 1_500
    html_networkidle_wait_ms: int = 2_500
    html_settle_wait_ms: int = 900
    html_pre_screenshot_wait_ms: int = 700
    pdf_screenshot_prefer_fitz: bool = True
    pdf_screenshot_dpi: int = 150
    pdf_browser_wait_ms: int = 2_000
    pdf_browser_retry_wait_ms: int = 2_500
    pdf_browser_max_retries: int = 2
    blank_detection_enabled: bool = True
