from __future__ import annotations

from lidltool.connectors.auth import browser_runtime
from lidltool.connectors.sdk.runtime import AuthBrowserPlan, AuthBrowserStartRequest


class _FakePage:
    def __init__(self) -> None:
        self.timeout_calls: list[int] = []
        self.goto_calls: list[tuple[str, str]] = []
        self.handlers: dict[str, object] = {}
        self.main_frame = object()

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def goto(self, url: str, wait_until: str = "load") -> None:
        self.goto_calls.append((url, wait_until))

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.timeout_calls.append(timeout_ms)

    def wait_for_event(self, event: str, timeout: int) -> None:
        raise AssertionError(f"unexpected wait_for_event call: {event} timeout={timeout}")


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self.pages = [page]
        self.handlers: dict[str, object] = {}
        self.closed = False

    def on(self, event: str, handler: object) -> None:
        self.handlers[event] = handler

    def storage_state(self) -> dict[str, object]:
        return {"cookies": [], "origins": []}

    def close(self) -> None:
        self.closed = True


class _FakePlaywrightContextManager:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_auth_browser_run_uses_non_failing_poll_loop(
    monkeypatch,
) -> None:
    page = _FakePage()
    context = _FakeContext(page)
    request = AuthBrowserStartRequest(
        flow_id="flow-1",
        plan=AuthBrowserPlan(
            start_url="https://example.test/login",
            callback_url_prefixes=("https://example.test/callback",),
            interactive=True,
            capture_storage_state=True,
            timeout_seconds=5,
        ),
    )

    callback_candidates = iter(
        [
            None,
            None,
            "https://example.test/callback?code=done",
        ]
    )

    monkeypatch.setattr(browser_runtime, "sync_playwright", lambda: _FakePlaywrightContextManager())
    monkeypatch.setattr(
        browser_runtime,
        "launch_playwright_chromium_persistent_context",
        lambda **_kwargs: context,
    )
    monkeypatch.setattr(
        browser_runtime,
        "_discover_callback_candidate",
        lambda **_kwargs: next(callback_candidates),
    )

    result = browser_runtime.AuthBrowserRuntimeService().run(
        request,
        environment={"DISPLAY": ":99"},
    )

    assert result.callback_url == "https://example.test/callback?code=done"
    assert page.goto_calls == [("https://example.test/login", "domcontentloaded")]
    assert page.timeout_calls == [500, 500]
    assert context.closed is True
