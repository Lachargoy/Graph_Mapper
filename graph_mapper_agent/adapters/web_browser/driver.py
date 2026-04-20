
from __future__ import annotations
#aither/adapters/tools/web_browser/driver.py
import tempfile
from dataclasses import dataclass
from typing import Any

try:
    from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
    from playwright.sync_api import Error as PlaywrightError
except ImportError:
    sync_playwright = None
    PlaywrightError = Exception
    Browser = Any
    BrowserContext = Any
    Page = Any


@dataclass(frozen=True)
class DriverSettings:
    browser_name: str = "chromium"
    headless: bool = False
    user_agent: str = "AitherWebAgent/1.0"
    default_timeout_ms: int = 30000
    default_navigation_timeout_ms: int = 30000
    slow_mo_ms: int = 300


@dataclass(frozen=True)
class DownloadResult:
    path: str
    filename: str
    url: str
    suggested_filename: str


class PlaywrightDriver:
    """
    Infrastructure wrapper over Playwright.
    Manages the lifecycle of the browser process and isolated contexts.
    """

    def __init__(self, settings: DriverSettings | None = None) -> None:
        self._settings = settings or DriverSettings()
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._persistent_page: Page | None = None

    def start(self) -> None:
        """Starts the browser process if it is not running."""
        if self._playwright is not None:
            return

        if sync_playwright is None:
            raise RuntimeError("Playwright not installed. pip install playwright")

        self._playwright = sync_playwright().start()
        launcher = getattr(self._playwright, self._settings.browser_name)

        self._browser = launcher.launch(
            headless=self._settings.headless,
        )

    def stop(self) -> None:
        """Stops and cleans up all resources."""
        self.reset_persistent_page(reason="driver_stop")

        if self._context:
            self._context.close()
            self._context = None

        if self._browser:
            self._browser.close()
            self._browser = None

        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def new_page(self) -> Page:
        """
        Creates a new page in the current context.
        Starts the driver if necessary.
        """
        self._ensure_context()
        if not self._context:
            raise RuntimeError("Could not initialize the browser context")

        page = self._context.new_page()
        self._apply_page_timeouts(page)
        return page

    def get_persistent_page(self) -> Page:
        """
        Reuses a single visible tab between steps for inspection/navigation.
        """
        if self._persistent_page is not None:
            is_closed = getattr(self._persistent_page, "is_closed", None)
            if callable(is_closed):
                try:
                    if not is_closed():
                        self._apply_page_timeouts(self._persistent_page)
                        return self._persistent_page
                except Exception:
                    pass
            else:
                self._apply_page_timeouts(self._persistent_page)
                return self._persistent_page

        self._persistent_page = self.new_page()
        return self._persistent_page

    def reset_persistent_page(self, reason: str = "manual_reset") -> None:
        page = self._persistent_page
        self._persistent_page = None

        if page is None:
            return

        try:
            print(f"[driver.reset_persistent_page] reason={reason}", flush=True)
            page.close()
        except Exception as exc:
            print(
                f"[driver.reset_persistent_page] close error reason={reason} exc={exc!r}",
                flush=True,
            )

    def _ensure_context(self) -> None:
        if self._context:
            return

        self.start()
        if not self._browser:
            raise RuntimeError("Browser not started correctly")

        self._context = self._browser.new_context(
            user_agent=self._settings.user_agent,
            accept_downloads=True,
        )
        self._context.set_default_timeout(self._settings.default_timeout_ms)
        try:
            self._context.set_default_navigation_timeout(
                self._settings.default_navigation_timeout_ms
            )
        except Exception:
            pass

    def _apply_page_timeouts(self, page: Page) -> None:
        try:
            page.set_default_timeout(self._settings.default_timeout_ms)
        except Exception:
            pass

        try:
            page.set_default_navigation_timeout(
                self._settings.default_navigation_timeout_ms
            )
        except Exception:
            pass

    def download_file(self, url: str, timeout_ms: int | None = None) -> DownloadResult:
        page = self.new_page()
        effective_timeout_ms = timeout_ms or self._settings.default_timeout_ms

        print(f"[driver.download_file] url={url}", flush=True)
        print(
            f"[driver.download_file] timeout_ms={effective_timeout_ms}",
            flush=True,
        )

        try:
            with page.expect_download(timeout=effective_timeout_ms) as download_info:
                try:
                    print("[driver.download_file] about to goto()", flush=True)
                    page.goto(url, wait_until="commit", timeout=effective_timeout_ms)
                    print("[driver.download_file] goto() returned", flush=True)
                except Exception as exc:
                    print(f"[driver.download_file] goto exception={exc!r}", flush=True)
                    if "Download is starting" not in str(exc) and "net::ERR_ABORTED" not in str(exc):
                        raise

            print("[driver.download_file] download event captured", flush=True)

            download = download_info.value
            print(
                f"[driver.download_file] suggested_filename={download.suggested_filename} "
                f"url={download.url}",
                flush=True,
            )

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                target_path = tmp.name

            download.save_as(target_path)
            print(f"[driver.download_file] saved_as={target_path}", flush=True)

            return DownloadResult(
                path=target_path,
                filename=download.suggested_filename,
                url=download.url,
                suggested_filename=download.suggested_filename
            )

        finally:
            print("[driver.download_file] closing page", flush=True)
            try:
                page.close()
            except Exception:
                pass