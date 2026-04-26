from __future__ import annotations

import html
import os
import secrets
import socket
import subprocess
import shutil
import sys
import time
import urllib.parse
import urllib.request
from contextlib import suppress
from tempfile import TemporaryDirectory
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from lidltool.connectors.sdk.runtime import (
    AUTH_BROWSER_METADATA_KEY,
    AuthBrowserMode,
    AuthBrowserPlan,
    AuthBrowserResult,
    AuthBrowserStartRequest,
    build_auth_browser_metadata,
    build_auth_browser_runtime_context,
    parse_auth_browser_runtime_context,
    parse_auth_browser_start_request,
)

AUTH_BROWSER_MODE_ENV = "LIDLTOOL_AUTH_BROWSER_MODE"
AUTH_BROWSER_EXECUTABLE_ENV = "LIDLTOOL_PLAYWRIGHT_BROWSER_EXECUTABLE_PATH"
AUTH_BROWSER_CHANNEL_ENV = "LIDLTOOL_PLAYWRIGHT_BROWSER_CHANNEL"
AUTH_BROWSER_PREFER_EXTERNAL_CHROMIUM_ENV = "LIDLTOOL_AUTH_BROWSER_PREFER_EXTERNAL_CHROMIUM"


@dataclass(frozen=True, slots=True)
class AuthBrowserSessionHandle:
    session_id: str
    flow_id: str
    mode: AuthBrowserMode
    start_url: str
    started_at: datetime


@dataclass(frozen=True, slots=True)
class AuthBrowserStartResult:
    handle: AuthBrowserSessionHandle


class AuthBrowserRuntimeService:
    def start_session(
        self,
        request: AuthBrowserStartRequest,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> AuthBrowserStartResult:
        env = dict(os.environ if environment is None else environment)
        handle = AuthBrowserSessionHandle(
            session_id=secrets.token_hex(12),
            flow_id=request.flow_id,
            mode=self._resolve_mode(env=env, interactive=request.plan.interactive),
            start_url=request.plan.start_url,
            started_at=datetime.now(tz=UTC),
        )
        return AuthBrowserStartResult(handle=handle)

    def run(
        self,
        request: AuthBrowserStartRequest,
        *,
        environment: Mapping[str, str] | None = None,
    ) -> AuthBrowserResult:
        env = dict(os.environ if environment is None else environment)
        started = self.start_session(request, environment=env)
        callback_url, storage_state = self._capture_browser_result(
            request=request,
            environment=env,
        )
        completed_at = datetime.now(tz=UTC)
        return AuthBrowserResult(
            flow_id=request.flow_id,
            session_id=started.handle.session_id,
            mode=started.handle.mode,
            start_url=request.plan.start_url,
            final_url=callback_url,
            callback_url=callback_url,
            started_at=started.handle.started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            storage_state=storage_state,
        )

    def _capture_browser_result(
        self,
        *,
        request: AuthBrowserStartRequest,
        environment: Mapping[str, str],
    ) -> tuple[str, dict[str, Any] | None]:
        callback_prefixes = tuple(request.plan.callback_url_prefixes)
        normalized_start_url = _normalize_browser_url(request.plan.start_url)
        mode = self._resolve_mode(env=environment, interactive=request.plan.interactive)
        headless = mode == "headless_capture_only"
        if request.plan.interactive and mode == "headless_capture_only":
            raise RuntimeError(
                "interactive browser auth requires a display. Start bootstrap through the web UI "
                "or provide DISPLAY for a local browser session."
            )
        if _should_use_external_chromium_handoff(
            plan=request.plan,
            mode=mode,
            environment=environment,
        ):
            return _capture_external_chromium_result(
                request=request,
                environment=environment,
            )

        with sync_playwright() as playwright:
            with TemporaryDirectory(prefix="lidltool-auth-browser-") as user_data_dir:
                context = launch_playwright_chromium_persistent_context(
                    playwright=playwright,
                    user_data_dir=user_data_dir,
                    headless=headless,
                    environment=environment,
                )
                page = context.new_page()

                try:
                    page.goto(request.plan.start_url, wait_until=request.plan.wait_until)
                except PlaywrightError as exc:
                    context.close()
                    raise RuntimeError(f"browser auth session failed to open login page: {exc}") from exc
                try:
                    result = _capture_callback_from_context(
                        context=context,
                        page=page,
                        request=request,
                        normalized_start_url=normalized_start_url,
                        callback_prefixes=callback_prefixes,
                    )
                    context.close()
                except PlaywrightError as exc:
                    context.close()
                    raise RuntimeError(f"browser auth storage-state capture failed: {exc}") from exc
        return result

    def _resolve_mode(
        self,
        *,
        env: Mapping[str, str],
        interactive: bool,
    ) -> AuthBrowserMode:
        mode_hint = str(env.get(AUTH_BROWSER_MODE_ENV) or "").strip().lower()
        if mode_hint in {"local_display", "remote_vnc", "headless_capture_only"}:
            return mode_hint  # type: ignore[return-value]
        display = str(env.get("DISPLAY") or os.environ.get("DISPLAY") or "").strip()
        if display:
            return "local_display"
        # Native desktop platforms can run a headed Playwright browser without X11 DISPLAY.
        if interactive and sys.platform in {"darwin", "win32"}:
            return "local_display"
        if interactive:
            return "headless_capture_only"
        return "headless_capture_only"


def _discover_callback_candidate(
    *,
    context: Any,
    start_url: str,
    callback_prefixes: tuple[str, ...],
    require_navigation_away_before_completion: bool,
    expected_callback_state: str | None,
    saw_navigation_away: bool,
) -> str | None:
    for page in list(getattr(context, "pages", ())):
        candidate = _discover_callback_candidate_from_page(
            page=page,
            callback_prefixes=callback_prefixes,
        )
        if _should_accept_callback_candidate(
            candidate=candidate,
            start_url=start_url,
            require_navigation_away_before_completion=require_navigation_away_before_completion,
            expected_callback_state=expected_callback_state,
            saw_navigation_away=saw_navigation_away,
        ):
            return candidate
    return None


def _discover_callback_candidate_from_page(
    *,
    page: Any,
    callback_prefixes: tuple[str, ...],
) -> str | None:
    try:
        snapshot = page.evaluate(
            """(prefixes) => {
                const candidates = [];
                const push = (value) => {
                    if (typeof value === "string" && value.trim()) {
                        candidates.push(value.trim());
                    }
                };

                push(window.location?.href ?? "");

                for (const element of document.querySelectorAll("a[href], area[href]")) {
                    push(element.getAttribute("href"));
                }
                for (const element of document.querySelectorAll("form[action]")) {
                    push(element.getAttribute("action"));
                }
                for (const element of document.querySelectorAll("iframe[src]")) {
                    push(element.getAttribute("src"));
                }
                for (const element of document.querySelectorAll("meta[http-equiv]")) {
                    const httpEquiv = (element.getAttribute("http-equiv") || "").toLowerCase();
                    if (httpEquiv === "refresh") {
                        push(element.getAttribute("content"));
                    }
                }

                const matches = [];
                for (const value of candidates) {
                    for (const prefix of prefixes) {
                        const index = value.indexOf(prefix);
                        if (index >= 0) {
                            matches.push(value.slice(index));
                        }
                    }
                }

                return {
                    matches,
                    html: document.documentElement?.outerHTML ?? "",
                    text: document.body?.innerText ?? "",
                };
            }""",
            list(callback_prefixes),
        )
    except PlaywrightError:
        return None

    if not isinstance(snapshot, dict):
        return None

    for raw_value in snapshot.get("matches", ()):
        matched = _match_callback_candidate(str(raw_value or "").strip(), callback_prefixes)
        if matched is not None:
            return matched

    body_text = str(snapshot.get("text") or "")
    matched = _match_callback_candidate(body_text, callback_prefixes)
    if matched is not None:
        return matched
    document_html = str(snapshot.get("html") or "")
    return _match_callback_candidate(document_html, callback_prefixes)


def _match_callback_candidate(candidate: str, callback_prefixes: tuple[str, ...]) -> str | None:
    raw = candidate.strip()
    if not raw:
        return None

    for variant in _callback_candidate_variants(raw):
        for prefix in callback_prefixes:
            index = variant.find(prefix)
            if index < 0:
                continue
            matched = variant[index:]
            for delimiter in ('"', "'", " ", "\n", "\r", "\t", "<", ">", ")", "]", "}", "\\", ";"):
                delimiter_index = matched.find(delimiter)
                if delimiter_index > 0:
                    matched = matched[:delimiter_index]
            return matched.rstrip(".,;")
    return None


def _callback_candidate_variants(candidate: str) -> tuple[str, ...]:
    variants: list[str] = []
    queue = [candidate]
    seen: set[str] = set()
    while queue:
        current = queue.pop(0).strip()
        if not current or current in seen:
            continue
        seen.add(current)
        variants.append(current)

        decoded = urllib.parse.unquote(current)
        if decoded != current:
            queue.append(decoded)

        html_decoded = html.unescape(current)
        if html_decoded != current:
            queue.append(html_decoded)

        js_unescaped = (
            current.replace("\\/", "/")
            .replace("\\u0026", "&")
            .replace("\\u003d", "=")
            .replace("\\u003f", "?")
            .replace("\\u003a", ":")
        )
        if js_unescaped != current:
            queue.append(js_unescaped)

    return tuple(variants)


def _normalize_browser_url(url: str | None) -> str:
    return str(url or "").strip()


def _record_navigation_away(
    *,
    candidate: str | None,
    start_url: str,
    saw_navigation_away: bool,
) -> bool:
    if saw_navigation_away:
        return True
    normalized_candidate = _normalize_browser_url(candidate)
    if not normalized_candidate or normalized_candidate == start_url:
        return False
    parsed = urllib.parse.urlparse(normalized_candidate)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _should_accept_callback_candidate(
    *,
    candidate: str | None,
    start_url: str,
    require_navigation_away_before_completion: bool,
    expected_callback_state: str | None,
    saw_navigation_away: bool,
) -> bool:
    if candidate is None:
        return False
    if not require_navigation_away_before_completion:
        navigation_ok = True
    else:
        normalized_candidate = _normalize_browser_url(candidate)
        if normalized_candidate != start_url:
            navigation_ok = True
        else:
            navigation_ok = saw_navigation_away
    if not navigation_ok:
        return False
    if expected_callback_state is None:
        return True
    parsed = urllib.parse.urlparse(candidate)
    actual_state = urllib.parse.parse_qs(parsed.query).get("state", [None])[0]
    return actual_state == expected_callback_state


def _capture_callback_from_context(
    *,
    context: Any,
    page: Any,
    request: AuthBrowserStartRequest,
    normalized_start_url: str,
    callback_prefixes: tuple[str, ...],
    initial_navigation_away: bool = False,
) -> tuple[str, dict[str, Any] | None]:
    captured_url: str | None = None
    captured_error: str | None = None
    saw_navigation_away = initial_navigation_away

    def capture(url: str | None, *, track_navigation_away: bool = False) -> None:
        nonlocal captured_url, saw_navigation_away
        if track_navigation_away:
            saw_navigation_away = _record_navigation_away(
                candidate=url,
                start_url=normalized_start_url,
                saw_navigation_away=saw_navigation_away,
            )
        matched = _match_callback_candidate(
            str(url or "").strip(),
            callback_prefixes,
        )
        if _should_accept_callback_candidate(
            candidate=matched,
            start_url=normalized_start_url,
            require_navigation_away_before_completion=request.plan.require_navigation_away_before_completion,
            expected_callback_state=request.plan.expected_callback_state,
            saw_navigation_away=saw_navigation_away,
        ):
            captured_url = matched

    def attach_page(connected_page: Any) -> None:
        def handle_frame_navigation(frame: Any) -> None:
            nonlocal saw_navigation_away
            try:
                is_main_frame = frame == connected_page.main_frame
            except Exception:
                is_main_frame = True
            if is_main_frame:
                normalized_url = _normalize_browser_url(getattr(frame, "url", ""))
                if normalized_url and normalized_url != normalized_start_url:
                    saw_navigation_away = True
            capture(getattr(frame, "url", ""), track_navigation_away=is_main_frame)

        connected_page.on("framenavigated", handle_frame_navigation)

    context.on(
        "request",
        lambda req: capture(req.url),
    )
    context.on(
        "requestfailed",
        lambda req: capture(req.url),
    )
    context.on(
        "response",
        lambda res: capture(res.headers.get("location")),
    )
    context.on("page", attach_page)
    attach_page(page)

    print("Browser open: complete login in your browser window.", flush=True)
    deadline = datetime.now(tz=UTC).timestamp() + request.plan.timeout_seconds
    while captured_url is None and captured_error is None:
        captured_url = _discover_callback_candidate(
            context=context,
            start_url=normalized_start_url,
            callback_prefixes=callback_prefixes,
            require_navigation_away_before_completion=request.plan.require_navigation_away_before_completion,
            expected_callback_state=request.plan.expected_callback_state,
            saw_navigation_away=saw_navigation_away,
        )
        if captured_url is not None:
            break
        if datetime.now(tz=UTC).timestamp() >= deadline:
            break
        try:
            page.wait_for_timeout(500)
        except PlaywrightError as exc:
            captured_url = _discover_callback_candidate(
                context=context,
                start_url=normalized_start_url,
                callback_prefixes=callback_prefixes,
                require_navigation_away_before_completion=request.plan.require_navigation_away_before_completion,
                expected_callback_state=request.plan.expected_callback_state,
                saw_navigation_away=saw_navigation_away,
            )
            if captured_url is not None:
                break
            captured_error = str(exc)
            break

    if captured_error is not None:
        raise RuntimeError(f"browser auth session failed before callback capture: {captured_error}")
    if captured_url is None:
        raise RuntimeError(
            "browser auth did not complete before timeout; retry bootstrap and finish the login flow."
        )

    storage_state = context.storage_state() if request.plan.capture_storage_state else None
    if request.plan.capture_storage_state and not isinstance(storage_state, dict):
        raise RuntimeError("browser auth storage-state capture returned no data")
    if request.plan.capture_storage_state:
        cookies = storage_state.get("cookies") if isinstance(storage_state, dict) else None
        origins = storage_state.get("origins") if isinstance(storage_state, dict) else None
        if not cookies and not origins:
            raise RuntimeError("browser auth storage-state capture was empty")
    return captured_url, storage_state


def _capture_external_chromium_result(
    *,
    request: AuthBrowserStartRequest,
    environment: Mapping[str, str],
) -> tuple[str, dict[str, Any] | None]:
    executable_path = _resolve_system_chromium_executable(environment)
    if executable_path is None:
        raise RuntimeError("external browser handoff requires an installed Chromium-based browser on this host")

    port = _allocate_local_port()
    with TemporaryDirectory(prefix="lidltool-auth-browser-") as user_data_dir:
        command = [
            str(executable_path),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            request.plan.start_url,
        ]
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_cdp_endpoint(
                port=port,
                process=process,
                timeout_seconds=min(max(request.plan.timeout_seconds, 15), 30),
            )
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                try:
                    context, page = _resolve_cdp_browser_context(
                        browser=browser,
                        start_url=request.plan.start_url,
                        wait_until=request.plan.wait_until,
                    )
                    return _capture_callback_from_context(
                        context=context,
                        page=page,
                        request=request,
                        normalized_start_url=_normalize_browser_url(request.plan.start_url),
                        callback_prefixes=tuple(request.plan.callback_url_prefixes),
                    )
                finally:
                    with suppress(Exception):
                        browser.close()
        finally:
            _terminate_external_browser_process(process)


def _should_use_external_chromium_handoff(
    *,
    plan: AuthBrowserPlan,
    mode: AuthBrowserMode,
    environment: Mapping[str, str],
    executable_path: Path | None = None,
) -> bool:
    if not plan.interactive or mode == "headless_capture_only":
        return False
    if plan.expected_callback_state is None:
        return False
    if not _bool_env(
        environment,
        AUTH_BROWSER_PREFER_EXTERNAL_CHROMIUM_ENV,
        default=True,
    ):
        return False
    return (executable_path or _resolve_system_chromium_executable(environment)) is not None


def _bool_env(environment: Mapping[str, str], key: str, *, default: bool) -> bool:
    raw_value = str(environment.get(key) or "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    return default


def _allocate_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_for_cdp_endpoint(
    *,
    port: int,
    process: subprocess.Popen[Any],
    timeout_seconds: int,
) -> None:
    deadline = time.monotonic() + max(timeout_seconds, 5)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"external browser exited before the login page became available (exit code {return_code})"
            )
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.25)
    detail = f": {last_error}" if last_error is not None else ""
    raise RuntimeError(f"external browser debugging endpoint did not become ready{detail}")


def _resolve_cdp_browser_context(
    *,
    browser: Any,
    start_url: str,
    wait_until: Literal["domcontentloaded", "load", "networkidle"],
) -> tuple[Any, Any]:
    deadline = time.monotonic() + 15
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        contexts = list(getattr(browser, "contexts", lambda: [])() if callable(getattr(browser, "contexts", None)) else getattr(browser, "contexts", ()))
        if not contexts:
            time.sleep(0.25)
            continue
        context = contexts[0]
        pages = list(getattr(context, "pages", lambda: [])() if callable(getattr(context, "pages", None)) else getattr(context, "pages", ()))
        if pages:
            page = pages[0]
        else:
            try:
                page = context.new_page()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(0.25)
                continue
        current_url = _normalize_browser_url(getattr(page, "url", ""))
        if current_url in {"", "about:blank", "data:,", "chrome://newtab/", "chrome-error://chromewebdata/"}:
            try:
                page.goto(start_url, wait_until=wait_until)
            except PlaywrightError as exc:
                last_error = exc
                time.sleep(0.25)
                continue
        return context, page
    detail = f": {last_error}" if last_error is not None else ""
    raise RuntimeError(f"external browser did not expose a usable page context{detail}")


def _terminate_external_browser_process(process: subprocess.Popen[Any]) -> None:
    with suppress(Exception):
        if process.poll() is not None:
            return
        process.terminate()
        process.wait(timeout=5)
        return
    with suppress(Exception):
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def _launch_auth_browser(
    *,
    playwright: Any,
    headless: bool,
    environment: Mapping[str, str],
) -> Any:
    return launch_playwright_chromium(
        playwright=playwright,
        headless=headless,
        environment=environment,
    )


def launch_playwright_chromium(
    *,
    playwright: Any,
    headless: bool,
    environment: Mapping[str, str] | None = None,
) -> Any:
    effective_environment = dict(os.environ if environment is None else environment)
    explicit_options = _browser_launch_override(effective_environment)
    if explicit_options is not None:
        return playwright.chromium.launch(headless=headless, **explicit_options)

    try:
        return playwright.chromium.launch(headless=headless)
    except PlaywrightError as exc:
        fallback_options = _system_browser_launch_options()
        if fallback_options is None or "Executable doesn't exist" not in str(exc):
            raise
        return playwright.chromium.launch(headless=headless, **fallback_options)


def launch_playwright_chromium_persistent_context(
    *,
    playwright: Any,
    user_data_dir: str | Path,
    headless: bool,
    environment: Mapping[str, str] | None = None,
    **context_options: Any,
) -> Any:
    effective_environment = dict(os.environ if environment is None else environment)
    explicit_options = _browser_launch_override(effective_environment) or {}
    try:
        return playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=headless,
            **explicit_options,
            **context_options,
        )
    except PlaywrightError as exc:
        fallback_options = _system_browser_launch_options()
        if fallback_options is None or "Executable doesn't exist" not in str(exc):
            raise
        return playwright.chromium.launch_persistent_context(
            str(user_data_dir),
            headless=headless,
            **fallback_options,
            **context_options,
        )


def _browser_launch_override(environment: Mapping[str, str]) -> dict[str, str] | None:
    executable_path = str(environment.get(AUTH_BROWSER_EXECUTABLE_ENV) or "").strip()
    if executable_path:
        return {"executable_path": executable_path}

    browser_channel = str(environment.get(AUTH_BROWSER_CHANNEL_ENV) or "").strip()
    if browser_channel:
        return {"channel": browser_channel}
    return None


def _system_browser_launch_options() -> dict[str, str] | None:
    executable_path = _resolve_system_chromium_executable(os.environ)
    if executable_path is not None:
        return {"executable_path": str(executable_path)}
    if shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser"):
        return {"channel": "chrome"}
    return None


def _resolve_system_chromium_executable(environment: Mapping[str, str]) -> Path | None:
    explicit_path = str(environment.get(AUTH_BROWSER_EXECUTABLE_ENV) or "").strip()
    if explicit_path:
        resolved = Path(explicit_path).expanduser().resolve()
        return resolved if resolved.exists() else None
    return _detect_system_chromium_executable()


def _detect_system_chromium_executable() -> Path | None:
    candidates: list[Path] = []
    if sys.platform == "darwin":
        candidates.extend(
            [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                Path.home() / "Applications/Chromium.app/Contents/MacOS/Chromium",
                Path.home() / "Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            ]
        )
    elif sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA") or "")
        program_files = Path(os.environ.get("PROGRAMFILES") or "")
        program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)") or "")
        candidates.extend(
            [
                local_app_data / "Google/Chrome/Application/chrome.exe",
                local_app_data / "Chromium/Application/chrome.exe",
                local_app_data / "Microsoft/Edge/Application/msedge.exe",
                program_files / "Google/Chrome/Application/chrome.exe",
                program_files / "Microsoft/Edge/Application/msedge.exe",
                program_files_x86 / "Google/Chrome/Application/chrome.exe",
                program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
            ]
        )
    else:
        for binary_name in (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
            "microsoft-edge",
            "microsoft-edge-stable",
        ):
            resolved_binary = shutil.which(binary_name)
            if resolved_binary:
                candidates.append(Path(resolved_binary))
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.exists():
            return resolved
    return None
