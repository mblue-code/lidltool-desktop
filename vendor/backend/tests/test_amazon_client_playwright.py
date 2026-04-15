from __future__ import annotations

from types import SimpleNamespace

from lidltool.amazon.client_playwright import AmazonPlaywrightClient, AmazonReauthRequiredError


class _FakeResponse:
    def __init__(self, *, ok: bool, text: str = "", url: str = "") -> None:
        self.ok = ok
        self._text = text
        self.url = url

    def text(self) -> str:
        return self._text


class _FakeRequest:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def get(self, _: str) -> _FakeResponse:
        return self._response


class _FakePage:
    def __init__(
        self,
        *,
        url: str,
        html: str,
        timed_states: list[tuple[str, str]] | None = None,
    ) -> None:
        self.url = url
        self._html = html
        self._timed_states = list(timed_states or [])
        self.closed = False

    def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        del wait_until
        self.url = url

    def wait_for_timeout(self, _: int) -> None:
        if self._timed_states:
            self.url, self._html = self._timed_states.pop(0)
        return None

    def content(self) -> str:
        return self._html

    def close(self) -> None:
        self.closed = True


class _FakeContext:
    def __init__(self, *, response: _FakeResponse, page: _FakePage) -> None:
        self.request = _FakeRequest(response)
        self._page = page
        self.storage_state_paths: list[str] = []

    def new_page(self) -> _FakePage:
        return self._page

    def storage_state(self, *, path: str) -> None:
        self.storage_state_paths.append(path)


class _FakeListPage:
    def __init__(self, pages: list[tuple[str, str]]) -> None:
        self._pages = pages
        self._index = -1
        self.url = ""

    def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        del wait_until
        self._index += 1
        self.url = self._pages[self._index][0]

    def wait_for_timeout(self, _: int) -> None:
        return None

    def content(self) -> str:
        return self._pages[self._index][1]


class _FakeListContext:
    def __init__(self, page: _FakeListPage, *, restored_pages: list[_FakePage] | None = None) -> None:
        self._page = page
        self.pages = list(restored_pages or [])
        self.storage_state_paths: list[str] = []
        self.new_page_calls = 0

    def new_page(self) -> _FakeListPage:
        self.new_page_calls += 1
        return self._page

    def storage_state(self, *, path: str) -> None:
        self.storage_state_paths.append(path)

    def close(self) -> None:
        return None


class _FakeListBrowser:
    def __init__(self, context: _FakeListContext) -> None:
        self._context = context

    def new_context(self, *, storage_state: str) -> _FakeListContext:
        del storage_state
        return self._context

    def close(self) -> None:
        return None


class _FakePlaywrightManager:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None


def test_detail_fetch_falls_back_to_page_navigation_and_clears_list_warnings(tmp_path) -> None:
    html = """
    <html><body>
      <div>Meine Bestellungen</div>
      <div data-component="default">
        <span>Bestellung aufgegeben</span>
        <span>14. April 2025</span>
      </div>
      <div class="a-box-group" data-component="shipments">
        <div class="a-fixed-left-grid-inner" data-component="purchasedItems">
          <a class="a-link-normal" href="/dp/B00TEST111">USB Kabel</a>
          <div data-component="unitPrice">
            <span class="a-price a-text-price"><span class="a-offscreen">29,98€</span></span>
            <span class="a-price a-text-price"><span class="a-offscreen">29,98€</span></span>
          </div>
        </div>
      </div>
      <div class="a-spacing-mini a-spacing-top-mini" data-component="chargeSummary">
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Gesamtsumme:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base a-text-bold">29,98 €</span></div>
        </div>
      </div>
    </body></html>
    """
    client = AmazonPlaywrightClient(
        state_file=tmp_path / "amazon_storage_state.json",
        source_id="amazon_de",
        headless=True,
    )
    context = _FakeContext(
        response=_FakeResponse(ok=False, url="https://www.amazon.de/your-orders/order-details?orderID=111-1111111-1111111"),
        page=_FakePage(
            url="https://www.amazon.de/your-orders/order-details?orderID=111-1111111-1111111",
            html=html,
        ),
    )
    order = {
        "orderId": "111-1111111-1111111",
        "orderDate": "",
        "totalAmount": 0,
        "currency": "EUR",
        "items": [{"title": "Amazon item B00TEST111", "asin": "B00TEST111", "quantity": 1, "price": 0}],
        "orderStatus": "Zugestellt",
        "detailsUrl": "https://www.amazon.de/your-orders/order-details?orderID=111-1111111-1111111",
        "promotions": [],
        "totalSavings": 0,
        "parseStatus": "partial",
        "parseWarnings": ["missing_order_date", "missing_total_amount"],
        "unsupportedReason": None,
    }

    client._enrich_order_from_details(context, order)  # noqa: SLF001

    assert order["orderDate"] == "14. April 2025"
    assert order["totalAmount"] == 29.98
    assert order["parseWarnings"] == []
    assert order["parseStatus"] == "complete"
    assert order["items"][0]["title"] == "USB Kabel"
    assert order["items"][0]["price"] == 29.98
    assert context._page.closed is True


def test_sparse_single_item_orders_keep_list_total_as_item_price(tmp_path) -> None:
    client = AmazonPlaywrightClient(
        state_file=tmp_path / "amazon_storage_state.json",
        source_id="amazon_de",
        headless=True,
    )
    order = {
        "orderId": "D01-2396164-3487030",
        "orderDate": "25. April 2025",
        "totalAmount": 4.46,
        "currency": "EUR",
        "items": [{"title": "Bound: The Gift of Desire (English Edition)", "asin": "B0DFTZTJ3Z", "quantity": 1, "price": 0}],
        "orderStatus": "",
        "detailsUrl": "https://www.amazon.de/gp/css/order-details?orderID=D01-2396164-3487030",
        "promotions": [],
        "totalSavings": 0,
        "shipping": 0,
        "gift_wrap": 0,
        "parseStatus": "partial",
        "parseWarnings": [],
        "unsupportedReason": None,
    }
    detail = SimpleNamespace(
        data={
            "items": [],
            "orderDate": "25. April 2025",
            "promotions": [],
            "shipping": 0,
            "gift_wrap": 0,
            "totalAmount": None,
            "subtotals": [],
        },
        parse_warnings=[],
        parse_status="partial",
        unsupported_reason=None,
    )

    client._merge_detail_parse_result(order=order, detail=detail)  # noqa: SLF001

    assert order["items"][0]["price"] == 4.46


def test_fetch_orders_scans_until_amazon_has_no_next_page_when_page_cap_is_unset(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "amazon_storage_state.json"
    state_file.write_text("{}", encoding="utf-8")
    list_page = _FakeListPage(
        pages=[
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=0",
                "page-0",
            ),
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=10",
                "page-1",
            ),
        ]
    )
    browser = _FakeListBrowser(_FakeListContext(list_page))
    parsed_pages = {
        "page-0": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=True,
        ),
        "page-1": SimpleNamespace(
            orders=[{"orderId": "222-2222222-2222222", "detailsUrl": "https://www.amazon.de/order/222"}],
            has_next_page=False,
        ),
    }

    monkeypatch.setattr("lidltool.amazon.client_playwright.sync_playwright", lambda: _FakePlaywrightManager())
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium",
        lambda playwright, headless: browser,
    )
    monkeypatch.setattr(
        "lidltool.amazon.client_playwright.parse_order_list_html",
        lambda html, profile, page_url: parsed_pages[html],
    )

    client = AmazonPlaywrightClient(
        state_file=state_file,
        source_id="amazon_de",
        headless=True,
    )
    monkeypatch.setattr(client, "_ensure_logged_in", lambda url, html: None)
    monkeypatch.setattr(client, "_enrich_order_from_details", lambda context, order: None)

    orders = client.fetch_orders(years=1, max_pages_per_year=None)

    assert [order["orderId"] for order in orders] == [
        "111-1111111-1111111",
        "222-2222222-2222222",
    ]
    assert list_page._index == 1
    assert orders[0]["pageYear"] == 2026
    assert orders[0]["dateSource"] == "page_year"


def test_detail_fetch_retries_via_page_when_request_auth_check_fails(tmp_path) -> None:
    html = """
    <html><body>
      <div>Meine Bestellungen</div>
      <div data-component="default">
        <span>Bestellung aufgegeben</span>
        <span>14. April 2025</span>
      </div>
      <div class="a-box-group" data-component="shipments">
        <div class="a-fixed-left-grid-inner" data-component="purchasedItems">
          <a class="a-link-normal" href="/dp/B00TEST111">USB Kabel</a>
          <div data-component="unitPrice">
            <span class="a-price a-text-price"><span class="a-offscreen">29,98€</span></span>
            <span class="a-price a-text-price"><span class="a-offscreen">29,98€</span></span>
          </div>
        </div>
      </div>
      <div class="a-spacing-mini a-spacing-top-mini" data-component="chargeSummary">
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Gesamtsumme:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base a-text-bold">29,98 €</span></div>
        </div>
      </div>
    </body></html>
    """
    client = AmazonPlaywrightClient(
        state_file=tmp_path / "amazon_storage_state.json",
        source_id="amazon_de",
        headless=True,
    )
    context = _FakeContext(
        response=_FakeResponse(
            ok=True,
            url="https://www.amazon.de/ap/signin",
            text="<html><body>Anmelden</body></html>",
        ),
        page=_FakePage(
            url="https://www.amazon.de/your-orders/order-details?orderID=111-1111111-1111111",
            html=html,
        ),
    )
    order = {
        "orderId": "111-1111111-1111111",
        "orderDate": "",
        "totalAmount": 0,
        "currency": "EUR",
        "items": [{"title": "Amazon item B00TEST111", "asin": "B00TEST111", "quantity": 1, "price": 0}],
        "orderStatus": "Zugestellt",
        "detailsUrl": "https://www.amazon.de/your-orders/order-details?orderID=111-1111111-1111111",
        "promotions": [],
        "totalSavings": 0,
        "parseStatus": "partial",
        "parseWarnings": ["missing_order_date", "missing_total_amount"],
        "unsupportedReason": None,
    }

    client._enrich_order_from_details(context, order)  # noqa: SLF001

    assert order["orderDate"] == "14. April 2025"
    assert order["totalAmount"] == 29.98
    assert order["parseWarnings"] == []
    assert order["parseStatus"] == "complete"
    assert context._page.closed is True


def test_fetch_orders_retries_order_list_after_transient_auth_block(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "amazon_storage_state.json"
    state_file.write_text("{}", encoding="utf-8")
    list_page = _FakeListPage(
        pages=[
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=0",
                "page-0",
            ),
            (
                "https://www.amazon.de/ap/signin",
                "signin",
            ),
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=10",
                "page-1",
            ),
        ]
    )
    context = _FakeListContext(list_page)
    browser = _FakeListBrowser(context)
    parsed_pages = {
        "page-0": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=True,
        ),
        "page-1": SimpleNamespace(
            orders=[{"orderId": "222-2222222-2222222", "detailsUrl": "https://www.amazon.de/order/222"}],
            has_next_page=False,
        ),
    }

    monkeypatch.setattr("lidltool.amazon.client_playwright.sync_playwright", lambda: _FakePlaywrightManager())
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium",
        lambda playwright, headless: browser,
    )
    monkeypatch.setattr(
        "lidltool.amazon.client_playwright.parse_order_list_html",
        lambda html, profile, page_url: parsed_pages[html],
    )

    client = AmazonPlaywrightClient(
        state_file=state_file,
        source_id="amazon_de",
        headless=True,
    )

    def fake_ensure_logged_in(url: str, html: str) -> None:
        if html == "signin":
            raise AmazonReauthRequiredError("temporary auth block", auth_state="expired_session")

    monkeypatch.setattr(client, "_ensure_logged_in", fake_ensure_logged_in)
    monkeypatch.setattr(client, "_enrich_order_from_details", lambda context, order: None)

    orders = client.fetch_orders(years=1, max_pages_per_year=None)

    assert [order["orderId"] for order in orders] == [
        "111-1111111-1111111",
        "222-2222222-2222222",
    ]
    assert list_page._index == 2
    assert context.storage_state_paths == [str(state_file), str(state_file)]


def test_merge_detail_parse_result_does_not_overwrite_existing_list_order_date(tmp_path) -> None:
    client = AmazonPlaywrightClient(
        state_file=tmp_path / "amazon_storage_state.json",
        source_id="amazon_de",
        headless=True,
    )
    order = {
        "orderId": "111-1111111-1111111",
        "orderDate": "14. April 2025",
        "dateSource": "list_order_date",
        "totalAmount": 29.98,
        "currency": "EUR",
        "items": [{"title": "USB Kabel", "asin": "B00TEST111", "quantity": 1, "price": 29.98}],
        "orderStatus": "Zugestellt",
        "detailsUrl": "https://www.amazon.de/your-orders/order-details?orderID=111-1111111-1111111",
        "promotions": [],
        "totalSavings": 0,
        "parseStatus": "partial",
        "parseWarnings": [],
        "unsupportedReason": None,
    }
    detail = SimpleNamespace(
        data={
            "items": [],
            "orderDate": "",
            "promotions": [],
            "shipping": 0,
            "gift_wrap": 0,
            "totalAmount": 29.98,
            "subtotals": [],
        },
        parse_warnings=[],
        parse_status="partial",
        unsupported_reason=None,
    )

    client._merge_detail_parse_result(order=order, detail=detail)  # noqa: SLF001

    assert order["orderDate"] == "14. April 2025"
    assert order["dateSource"] == "list_order_date"


def test_fetch_orders_uses_persistent_profile_dir_when_available(tmp_path, monkeypatch) -> None:
    profile_dir = tmp_path / "amazon-profile"
    profile_dir.mkdir()
    (profile_dir / "Cookies").write_text("cookie-db", encoding="utf-8")
    list_page = _FakeListPage(
        pages=[
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=0",
                "page-0",
            ),
        ]
    )
    context = _FakeListContext(list_page)
    parsed_pages = {
        "page-0": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=False,
        ),
    }

    monkeypatch.setattr("lidltool.amazon.client_playwright.sync_playwright", lambda: _FakePlaywrightManager())
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium_persistent_context",
        lambda playwright, user_data_dir, headless: context,
    )
    monkeypatch.setattr(
        "lidltool.amazon.client_playwright.parse_order_list_html",
        lambda html, profile, page_url: parsed_pages[html],
    )

    client = AmazonPlaywrightClient(
        state_file=tmp_path / "amazon_storage_state.json",
        profile_dir=profile_dir,
        source_id="amazon_de",
        headless=True,
    )
    monkeypatch.setattr(client, "_ensure_logged_in", lambda url, html: None)
    monkeypatch.setattr(client, "_enrich_order_from_details", lambda context, order: None)

    orders = client.fetch_orders(years=1, max_pages_per_year=None)

    assert [order["orderId"] for order in orders] == ["111-1111111-1111111"]


def test_fetch_orders_falls_back_to_storage_state_when_profile_dir_is_locked(tmp_path, monkeypatch) -> None:
    profile_dir = tmp_path / "amazon-profile"
    profile_dir.mkdir()
    (profile_dir / "Cookies").write_text("cookie-db", encoding="utf-8")
    state_file = tmp_path / "amazon_storage_state.json"
    state_file.write_text("{}", encoding="utf-8")
    list_page = _FakeListPage(
        pages=[
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=0",
                "page-0",
            ),
        ]
    )
    context = _FakeListContext(list_page)
    browser = _FakeListBrowser(context)
    parsed_pages = {
        "page-0": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=False,
        ),
    }

    monkeypatch.setattr("lidltool.amazon.client_playwright.sync_playwright", lambda: _FakePlaywrightManager())
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium_persistent_context",
        lambda playwright, user_data_dir, headless: (_ for _ in ()).throw(
            RuntimeError("Failed to create a ProcessSingleton for your profile directory")
        ),
    )
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium",
        lambda playwright, headless: browser,
    )
    monkeypatch.setattr(
        "lidltool.amazon.client_playwright.parse_order_list_html",
        lambda html, profile, page_url: parsed_pages[html],
    )

    client = AmazonPlaywrightClient(
        state_file=state_file,
        profile_dir=profile_dir,
        source_id="amazon_de",
        headless=True,
    )
    monkeypatch.setattr(client, "_ensure_logged_in", lambda url, html: None)
    monkeypatch.setattr(client, "_enrich_order_from_details", lambda context, order: None)

    orders = client.fetch_orders(years=1, max_pages_per_year=None)

    assert [order["orderId"] for order in orders] == ["111-1111111-1111111"]


def test_fetch_orders_opens_fresh_page_for_persistent_profile(tmp_path, monkeypatch) -> None:
    profile_dir = tmp_path / "amazon-profile"
    profile_dir.mkdir()
    (profile_dir / "Cookies").write_text("cookie-db", encoding="utf-8")
    restored_page = _FakePage(
        url="https://www.amazon.de/ap/signin",
        html="signin",
    )
    list_page = _FakeListPage(
        pages=[
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=0",
                "page-0",
            ),
        ]
    )
    context = _FakeListContext(list_page, restored_pages=[restored_page])
    parsed_pages = {
        "page-0": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=False,
        ),
    }

    monkeypatch.setattr("lidltool.amazon.client_playwright.sync_playwright", lambda: _FakePlaywrightManager())
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium_persistent_context",
        lambda playwright, user_data_dir, headless: context,
    )
    monkeypatch.setattr(
        "lidltool.amazon.client_playwright.parse_order_list_html",
        lambda html, profile, page_url: parsed_pages[html],
    )

    client = AmazonPlaywrightClient(
        state_file=tmp_path / "amazon_storage_state.json",
        profile_dir=profile_dir,
        source_id="amazon_de",
        headless=True,
    )
    monkeypatch.setattr(client, "_ensure_logged_in", lambda url, html: None)
    monkeypatch.setattr(client, "_enrich_order_from_details", lambda context, order: None)

    orders = client.fetch_orders(years=1, max_pages_per_year=None)

    assert [order["orderId"] for order in orders] == ["111-1111111-1111111"]
    assert context.new_page_calls == 1
    assert restored_page.closed is True


def test_fetch_orders_tolerates_stalled_page_when_amazon_still_has_next_page(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "amazon_storage_state.json"
    state_file.write_text("{}", encoding="utf-8")
    list_page = _FakeListPage(
        pages=[
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=0",
                "page-0",
            ),
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=10",
                "page-1",
            ),
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=20",
                "page-2",
            ),
        ]
    )
    context = _FakeListContext(list_page)
    browser = _FakeListBrowser(context)
    parsed_pages = {
        "page-0": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=True,
        ),
        "page-1": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=True,
        ),
        "page-2": SimpleNamespace(
            orders=[{"orderId": "222-2222222-2222222", "detailsUrl": "https://www.amazon.de/order/222"}],
            has_next_page=False,
        ),
    }

    monkeypatch.setattr("lidltool.amazon.client_playwright.sync_playwright", lambda: _FakePlaywrightManager())
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium",
        lambda playwright, headless: browser,
    )
    monkeypatch.setattr(
        "lidltool.amazon.client_playwright.parse_order_list_html",
        lambda html, profile, page_url: parsed_pages[html],
    )

    client = AmazonPlaywrightClient(
        state_file=state_file,
        source_id="amazon_de",
        headless=True,
    )
    monkeypatch.setattr(client, "_ensure_logged_in", lambda url, html: None)
    monkeypatch.setattr(client, "_enrich_order_from_details", lambda context, order: None)

    orders = client.fetch_orders(years=1, max_pages_per_year=None)

    assert [order["orderId"] for order in orders] == [
        "111-1111111-1111111",
        "222-2222222-2222222",
    ]
    assert list_page._index == 2


def test_fetch_orders_continues_past_multiple_duplicate_pages_until_next_page_ends(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "amazon_storage_state.json"
    state_file.write_text("{}", encoding="utf-8")
    list_page = _FakeListPage(
        pages=[
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=0",
                "page-0",
            ),
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=10",
                "page-1",
            ),
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=20",
                "page-2",
            ),
            (
                "https://www.amazon.de/gp/your-account/order-history?orderFilter=year-2026&startIndex=30",
                "page-3",
            ),
        ]
    )
    context = _FakeListContext(list_page)
    browser = _FakeListBrowser(context)
    parsed_pages = {
        "page-0": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=True,
        ),
        "page-1": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=True,
        ),
        "page-2": SimpleNamespace(
            orders=[{"orderId": "111-1111111-1111111", "detailsUrl": "https://www.amazon.de/order/111"}],
            has_next_page=True,
        ),
        "page-3": SimpleNamespace(
            orders=[{"orderId": "222-2222222-2222222", "detailsUrl": "https://www.amazon.de/order/222"}],
            has_next_page=False,
        ),
    }

    monkeypatch.setattr("lidltool.amazon.client_playwright.sync_playwright", lambda: _FakePlaywrightManager())
    monkeypatch.setattr(
        "lidltool.connectors.auth.browser_runtime.launch_playwright_chromium",
        lambda playwright, headless: browser,
    )
    monkeypatch.setattr(
        "lidltool.amazon.client_playwright.parse_order_list_html",
        lambda html, profile, page_url: parsed_pages[html],
    )

    client = AmazonPlaywrightClient(
        state_file=state_file,
        source_id="amazon_de",
        headless=True,
    )
    monkeypatch.setattr(client, "_ensure_logged_in", lambda url, html: None)
    monkeypatch.setattr(client, "_enrich_order_from_details", lambda context, order: None)

    orders = client.fetch_orders(years=1, max_pages_per_year=None)

    assert [order["orderId"] for order in orders] == [
        "111-1111111-1111111",
        "222-2222222-2222222",
    ]
    assert list_page._index == 3


def test_load_authenticated_html_waits_for_visible_auth_recovery(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "amazon_storage_state.json"
    profile_dir = tmp_path / "amazon-profile"
    profile_dir.mkdir()
    (profile_dir / "Cookies").write_text("cookie-db", encoding="utf-8")
    page = _FakePage(
        url="https://www.amazon.de/ap/signin",
        html="signin",
        timed_states=[
            ("https://www.amazon.de/ap/signin", "signin"),
            (
                "https://www.amazon.de/gp/your-account/order-history",
                "<html><body>Meine Bestellungen</body></html>",
            ),
        ],
    )
    context = _FakeContext(
        response=_FakeResponse(ok=False),
        page=page,
    )
    client = AmazonPlaywrightClient(
        state_file=state_file,
        profile_dir=profile_dir,
        source_id="amazon_de",
        headless=False,
        page_delay_ms=100,
    )

    def fake_ensure_logged_in(url: str, html: str) -> None:
        del url
        if html == "signin":
            raise AmazonReauthRequiredError("needs browser attention", auth_state="unknown_auth_block")

    monkeypatch.setattr(client, "_ensure_logged_in", fake_ensure_logged_in)

    html = client._load_authenticated_html(  # noqa: SLF001
        page=page,
        context=context,
        url="https://www.amazon.de/gp/your-account/order-history",
        retries=0,
    )

    assert "Meine Bestellungen" in html
    assert context.storage_state_paths == [str(state_file)]
