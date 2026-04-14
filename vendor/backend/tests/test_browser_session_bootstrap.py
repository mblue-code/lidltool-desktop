from __future__ import annotations

from pathlib import Path

from lidltool.connectors.auth import browser_session_bootstrap as bootstrap_module


class _FakeResponse:
    def __init__(self, *, url: str, html: str) -> None:
        self.url = url
        self._html = html

    def text(self) -> str:
        return self._html


class _FakeRequest:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def get(self, url: str) -> _FakeResponse:
        self.calls.append(url)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class _FakePage:
    def __init__(self) -> None:
        self.visited: list[str] = []
        self.wait_calls = 0

    def goto(self, url: str, wait_until: str = "load") -> None:
        self.visited.append(f"{url}|{wait_until}")

    def wait_for_timeout(self, _timeout_ms: int) -> None:
        self.wait_calls += 1


class _FakeContext:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.request = _FakeRequest(responses)
        self.page = _FakePage()
        self.saved_path: str | None = None
        self.closed = False

    def new_page(self) -> _FakePage:
        return self.page

    def storage_state(self, *, path: str) -> None:
        self.saved_path = path

    def close(self) -> None:
        self.closed = True


class _FakeBrowser:
    def __init__(self, context: _FakeContext) -> None:
        self.context = context
        self.closed = False

    def new_context(self) -> _FakeContext:
        return self.context

    def close(self) -> None:
        self.closed = True


class _FakePlaywrightContextManager:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_session_validation_looks_authenticated_blocks_auth_markers() -> None:
    assert (
        bootstrap_module.session_validation_looks_authenticated(
            url="https://www.amazon.de/ap/signin",
            html="<html></html>",
            blocked_url_patterns=("/ap/signin",),
        )
        is False
    )
    assert (
        bootstrap_module.session_validation_looks_authenticated(
            url="https://www.amazon.de/gp/your-account/order-history",
            html='<form name="signIn"></form>',
            blocked_url_patterns=("/ap/signin",),
            blocked_html_markers=('name="signIn"',),
        )
        is False
    )
    assert (
        bootstrap_module.session_validation_looks_authenticated(
            url="https://www.amazon.de/gp/your-account/order-history",
            html="<html><body>orders</body></html>",
            blocked_url_patterns=("/ap/signin",),
            blocked_html_markers=('name="signIn"',),
        )
        is True
    )


def test_run_headful_browser_session_bootstrap_saves_state_after_validation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    context = _FakeContext(
        responses=[
            _FakeResponse(
                url="https://www.amazon.de/ap/signin",
                html='<html><form name="signIn"></form></html>',
            ),
            _FakeResponse(
                url="https://www.amazon.de/ap/cvf/verify",
                html="<html>mfa</html>",
            ),
            _FakeResponse(
                url="https://www.amazon.de/gp/your-account/order-history",
                html="<html><body>orders</body></html>",
            ),
        ]
    )
    browser = _FakeBrowser(context)

    monkeypatch.setattr(bootstrap_module, "sync_playwright", lambda: _FakePlaywrightContextManager())
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium",
        lambda **_kwargs: browser,
    )

    state_file = tmp_path / "amazon_storage_state.json"
    created_paths: list[Path] = []

    ok = bootstrap_module.run_headful_browser_session_bootstrap(
        state_file,
        ensure_state_parent=lambda path: created_paths.append(path),
        login_url="https://www.amazon.de/ap/signin",
        validation_url="https://www.amazon.de/gp/your-account/order-history",
        instructions="Browser open",
        blocked_url_patterns=("/ap/signin", "/ap/cvf/"),
        blocked_html_markers=('name="signIn"',),
        timeout_seconds=5,
        poll_interval_ms=10,
    )

    assert ok is True
    assert created_paths == [state_file]
    assert context.saved_path == str(state_file)
    assert context.request.calls == [
        "https://www.amazon.de/gp/your-account/order-history",
        "https://www.amazon.de/gp/your-account/order-history",
        "https://www.amazon.de/gp/your-account/order-history",
    ]
    assert context.page.visited == ["https://www.amazon.de/ap/signin|domcontentloaded"]
    assert context.page.wait_calls == 2
    assert context.closed is True
    assert browser.closed is True
