from __future__ import annotations

from pathlib import Path

from lidltool.amazon import bootstrap_playwright as amazon_bootstrap_module
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
        self.url = ""
        self.html = "<html></html>"
        self.available_selectors: set[str] = set()
        self.focused_selector: str | None = None

    def goto(self, url: str, wait_until: str = "load") -> None:
        self.visited.append(f"{url}|{wait_until}")
        self.url = url

    def wait_for_timeout(self, _timeout_ms: int) -> None:
        self.wait_calls += 1

    def content(self) -> str:
        return self.html

    def locator(self, selector: str) -> "_FakeLocator":
        return _FakeLocator(page=self, selector=selector)


class _FakeLocator:
    def __init__(self, *, page: _FakePage, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self) -> "_FakeLocator":
        return self

    def focus(self) -> None:
        if self._selector not in self._page.available_selectors:
            raise RuntimeError(f"selector not found: {self._selector}")
        self._page.focused_selector = self._selector


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


class _FakePersistentContext(_FakeContext):
    pass


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


def test_run_headful_browser_session_bootstrap_accepts_authenticated_live_page(
    monkeypatch,
    tmp_path: Path,
) -> None:
    context = _FakeContext(
        responses=[
            _FakeResponse(
                url="https://www.amazon.de/ap/intent",
                html="<html>still gated in request probe</html>",
            )
        ]
    )
    context.page.url = "https://www.amazon.de/gp/your-account/order-history"
    context.page.html = "<html><body>orders</body></html>"
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
        login_url="https://www.amazon.de/gp/your-account/order-history",
        validation_url="https://www.amazon.de/gp/your-account/order-history",
        instructions="Browser open",
        blocked_url_patterns=("/ap/signin", "/ap/cvf/", "/ap/intent"),
        blocked_html_markers=('name="signIn"',),
        timeout_seconds=5,
        poll_interval_ms=10,
    )

    assert ok is True
    assert created_paths == [state_file]
    assert context.saved_path == str(state_file)
    assert context.request.calls == []


def test_run_headful_browser_session_bootstrap_focuses_first_login_field(
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
                url="https://www.amazon.de/gp/your-account/order-history",
                html="<html><body>orders</body></html>",
            ),
        ]
    )
    context.page.available_selectors = {"#ap_email"}
    browser = _FakeBrowser(context)

    monkeypatch.setattr(bootstrap_module, "sync_playwright", lambda: _FakePlaywrightContextManager())
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium",
        lambda **_kwargs: browser,
    )

    state_file = tmp_path / "amazon_storage_state.json"

    ok = bootstrap_module.run_headful_browser_session_bootstrap(
        state_file,
        ensure_state_parent=lambda _path: None,
        login_url="https://www.amazon.de/ap/signin",
        validation_url="https://www.amazon.de/gp/your-account/order-history",
        instructions="Browser open",
        blocked_url_patterns=("/ap/signin", "/ap/cvf/"),
        blocked_html_markers=('name="signIn"',),
        timeout_seconds=5,
        poll_interval_ms=10,
    )

    assert ok is True
    assert context.page.focused_selector == "#ap_email"


def test_run_headful_browser_session_bootstrap_reports_waiting_auth_state(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    context = _FakeContext(
        responses=[
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

    ok = bootstrap_module.run_headful_browser_session_bootstrap(
        state_file,
        ensure_state_parent=lambda _path: None,
        login_url="https://www.amazon.de/gp/your-account/order-history",
        validation_url="https://www.amazon.de/gp/your-account/order-history",
        instructions="Browser open",
        blocked_url_patterns=("/ap/signin", "/ap/cvf/"),
        blocked_html_markers=('name="signIn"',),
        timeout_seconds=5,
        poll_interval_ms=10,
        probe_validator=lambda url, html: bootstrap_module.SessionValidationProbeResult(
            authenticated="orders" in html,
            url=url,
            html=html,
            state="authenticated" if "orders" in html else "mfa_required",
            detail=None if "orders" in html else "Amazon is requesting MFA or an extra verification code.",
        ),
    )

    captured = capsys.readouterr()
    assert ok is True
    assert "Waiting for auth step: mfa_required" in captured.out
    assert "Amazon is requesting MFA or an extra verification code." in captured.out


def test_run_headful_browser_session_bootstrap_uses_persistent_profile_dir_when_provided(
    monkeypatch,
    tmp_path: Path,
) -> None:
    context = _FakePersistentContext(
        responses=[
            _FakeResponse(
                url="https://www.amazon.de/gp/your-account/order-history",
                html="<html><body>orders</body></html>",
            ),
        ]
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(bootstrap_module, "sync_playwright", lambda: _FakePlaywrightContextManager())

    def _fake_launch_persistent_context(*, playwright, user_data_dir, headless):
        del playwright, headless
        captured["user_data_dir"] = Path(user_data_dir)
        return context

    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium_persistent_context",
        _fake_launch_persistent_context,
    )

    state_file = tmp_path / "amazon_storage_state.json"
    profile_dir = tmp_path / "amazon-profile"

    ok = bootstrap_module.run_headful_browser_session_bootstrap(
        state_file,
        ensure_state_parent=lambda _path: None,
        login_url="https://www.amazon.de/gp/your-account/order-history",
        validation_url="https://www.amazon.de/gp/your-account/order-history",
        instructions="Browser open",
        blocked_url_patterns=("/ap/signin",),
        blocked_html_markers=('name="signIn"',),
        timeout_seconds=1,
        poll_interval_ms=10,
        user_data_dir=profile_dir,
    )

    assert ok is True
    assert captured["user_data_dir"] == profile_dir
    assert context.saved_path == str(state_file)


def test_amazon_bootstrap_uses_order_history_entrypoint(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def _fake_run_headful_browser_session_bootstrap(
        state_file: Path,
        *,
        ensure_state_parent,
        login_url: str,
        validation_url: str,
        instructions: str,
        blocked_url_patterns,
        blocked_html_markers=(),
        timeout_seconds: int = 300,
        poll_interval_ms: int = 500,
        probe_validator=None,
        debug_html_dir: Path | None = None,
        user_data_dir: Path | None = None,
    ) -> bool:
        del ensure_state_parent, instructions, blocked_url_patterns, blocked_html_markers
        del timeout_seconds, poll_interval_ms, probe_validator, debug_html_dir
        captured["state_file"] = state_file
        captured["login_url"] = login_url
        captured["validation_url"] = validation_url
        captured["user_data_dir"] = user_data_dir
        return True

    monkeypatch.setattr(
        amazon_bootstrap_module,
        "run_headful_browser_session_bootstrap",
        _fake_run_headful_browser_session_bootstrap,
    )

    state_file = tmp_path / "amazon_storage_state.json"
    profile_dir = tmp_path / "amazon-profile"
    ok = amazon_bootstrap_module.run_amazon_headful_bootstrap(
        state_file,
        source_id="amazon_de",
        profile_dir=profile_dir,
    )

    assert ok is True
    assert captured["state_file"] == state_file
    assert captured["login_url"] == "https://www.amazon.de/gp/your-account/order-history"
    assert captured["validation_url"] == "https://www.amazon.de/gp/your-account/order-history"
    assert captured["user_data_dir"] == profile_dir


def test_amazon_bootstrap_short_circuits_when_saved_profile_is_already_valid(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_file = tmp_path / "amazon_storage_state.json"
    profile_dir = tmp_path / "amazon-profile"
    profile_dir.mkdir()
    (profile_dir / "Cookies").write_text("cookie-db", encoding="utf-8")
    validate_calls: list[tuple[Path, Path, str, str | None, bool]] = []

    class _FakeClient:
        def __init__(self, *, state_file: Path, profile_dir: Path, source_id: str, domain: str | None, headless: bool) -> None:
            validate_calls.append((state_file, profile_dir, source_id, domain, headless))

        def validate_session(self) -> None:
            return None

    monkeypatch.setattr(amazon_bootstrap_module, "AmazonPlaywrightClient", _FakeClient)
    monkeypatch.setattr(
        amazon_bootstrap_module,
        "run_headful_browser_session_bootstrap",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("headful bootstrap should not run")),
    )

    ok = amazon_bootstrap_module.run_amazon_headful_bootstrap(
        state_file,
        source_id="amazon_de",
        profile_dir=profile_dir,
    )

    assert ok is True
    assert validate_calls == [(state_file, profile_dir, "amazon_de", "amazon.de", True)]
