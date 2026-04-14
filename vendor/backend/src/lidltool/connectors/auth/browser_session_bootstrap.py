from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


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
) -> bool:
    ensure_state_parent(state_file)

    with sync_playwright() as playwright:
        from lidltool.connectors.auth.browser_runtime import launch_playwright_chromium

        browser = launch_playwright_chromium(playwright=playwright, headless=False)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                page.goto(login_url, wait_until="domcontentloaded")

                print(instructions, flush=True)
                print(
                    "The desktop app will keep checking the saved session until the account page is available.",
                    flush=True,
                )

                attempts = max(1, int((timeout_seconds * 1000) / max(1, poll_interval_ms)))
                last_probe: SessionValidationProbeResult | None = None
                for _ in range(attempts):
                    probe = _session_probe(
                        context=context,
                        validation_url=validation_url,
                        blocked_url_patterns=blocked_url_patterns,
                        blocked_html_markers=blocked_html_markers,
                        probe_validator=probe_validator,
                    )
                    if probe is not None:
                        last_probe = probe
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
                    validation_url=validation_url,
                    blocked_url_patterns=blocked_url_patterns,
                    blocked_html_markers=blocked_html_markers,
                    probe_validator=probe_validator,
                )
                if final_probe is not None:
                    last_probe = final_probe
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
            browser.close()


def _session_probe(
    *,
    context: Any,
    validation_url: str,
    blocked_url_patterns: Iterable[str],
    blocked_html_markers: Iterable[str],
    probe_validator: Callable[[str, str], SessionValidationProbeResult] | None = None,
) -> SessionValidationProbeResult | None:
    probe = _fetch_validation_probe(context=context, validation_url=validation_url)
    if probe is None:
        return None
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


def _write_debug_probe_html(
    *,
    debug_html_dir: Path,
    probe: SessionValidationProbeResult,
) -> None:
    debug_html_dir.mkdir(parents=True, exist_ok=True)
    suffix = probe.state or "unknown"
    target = debug_html_dir / f"session_probe_{suffix}.html"
    target.write_text(probe.html, encoding="utf-8")
