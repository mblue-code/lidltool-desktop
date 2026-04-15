from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

_INITIAL_LOGIN_FIELD_SELECTORS: tuple[str, ...] = (
    "#ap_email",
    "#auth-email",
    'input[type="email"]',
    'input[name="email"]',
    'input[name="emailOrPhoneNumber"]',
    'input[name="username"]',
    'input[type="tel"]',
    'input[type="text"]',
)


@dataclass(frozen=True, slots=True)
class SessionValidationProbeResult:
    authenticated: bool
    url: str
    html: str
    state: str | None = None
    detail: str | None = None


def session_validation_looks_authenticated(
    *,
    url: str,
    html: str,
    blocked_url_patterns: Iterable[str],
    blocked_html_markers: Iterable[str] = (),
) -> bool:
    return session_validation_probe(
        url=url,
        html=html,
        blocked_url_patterns=blocked_url_patterns,
        blocked_html_markers=blocked_html_markers,
    ).authenticated


def session_validation_probe(
    *,
    url: str,
    html: str,
    blocked_url_patterns: Iterable[str],
    blocked_html_markers: Iterable[str] = (),
) -> SessionValidationProbeResult:
    normalized_url = url.strip().lower()
    if any(pattern.strip().lower() in normalized_url for pattern in blocked_url_patterns if pattern.strip()):
        return SessionValidationProbeResult(
            authenticated=False,
            url=url,
            html=html,
            state="blocked_url",
        )

    normalized_html = html.lower()
    if any(marker.strip().lower() in normalized_html for marker in blocked_html_markers if marker.strip()):
        return SessionValidationProbeResult(
            authenticated=False,
            url=url,
            html=html,
            state="blocked_html",
        )

    return SessionValidationProbeResult(authenticated=True, url=url, html=html, state="authenticated")


def run_headful_browser_session_bootstrap(
    state_file: Path,
    *,
    ensure_state_parent: Callable[[Path], None],
    login_url: str,
    validation_url: str,
    instructions: str,
    blocked_url_patterns: Iterable[str],
    blocked_html_markers: Iterable[str] = (),
    timeout_seconds: int = 300,
    poll_interval_ms: int = 500,
    probe_validator: Callable[[str, str], SessionValidationProbeResult] | None = None,
    debug_html_dir: Path | None = None,
    user_data_dir: Path | None = None,
) -> bool:
    ensure_state_parent(state_file)
    if user_data_dir is not None:
        user_data_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        from lidltool.connectors.auth.browser_runtime import (
            launch_playwright_chromium,
            launch_playwright_chromium_persistent_context,
        )

        browser = None
        try:
            if user_data_dir is not None:
                context = launch_playwright_chromium_persistent_context(
                    playwright=playwright,
                    user_data_dir=user_data_dir,
                    headless=False,
                )
            else:
                browser = launch_playwright_chromium(playwright=playwright, headless=False)
                context = browser.new_context()
            try:
                page = context.new_page()
                page.goto(login_url, wait_until="domcontentloaded")
                _focus_initial_login_field(page=page)

                print(instructions, flush=True)
                print(
                    "The desktop app will keep checking the saved session until the account page is available.",
                    flush=True,
                )

                attempts = max(1, int((timeout_seconds * 1000) / max(1, poll_interval_ms)))
                last_probe: SessionValidationProbeResult | None = None
                last_reported_wait_state: tuple[str | None, str | None] | None = None
                for _ in range(attempts):
                    probe = _session_probe(
                        context=context,
                        page=page,
                        validation_url=validation_url,
                        blocked_url_patterns=blocked_url_patterns,
                        blocked_html_markers=blocked_html_markers,
                        probe_validator=probe_validator,
                    )
                    if probe is not None:
                        last_probe = probe
                        wait_state = (probe.state, probe.detail)
                        if not probe.authenticated and wait_state != last_reported_wait_state:
                            _print_waiting_probe_state(probe)
                            last_reported_wait_state = wait_state
                    if probe is not None and probe.authenticated:
                        context.storage_state(path=str(state_file))
                        print("Session validated and saved.", flush=True)
                        return True
                    if probe is not None and debug_html_dir is not None and probe.html:
                        _write_debug_probe_html(debug_html_dir=debug_html_dir, probe=probe)
                    try:
                        page.wait_for_timeout(poll_interval_ms)
                    except Exception:  # noqa: BLE001
                        break

                final_probe = _session_probe(
                    context=context,
                    page=page,
                    validation_url=validation_url,
                    blocked_url_patterns=blocked_url_patterns,
                    blocked_html_markers=blocked_html_markers,
                    probe_validator=probe_validator,
                )
                if final_probe is not None:
                    last_probe = final_probe
                    wait_state = (final_probe.state, final_probe.detail)
                    if not final_probe.authenticated and wait_state != last_reported_wait_state:
                        _print_waiting_probe_state(final_probe)
                if final_probe is not None and final_probe.authenticated:
                    context.storage_state(path=str(state_file))
                    print("Session validated and saved.", flush=True)
                    return True

                if last_probe is not None and last_probe.detail:
                    print(last_probe.detail, flush=True)
                else:
                    print(
                        "Session capture timed out before the account page became available.",
                        flush=True,
                    )
                return False
            finally:
                context.close()
        finally:
            if browser is not None:
                browser.close()


def _focus_initial_login_field(*, page: Any) -> None:
    for selector in _INITIAL_LOGIN_FIELD_SELECTORS:
        try:
            locator = page.locator(selector).first
            locator.focus()
            return
        except Exception:  # noqa: BLE001
            continue


def _session_probe(
    *,
    context: Any,
    page: Any,
    validation_url: str,
    blocked_url_patterns: Iterable[str],
    blocked_html_markers: Iterable[str],
    probe_validator: Callable[[str, str], SessionValidationProbeResult] | None = None,
) -> SessionValidationProbeResult | None:
    page_probe = _fetch_current_page_probe(page=page)
    if page_probe is not None:
        url, html = page_probe
        if probe_validator is not None:
            validated = probe_validator(url, html)
        else:
            validated = session_validation_probe(
                url=url,
                html=html,
                blocked_url_patterns=blocked_url_patterns,
                blocked_html_markers=blocked_html_markers,
            )
        if validated.authenticated:
            return validated

    probe = _fetch_validation_probe(context=context, validation_url=validation_url)
    if probe is None:
        return validated if page_probe is not None else None
    url, html = probe
    if probe_validator is not None:
        return probe_validator(url, html)
    return session_validation_probe(
        url=url,
        html=html,
        blocked_url_patterns=blocked_url_patterns,
        blocked_html_markers=blocked_html_markers,
    )


def _fetch_validation_probe(
    *,
    context: Any,
    validation_url: str,
) -> tuple[str, str] | None:
    try:
        response = context.request.get(validation_url)
    except Exception:  # noqa: BLE001
        return None

    url = str(getattr(response, "url", "") or validation_url)
    try:
        html = response.text()
    except Exception:  # noqa: BLE001
        html = ""
    return url, html


def _fetch_current_page_probe(*, page: Any) -> tuple[str, str] | None:
    try:
        url = str(getattr(page, "url", "") or "")
    except Exception:  # noqa: BLE001
        url = ""
    if not url:
        return None

    try:
        html = page.content()
    except Exception:  # noqa: BLE001
        html = ""
    return url, html


def _write_debug_probe_html(
    *,
    debug_html_dir: Path,
    probe: SessionValidationProbeResult,
) -> None:
    debug_html_dir.mkdir(parents=True, exist_ok=True)
    suffix = probe.state or "unknown"
    target = debug_html_dir / f"session_probe_{suffix}.html"
    target.write_text(probe.html, encoding="utf-8")


def _print_waiting_probe_state(probe: SessionValidationProbeResult) -> None:
    state = probe.state or "unknown"
    detail = probe.detail or "Authentication is still incomplete."
    print(f"Waiting for auth step: {state}", flush=True)
    print(detail, flush=True)
