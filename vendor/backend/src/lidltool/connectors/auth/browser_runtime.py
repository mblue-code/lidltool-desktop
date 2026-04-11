from __future__ import annotations

import os
import secrets
import shutil
import sys
from tempfile import TemporaryDirectory
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

AuthBrowserMode = Literal["local_display", "remote_vnc", "headless_capture_only"]

AUTH_BROWSER_METADATA_KEY = "auth_browser"
AUTH_BROWSER_MODE_ENV = "LIDLTOOL_AUTH_BROWSER_MODE"
AUTH_BROWSER_EXECUTABLE_ENV = "LIDLTOOL_PLAYWRIGHT_BROWSER_EXECUTABLE_PATH"
AUTH_BROWSER_CHANNEL_ENV = "LIDLTOOL_PLAYWRIGHT_BROWSER_CHANNEL"


class AuthBrowserPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_url: str
    callback_url_prefixes: tuple[str, ...]
    timeout_seconds: int = Field(default=900, ge=1, le=7200)
    wait_until: Literal["domcontentloaded", "load", "networkidle"] = "domcontentloaded"
    interactive: bool = True


class AuthBrowserStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str
    plan: AuthBrowserPlan


class AuthBrowserResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str
    session_id: str
    mode: AuthBrowserMode
    start_url: str
    final_url: str
    callback_url: str
    started_at: str
    completed_at: str


_REQUEST_ADAPTER: TypeAdapter[AuthBrowserStartRequest] = TypeAdapter(AuthBrowserStartRequest)
_RESULT_ADAPTER: TypeAdapter[AuthBrowserResult] = TypeAdapter(AuthBrowserResult)


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
        callback_url = self._wait_for_callback(
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
        )

    def _wait_for_callback(
        self,
        *,
        request: AuthBrowserStartRequest,
        environment: Mapping[str, str],
    ) -> str:
        callback_prefixes = tuple(request.plan.callback_url_prefixes)
        mode = self._resolve_mode(env=environment, interactive=request.plan.interactive)
        headless = mode == "headless_capture_only"
        if request.plan.interactive and mode == "headless_capture_only":
            raise RuntimeError(
                "interactive browser auth requires a display. Start bootstrap through the web UI "
                "or provide DISPLAY for a local browser session."
            )

        with sync_playwright() as playwright:
            with TemporaryDirectory(prefix="lidltool-auth-browser-") as user_data_dir:
                context = launch_playwright_chromium_persistent_context(
                    playwright=playwright,
                    user_data_dir=user_data_dir,
                    headless=headless,
                    environment=environment,
                )
                captured_url: str | None = None
                captured_error: str | None = None

                def capture(url: str | None) -> None:
                    nonlocal captured_url
                    matched = _match_callback_candidate(
                        str(url or "").strip(),
                        callback_prefixes,
                    )
                    if matched is not None:
                        captured_url = matched

                def attach_page(page: Any) -> None:
                    page.on("framenavigated", lambda frame: capture(frame.url))

                context.on("request", lambda req: capture(req.url))
                context.on("requestfailed", lambda req: capture(req.url))
                context.on("response", lambda res: capture(res.headers.get("location")))
                context.on("page", attach_page)

                page = context.pages[0] if getattr(context, "pages", None) else context.new_page()
                attach_page(page)

                try:
                    page.goto(request.plan.start_url, wait_until=request.plan.wait_until)
                except PlaywrightError as exc:
                    context.close()
                    raise RuntimeError(f"browser auth session failed to open login page: {exc}") from exc

                print("Browser open: complete login in the shared auth session window.", flush=True)
                deadline = datetime.now(tz=UTC).timestamp() + request.plan.timeout_seconds
                while captured_url is None and captured_error is None:
                    captured_url = _discover_callback_candidate(
                        context=context,
                        callback_prefixes=callback_prefixes,
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
                            callback_prefixes=callback_prefixes,
                        )
                        if captured_url is not None:
                            break
                        captured_error = str(exc)
                        break

                context.close()

        if captured_error is not None:
            raise RuntimeError(f"browser auth session failed before callback capture: {captured_error}")
        if captured_url is None:
            raise RuntimeError(
                "browser auth did not complete before timeout; retry bootstrap and finish the login flow."
            )
        return captured_url

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
    callback_prefixes: tuple[str, ...],
) -> str | None:
    for page in list(getattr(context, "pages", ())):
        candidate = _discover_callback_candidate_from_page(
            page=page,
            callback_prefixes=callback_prefixes,
        )
        if candidate is not None:
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
    return _match_callback_candidate(body_text, callback_prefixes)


def _match_callback_candidate(candidate: str, callback_prefixes: tuple[str, ...]) -> str | None:
    raw = candidate.strip()
    if not raw:
        return None

    for prefix in callback_prefixes:
        index = raw.find(prefix)
        if index < 0:
            continue
        matched = raw[index:]
        for delimiter in ('"', "'", " ", "\n", "\r", "\t", "<", ">", ")", "]"):
            delimiter_index = matched.find(delimiter)
            if delimiter_index > 0:
                matched = matched[:delimiter_index]
        return matched.rstrip(".,;")
    return None


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
    executable_path = _detect_system_chromium_executable()
    if executable_path is not None:
        return {"executable_path": str(executable_path)}
    if shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser"):
        return {"channel": "chrome"}
    return None


def _detect_system_chromium_executable() -> Path | None:
    candidates: list[Path] = []
    if sys.platform == "darwin":
        candidates.extend(
            [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                Path.home() / "Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
        )
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.exists():
            return resolved
    return None


def build_auth_browser_metadata(
    *,
    flow_id: str,
    plan: AuthBrowserPlan,
) -> dict[str, Any]:
    payload = AuthBrowserStartRequest(flow_id=flow_id, plan=plan)
    return {AUTH_BROWSER_METADATA_KEY: payload.model_dump(mode="python")}


def parse_auth_browser_start_request(metadata: Mapping[str, Any] | None) -> AuthBrowserStartRequest | None:
    if not isinstance(metadata, Mapping):
        return None
    payload = metadata.get(AUTH_BROWSER_METADATA_KEY)
    if payload is None:
        return None
    return _REQUEST_ADAPTER.validate_python(payload)


def build_auth_browser_runtime_context(result: AuthBrowserResult) -> dict[str, Any]:
    return {AUTH_BROWSER_METADATA_KEY: result.model_dump(mode="python")}


def parse_auth_browser_runtime_context(
    runtime_context: Mapping[str, Any] | None,
) -> AuthBrowserResult | None:
    if not isinstance(runtime_context, Mapping):
        return None
    payload = runtime_context.get(AUTH_BROWSER_METADATA_KEY)
    if payload is None:
        return None
    return _RESULT_ADAPTER.validate_python(payload)
