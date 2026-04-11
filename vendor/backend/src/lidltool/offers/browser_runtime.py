from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from lidltool.config import AppConfig
from lidltool.connectors.auth.browser_runtime import (
    launch_playwright_chromium_persistent_context,
)
from lidltool.db.models import OfferSourceConfig

_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)
_ABORT_RESOURCE_TYPES = {"font", "image", "media"}
_CAPTURE_RESPONSE_RESOURCE_TYPES = {"fetch", "xhr"}
_BROWSER_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--lang=de-DE",
]
_OFFER_URL_HINTS = (
    "angebot",
    "angebote",
    "coupon",
    "deal",
    "discount",
    "offer",
    "preis",
    "product",
    "promo",
    "prospekt",
    "sale",
)
_COOKIE_BUTTON_LABELS = (
    "Accept",
    "Accept All",
    "Accept all",
    "Akzeptieren",
    "Alle akzeptieren",
    "Einverstanden",
    "I agree",
    "OK",
    "Zustimmen",
)
_MAX_CAPTURED_RESPONSES = 12
_MAX_CAPTURED_RESPONSE_BODY_CHARS = 12000
_MAX_CAPTURED_HTML_CHARS = 120000


@dataclass(slots=True)
class BrowserCapturedResponse:
    url: str
    status: int
    content_type: str | None
    resource_type: str
    body_excerpt: str


@dataclass(slots=True)
class BrowserOfferPageCapture:
    source_url: str
    final_url: str
    page_title: str | None
    html: str
    notes: list[str]
    responses: list[BrowserCapturedResponse]

    def as_prompt_sections(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "final_url": self.final_url,
            "page_title": self.page_title,
            "notes": list(self.notes),
            "responses": [asdict(response) for response in self.responses],
        }


def capture_offer_page_with_browser(
    *,
    config: AppConfig,
    source: OfferSourceConfig,
) -> BrowserOfferPageCapture:
    profile_dir = offer_browser_profile_dir(config=config, source_id=source.source_id)
    profile_dir.mkdir(parents=True, exist_ok=True)
    _clear_stale_profile_locks(profile_dir)

    navigation_timeout_ms = max(int(config.offers_browser_timeout_s * 1000), 1000)
    notes: list[str] = []
    responses: list[BrowserCapturedResponse] = []
    with sync_playwright() as playwright:
        context = launch_playwright_chromium_persistent_context(
            playwright=playwright,
            user_data_dir=profile_dir,
            headless=config.offers_browser_headless,
            args=_BROWSER_LAUNCH_ARGS,
            locale="de-DE",
            user_agent=_BROWSER_USER_AGENT,
            viewport={"width": 1440, "height": 2200},
            ignore_https_errors=True,
            java_script_enabled=True,
            service_workers="block",
            timezone_id=_offer_browser_timezone_id(source),
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        context.set_default_navigation_timeout(navigation_timeout_ms)
        context.set_default_timeout(min(navigation_timeout_ms, 15000))
        with suppress(PlaywrightError):
            context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['de-DE', 'de', 'en-US', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4] });
                window.chrome = window.chrome || { runtime: {} };
                """
            )

        def handle_route(route: Any) -> None:
            request = route.request
            if request.resource_type in _ABORT_RESOURCE_TYPES:
                route.abort()
                return
            route.continue_()

        def handle_response(response: Any) -> None:
            request = response.request
            resource_type = str(request.resource_type or "")
            response_url = str(response.url or "")
            content_type = response.headers.get("content-type")
            lowered_url = response_url.lower()
            if response.status >= 400 and resource_type in {"document", "fetch", "xhr"}:
                _append_note(
                    notes,
                    f"{resource_type.upper()} {response.status} for {response_url}",
                )
            if len(responses) >= _MAX_CAPTURED_RESPONSES:
                return
            if resource_type not in _CAPTURE_RESPONSE_RESOURCE_TYPES:
                return
            captures_json = isinstance(content_type, str) and "json" in content_type.lower()
            offer_like_url = any(hint in lowered_url for hint in _OFFER_URL_HINTS)
            if not captures_json and not offer_like_url:
                return
            try:
                body = response.text()
            except PlaywrightError:
                return
            normalized_body = body.strip()
            if not normalized_body:
                return
            responses.append(
                BrowserCapturedResponse(
                    url=response_url,
                    status=int(response.status),
                    content_type=content_type,
                    resource_type=resource_type,
                    body_excerpt=normalized_body[:_MAX_CAPTURED_RESPONSE_BODY_CHARS],
                )
            )

        context.route("**/*", handle_route)
        context.on("response", handle_response)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page_response = page.goto(
                source.merchant_url,
                wait_until="domcontentloaded",
                timeout=navigation_timeout_ms,
            )
            if page_response is not None and page_response.status >= 400:
                _append_note(
                    notes,
                    f"Document response returned HTTP {page_response.status} for {source.merchant_url}",
                )
            _dismiss_cookie_banners(page)
            _wait_for_offer_page_settle(page)
            _dismiss_cookie_banners(page)
            html = page.content()[:_MAX_CAPTURED_HTML_CHARS]
            final_url = str(page.url or source.merchant_url)
            with suppress(PlaywrightError):
                title = page.title()
            if "title" not in locals():
                title = None
            _record_block_signals(notes=notes, html=html, final_url=final_url)
        except PlaywrightError as exc:
            raise RuntimeError(f"browser offer fetch failed for {source.merchant_url}: {exc}") from exc
        finally:
            context.close()

    return BrowserOfferPageCapture(
        source_url=source.merchant_url,
        final_url=final_url,
        page_title=title,
        html=html,
        notes=notes,
        responses=responses,
    )


def offer_browser_profile_dir(*, config: AppConfig, source_id: str) -> Path:
    return (config.config_dir / "offers" / "browser_profiles" / source_id).expanduser().resolve()


def _clear_stale_profile_locks(profile_dir: Path) -> None:
    for name in ("SingletonCookie", "SingletonLock", "SingletonSocket"):
        with suppress(FileNotFoundError):
            (profile_dir / name).unlink()


def _offer_browser_timezone_id(source: OfferSourceConfig) -> str:
    if source.country_code.strip().upper() == "DE":
        return "Europe/Berlin"
    return "UTC"


def _wait_for_offer_page_settle(page: Any) -> None:
    with suppress(PlaywrightError):
        page.wait_for_load_state("networkidle", timeout=8000)
    page.wait_for_timeout(1200)
    with suppress(PlaywrightError):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(400)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(250)


def _dismiss_cookie_banners(page: Any) -> None:
    for label in _COOKIE_BUTTON_LABELS:
        with suppress(PlaywrightError):
            locator = page.get_by_role("button", name=label)
            if locator.count() > 0:
                locator.first.click(timeout=1200)
                page.wait_for_timeout(300)
                return
        with suppress(PlaywrightError):
            locator = page.locator(f"text={label}")
            if locator.count() > 0:
                locator.first.click(timeout=1200)
                page.wait_for_timeout(300)
                return


def _record_block_signals(*, notes: list[str], html: str, final_url: str) -> None:
    lowered_html = html.lower()
    lowered_url = final_url.lower()
    if any(token in lowered_url for token in ("captcha", "challenge")):
        _append_note(notes, f"Final URL suggests an anti-bot challenge: {final_url}")
    for marker in (
        "access denied",
        "forbidden",
        "captcha",
        "robot",
        "security check",
        "unusual traffic",
    ):
        if marker in lowered_html:
            _append_note(notes, f"Rendered page contains possible block marker: {marker}")


def _append_note(notes: list[str], note: str) -> None:
    normalized = note.strip()
    if not normalized or normalized in notes or len(notes) >= 12:
        return
    notes.append(normalized)
