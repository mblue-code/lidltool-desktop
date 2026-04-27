from __future__ import annotations

import html
import json
import os
import secrets
import sqlite3
import subprocess
import shutil
import sys
from tempfile import TemporaryDirectory
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager, suppress
from tempfile import TemporaryDirectory, mkdtemp
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
AUTH_BROWSER_PREFER_SYSTEM_PROFILE_ENV = "LIDLTOOL_AUTH_BROWSER_PREFER_SYSTEM_PROFILE"


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


@dataclass(frozen=True, slots=True)
class ExternalChromiumLaunch:
    command: tuple[str, ...]
    launcher_may_exit_early: bool


@dataclass(frozen=True, slots=True)
class SystemChromiumProfileTarget:
    executable_path: Path
    app_bundle_path: Path | None
    browser_name: str
    user_data_dir: Path
    profile_name: str
    history_db_path: Path


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
        if _should_use_system_profile_browser_handoff(
            plan=request.plan,
            mode=mode,
            environment=environment,
        ):
            return _capture_system_profile_browser_result(
                request=request,
                environment=environment,
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


def _capture_system_profile_browser_result(
    *,
    request: AuthBrowserStartRequest,
    environment: Mapping[str, str],
) -> tuple[str, dict[str, Any] | None]:
    target = _resolve_system_chromium_profile_target(environment)
    if target is None:
        raise RuntimeError("system-profile browser handoff requires a supported installed Chromium browser")

    not_before = _chromium_history_timestamp(datetime.now(tz=UTC))
    if request.plan.auto_launch_browser:
        _launch_system_profile_browser(
            target=target,
            start_url=request.plan.start_url,
        )
    callback_url = _wait_for_callback_in_system_profile_browser(
        target=target,
        auto_launch_browser=request.plan.auto_launch_browser,
        callback_prefixes=tuple(request.plan.callback_url_prefixes),
        expected_callback_state=request.plan.expected_callback_state,
        timeout_seconds=request.plan.timeout_seconds,
        not_before=not_before,
    )
    return callback_url, None


def _wait_for_callback_in_system_profile_browser(
    *,
    target: SystemChromiumProfileTarget,
    auto_launch_browser: bool,
    callback_prefixes: tuple[str, ...],
    expected_callback_state: str | None,
    timeout_seconds: int,
    not_before: int,
) -> str:
    deadline = time.monotonic() + max(timeout_seconds, 5)
    if auto_launch_browser:
        print("Browser open: complete login in your browser window.", flush=True)
    else:
        print(
            "Browser handoff ready: open the connector sign-in link in your normal browser, then finish login there.",
            flush=True,
        )
    while time.monotonic() < deadline:
        candidate = _read_callback_from_system_browser_tabs(
            target=target,
            callback_prefixes=callback_prefixes,
            expected_callback_state=expected_callback_state,
        )
        if candidate is None:
            candidate = _read_callback_from_chromium_history(
                target=target,
                callback_prefixes=callback_prefixes,
                expected_callback_state=expected_callback_state,
                not_before=not_before,
            )
        if candidate is not None:
            return candidate
        time.sleep(0.5)
    raise RuntimeError(
        "browser auth did not complete before timeout; reopen the sign-in link and finish the login flow."
    )


def _read_callback_from_system_browser_tabs(
    *,
    target: SystemChromiumProfileTarget,
    callback_prefixes: tuple[str, ...],
    expected_callback_state: str | None,
) -> str | None:
    if sys.platform != "darwin":
        return None
    result = subprocess.run(
        [
            "osascript",
            "-e",
            f'tell application "{target.browser_name}"',
            "-e",
            "set foundUrls to {}",
            "-e",
            "repeat with w in windows",
            "-e",
            "repeat with t in tabs of w",
            "-e",
            "copy (URL of t) to end of foundUrls",
            "-e",
            "end repeat",
            "-e",
            "end repeat",
            "-e",
            "set AppleScript's text item delimiters to linefeed",
            "-e",
            "return foundUrls as text",
            "-e",
            "end tell",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    for raw_url in result.stdout.splitlines():
        matched = _match_callback_candidate(str(raw_url or "").strip(), callback_prefixes)
        if matched is None:
            continue
        if expected_callback_state is None:
            return matched
        parsed = urllib.parse.urlparse(matched)
        actual_state = urllib.parse.parse_qs(parsed.query).get("state", [None])[0]
        if actual_state == expected_callback_state:
            return matched
    return None


def _read_callback_from_chromium_history(
    *,
    target: SystemChromiumProfileTarget,
    callback_prefixes: tuple[str, ...],
    expected_callback_state: str | None,
    not_before: int,
) -> str | None:
    if not target.history_db_path.exists():
        return None
    with TemporaryDirectory(prefix="lidltool-auth-history-") as tmp_dir:
        temp_db = Path(tmp_dir) / "History"
        try:
            shutil.copy2(target.history_db_path, temp_db)
            connection = sqlite3.connect(str(temp_db))
        except (OSError, sqlite3.Error):
            return None
        try:
            query = (
                "select url, last_visit_time from urls "
                "where last_visit_time >= ? and ("
                + " or ".join("url like ?" for _ in callback_prefixes)
                + ") order by last_visit_time desc limit 25"
            )
            params: list[Any] = [not_before, *(f"{prefix}%" for prefix in callback_prefixes)]
            rows = list(connection.execute(query, params))
        except sqlite3.Error:
            return None
        finally:
            connection.close()
    for raw_url, _last_visit_time in rows:
        matched = _match_callback_candidate(str(raw_url or "").strip(), callback_prefixes)
        if matched is None:
            continue
        if expected_callback_state is None:
            return matched
        parsed = urllib.parse.urlparse(matched)
        actual_state = urllib.parse.parse_qs(parsed.query).get("state", [None])[0]
        if actual_state == expected_callback_state:
            return matched
    return None


def _launch_system_profile_browser(
    *,
    target: SystemChromiumProfileTarget,
    start_url: str,
) -> None:
    if sys.platform == "darwin" and target.app_bundle_path is not None:
        command = ("open", "-a", str(target.app_bundle_path), start_url)
    else:
        command = (str(target.executable_path), start_url)
    result = subprocess.run(
        list(command),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        env=_external_browser_process_environment(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"failed to open {target.browser_name} for browser auth (exit code {result.returncode})")


def _chromium_history_timestamp(value: datetime) -> int:
    utc_value = value.astimezone(UTC)
    return int((utc_value.timestamp() + 11_644_473_600) * 1_000_000)


def _resolve_system_chromium_profile_target(
    environment: Mapping[str, str],
) -> SystemChromiumProfileTarget | None:
    executable_path = _resolve_system_chromium_executable(environment)
    if executable_path is None:
        return None
    browser_name, user_data_dir = _chromium_user_data_dir_for_executable(executable_path)
    if user_data_dir is None or not user_data_dir.exists():
        return None
    profile_name = _chromium_last_used_profile_name(user_data_dir) or "Default"
    history_db_path = user_data_dir / profile_name / "History"
    if not history_db_path.exists():
        fallback_history_path = user_data_dir / "Default" / "History"
        if not fallback_history_path.exists():
            return None
        profile_name = "Default"
        history_db_path = fallback_history_path
    return SystemChromiumProfileTarget(
        executable_path=executable_path,
        app_bundle_path=_macos_app_bundle_from_executable(executable_path),
        browser_name=browser_name,
        user_data_dir=user_data_dir,
        profile_name=profile_name,
        history_db_path=history_db_path,
    )


def _chromium_user_data_dir_for_executable(executable_path: Path) -> tuple[str, Path | None]:
    executable_marker = str(executable_path).lower()
    home = _real_user_home_dir()
    if not home:
        return "Chromium", None
    home_path = Path(home).expanduser().resolve()
    if sys.platform == "darwin":
        if "microsoft edge.app" in executable_marker:
            return "Microsoft Edge", (home_path / "Library" / "Application Support" / "Microsoft Edge").resolve()
        if "chromium.app" in executable_marker:
            return "Chromium", (home_path / "Library" / "Application Support" / "Chromium").resolve()
        return "Google Chrome", (home_path / "Library" / "Application Support" / "Google" / "Chrome").resolve()
    if sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA") or "")
        if "msedge.exe" in executable_marker:
            return "Microsoft Edge", (local_app_data / "Microsoft" / "Edge" / "User Data").resolve()
        if "chromium" in executable_marker:
            return "Chromium", (local_app_data / "Chromium" / "User Data").resolve()
        return "Google Chrome", (local_app_data / "Google" / "Chrome" / "User Data").resolve()
    if "microsoft-edge" in executable_marker or "msedge" in executable_marker:
        return "Microsoft Edge", (home_path / ".config" / "microsoft-edge").resolve()
    if "chromium" in executable_marker:
        return "Chromium", (home_path / ".config" / "chromium").resolve()
    return "Google Chrome", (home_path / ".config" / "google-chrome").resolve()


def _chromium_last_used_profile_name(user_data_dir: Path) -> str | None:
    local_state_path = user_data_dir / "Local State"
    try:
        payload = json.loads(local_state_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    profile_payload = payload.get("profile")
    if not isinstance(profile_payload, dict):
        return None
    candidate = str(profile_payload.get("last_used") or "").strip()
    return candidate or None


def _capture_external_chromium_result(
    *,
    request: AuthBrowserStartRequest,
    environment: Mapping[str, str],
) -> tuple[str, dict[str, Any] | None]:
    executable_path = _resolve_system_chromium_executable(environment)
    if executable_path is None:
        raise RuntimeError("external browser handoff requires an installed Chromium-based browser on this host")

    with _temporary_local_temp_environment():
        user_data_dir = Path(
            mkdtemp(
                prefix="lidltool-auth-browser-",
                dir=_external_browser_temp_root(),
            )
        )
        try:
            _seed_external_chromium_profile(user_data_dir)
            launch = _build_external_chromium_launch(
                executable_path=executable_path,
                user_data_dir=user_data_dir,
                start_url=request.plan.start_url,
            )
            browser_log_path = user_data_dir / "external-browser.log"
            browser_log = browser_log_path.open("ab")
            process = subprocess.Popen(
                list(launch.command),
                stdout=browser_log,
                stderr=subprocess.STDOUT,
                env=_external_browser_process_environment(),
            )
            try:
                port = _wait_for_cdp_endpoint(
                    user_data_dir=user_data_dir,
                    process=process,
                    launcher_may_exit_early=launch.launcher_may_exit_early,
                    timeout_seconds=min(max(request.plan.timeout_seconds, 15), 30),
                    log_path=browser_log_path,
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
                with suppress(Exception):
                    browser_log.close()
                _terminate_external_browser_process(
                    process,
                    user_data_dir=user_data_dir,
                    launcher_may_exit_early=launch.launcher_may_exit_early,
                )
        finally:
            _cleanup_browser_profile_dir(user_data_dir)


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


def _should_use_system_profile_browser_handoff(
    *,
    plan: AuthBrowserPlan,
    mode: AuthBrowserMode,
    environment: Mapping[str, str],
) -> bool:
    if sys.platform != "darwin":
        return False
    if not plan.interactive or mode == "headless_capture_only":
        return False
    if plan.capture_storage_state:
        return False
    if plan.expected_callback_state is None:
        return False
    if not _bool_env(
        environment,
        AUTH_BROWSER_PREFER_SYSTEM_PROFILE_ENV,
        default=True,
    ):
        return False
    return _resolve_system_chromium_profile_target(environment) is not None


def _bool_env(environment: Mapping[str, str], key: str, *, default: bool) -> bool:
    raw_value = str(environment.get(key) or "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    return default


def _build_external_chromium_launch(
    *,
    executable_path: Path,
    user_data_dir: Path,
    start_url: str,
) -> ExternalChromiumLaunch:
    browser_args = (
        "--remote-debugging-port=0",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={user_data_dir}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        start_url,
    )
    app_bundle_path = _macos_app_bundle_from_executable(executable_path)
    if sys.platform == "darwin" and app_bundle_path is not None:
        return ExternalChromiumLaunch(
            command=("open", "-n", "-a", str(app_bundle_path), "--args", *browser_args),
            launcher_may_exit_early=True,
        )
    return ExternalChromiumLaunch(
        command=(str(executable_path), *browser_args),
        launcher_may_exit_early=False,
    )


def _wait_for_cdp_endpoint(
    *,
    user_data_dir: Path,
    process: subprocess.Popen[Any],
    launcher_may_exit_early: bool,
    timeout_seconds: int,
    log_path: Path | None = None,
) -> int:
    deadline = time.monotonic() + max(timeout_seconds, 5)
    last_error: Exception | None = None
    observed_port: int | None = None
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None and (return_code != 0 or not launcher_may_exit_early):
            raise RuntimeError(
                f"external browser exited before the login page became available (exit code {return_code})"
            )
        observed_port = _read_devtools_active_port(user_data_dir)
        if observed_port is not None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{observed_port}/json/version", timeout=1) as response:
                    if response.status == 200:
                        return observed_port
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        time.sleep(0.25)
    detail_parts: list[str] = []
    if observed_port is not None:
        detail_parts.append(f"detected port {observed_port} but /json/version stayed unreachable")
    if last_error is not None:
        detail_parts.append(str(last_error))
    log_tail = _read_browser_launch_log_tail(log_path)
    if log_tail:
        detail_parts.append(f"browser log tail: {log_tail}")
    detail = f": {'; '.join(detail_parts)}" if detail_parts else ""
    raise RuntimeError(f"external browser debugging endpoint did not become ready{detail}")


def _read_devtools_active_port(user_data_dir: Path) -> int | None:
    candidate = user_data_dir / "DevToolsActivePort"
    try:
        lines = candidate.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines:
        return None
    try:
        port = int(lines[0].strip())
    except ValueError:
        return None
    return port if port > 0 else None


def _read_browser_launch_log_tail(log_path: Path | None) -> str | None:
    if log_path is None:
        return None
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return None
    return " | ".join(lines[-4:])


def _macos_app_bundle_from_executable(executable_path: Path) -> Path | None:
    if sys.platform != "darwin":
        return None
    for parent in executable_path.parents:
        if parent.suffix == ".app":
            return parent
    return None


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


def _terminate_external_browser_process(
    process: subprocess.Popen[Any],
    *,
    user_data_dir: Path,
    launcher_may_exit_early: bool,
) -> None:
    if launcher_may_exit_early:
        _terminate_browser_processes_for_profile(user_data_dir)
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


def _terminate_browser_processes_for_profile(user_data_dir: Path) -> None:
    marker = str(user_data_dir)
    if not marker:
        return
    if shutil.which("pkill") is None:
        return
    with suppress(Exception):
        subprocess.run(
            ["pkill", "-f", marker],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if not _profile_processes_still_running(marker):
            return
        time.sleep(0.1)


def _profile_processes_still_running(marker: str) -> bool:
    if not marker or shutil.which("pgrep") is None:
        return False
    result = subprocess.run(
        ["pgrep", "-f", marker],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _cleanup_browser_profile_dir(user_data_dir: Path) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            shutil.rmtree(user_data_dir)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.1)
    with suppress(Exception):
        shutil.rmtree(user_data_dir, ignore_errors=True)


def _seed_external_chromium_profile(user_data_dir: Path) -> None:
    default_dir = user_data_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    preferences_path = default_dir / "Preferences"
    payload: dict[str, Any]
    if preferences_path.exists():
        try:
            payload = json.loads(preferences_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
    else:
        payload = {}
    payload["allow_javascript_apple_events"] = True
    preferences_path.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _external_browser_temp_root() -> str | None:
    if sys.platform != "darwin":
        return None
    for candidate in (Path("/private/tmp"), Path("/tmp")):
        if candidate.exists() and candidate.is_dir():
            return str(candidate)
    return None


def _external_browser_process_environment() -> dict[str, str]:
    env = dict(os.environ)
    real_home = _real_user_home_dir()
    if real_home:
        env["HOME"] = real_home
        if sys.platform == "win32":
            env["USERPROFILE"] = real_home
    temp_root = _external_browser_temp_root()
    if temp_root:
        env["TMPDIR"] = temp_root
        env["TMP"] = temp_root
        env["TEMP"] = temp_root
    return env


def _real_user_home_dir() -> str | None:
    if sys.platform == "win32":
        home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
        return str(home).strip() or None
    with suppress(Exception):
        import pwd

        resolved = pwd.getpwuid(os.getuid()).pw_dir
        if resolved:
            return str(resolved).strip() or None
    home = os.environ.get("HOME")
    return str(home).strip() or None


@contextmanager
def _temporary_local_temp_environment() -> Any:
    temp_root = _external_browser_temp_root()
    if not temp_root:
        yield
        return
    original: dict[str, str | None] = {key: os.environ.get(key) for key in ("TMPDIR", "TMP", "TEMP")}
    try:
        for key in original:
            os.environ[key] = temp_root
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


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
