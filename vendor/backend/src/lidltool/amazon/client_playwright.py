from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, sync_playwright

from lidltool.amazon.auth_state import classify_amazon_auth_state, describe_auth_failure
from lidltool.amazon.parsers import (
    AmazonParseResult,
    merge_item_details,
    parse_order_detail_html,
    parse_order_list_html,
    parse_promotions_from_details_html,
)
from lidltool.amazon.profiles import GERMANY_PROFILE, AmazonCountryProfile, get_country_profile


class AmazonClientError(RuntimeError):
    pass


class AmazonReauthRequiredError(AmazonClientError):
    def __init__(
        self,
        message: str,
        *,
        auth_state: str | None = None,
    ) -> None:
        super().__init__(message)
        self.auth_state = auth_state


REAUTH_URL_PATTERNS = GERMANY_PROFILE.auth_rules.blocked_url_patterns()
REAUTH_HTML_MARKERS = GERMANY_PROFILE.auth_rules.blocked_html_markers()


def _parse_amazon_de_date(text: str):
    return GERMANY_PROFILE.date_parser(text)


def _parse_de_amount(text: str) -> float:
    return abs(GERMANY_PROFILE.amount_parser(text))


def _parse_order_detail_html(html: str) -> dict[str, Any]:
    return parse_order_detail_html(html, profile=GERMANY_PROFILE).data


def _parse_promotions_from_details_html(html: str) -> list[dict[str, Any]]:
    return parse_promotions_from_details_html(html, profile=GERMANY_PROFILE)


def _merge_item_details(
    list_items: list[dict[str, Any]],
    detail_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return merge_item_details(list_items, detail_items, profile=GERMANY_PROFILE)


class AmazonPlaywrightClient:
    def __init__(
        self,
        *,
        state_file: Path,
        source_id: str = "amazon_de",
        domain: str | None = None,
        headless: bool = True,
        page_delay_ms: int = 800,
        dump_html_dir: Path | None = None,
    ) -> None:
        self._state_file = state_file
        self._profile = get_country_profile(source_id=source_id, domain=domain)
        self._source_id = self._profile.source_id
        self._headless = headless
        self._page_delay_ms = page_delay_ms
        self._dump_html_dir = dump_html_dir

    @property
    def profile(self) -> AmazonCountryProfile:
        return self._profile

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def domain(self) -> str:
        return self._profile.normalized_domain()

    def fetch_orders(self, *, years: int = 2, max_pages_per_year: int = 8) -> list[dict[str, Any]]:
        if not self._state_file.exists():
            raise AmazonReauthRequiredError(
                f"Amazon session state missing: {self._state_file}. "
                f"Run 'lidltool connectors auth bootstrap --source-id {self._source_id}' first.",
                auth_state="expired_session",
            )

        seen_order_ids: set[str] = set()
        out: list[dict[str, Any]] = []
        current_year = datetime.now().year

        with sync_playwright() as playwright:
            from lidltool.connectors.auth.browser_runtime import launch_playwright_chromium

            browser = launch_playwright_chromium(playwright=playwright, headless=self._headless)
            context = browser.new_context(storage_state=str(self._state_file))
            page = context.new_page()

            try:
                for offset in range(max(1, years)):
                    year = current_year - offset
                    year_any = False
                    for page_idx in range(max(1, max_pages_per_year)):
                        start_idx = page_idx * 10
                        page.goto(
                            self._profile.order_history_url(year=year, start_index=start_idx),
                            wait_until="domcontentloaded",
                        )
                        page.wait_for_timeout(self._page_delay_ms)

                        page_html = page.content()
                        self._ensure_logged_in(page.url, page_html)
                        self._maybe_dump_html(page_html, f"order_list_y{year}_p{page_idx}.html")

                        parsed_page = parse_order_list_html(
                            page_html,
                            profile=self._profile,
                            page_url=page.url,
                        )
                        if not parsed_page.orders:
                            break

                        page_new = 0
                        for row in parsed_page.orders:
                            order_id = row.get("orderId")
                            if not isinstance(order_id, str) or not order_id or order_id in seen_order_ids:
                                continue
                            seen_order_ids.add(order_id)
                            self._enrich_order_from_details(context, row)
                            out.append(row)
                            page_new += 1

                        if page_new == 0:
                            break
                        year_any = True
                        if not parsed_page.has_next_page:
                            break

                    if not year_any and offset > 0:
                        continue
            finally:
                context.close()
                browser.close()

        return out

    def _ensure_logged_in(self, url: str, html: str) -> None:
        classification = classify_amazon_auth_state(
            url=url,
            html=html,
            profile=self._profile,
            expect_authenticated_session=True,
        )
        if classification.authenticated:
            return
        raise AmazonReauthRequiredError(
            describe_auth_failure(source_id=self._source_id, classification=classification),
            auth_state=classification.state.value,
        )

    def _enrich_order_from_details(self, context: BrowserContext, order: dict[str, Any]) -> None:
        details_url = order.get("detailsUrl")
        if not isinstance(details_url, str) or not details_url:
            order.setdefault("parseWarnings", []).append("missing_details_url")
            order["parseStatus"] = "partial"
            return

        try:
            response = context.request.get(details_url)
        except Exception:  # noqa: BLE001
            order.setdefault("parseWarnings", []).append("detail_request_failed")
            order["parseStatus"] = "partial"
            return
        if not response.ok:
            order.setdefault("parseWarnings", []).append("detail_response_not_ok")
            order["parseStatus"] = "partial"
            return

        html = response.text()
        classification = classify_amazon_auth_state(
            url=str(getattr(response, "url", details_url) or details_url),
            html=html,
            profile=self._profile,
            expect_authenticated_session=True,
        )
        if not classification.authenticated:
            raise AmazonReauthRequiredError(
                describe_auth_failure(source_id=self._source_id, classification=classification),
                auth_state=classification.state.value,
            )

        order_id = str(order.get("orderId") or "unknown")
        self._maybe_dump_html(html, f"order_detail_{order_id}.html")
        detail = parse_order_detail_html(html, profile=self._profile)
        self._merge_detail_parse_result(order=order, detail=detail)

    def _merge_detail_parse_result(
        self,
        *,
        order: dict[str, Any],
        detail: AmazonParseResult,
    ) -> None:
        if detail.data["items"]:
            order["items"] = merge_item_details(
                order.get("items") or [],
                detail.data["items"],
                profile=self._profile,
            )
        if detail.data["promotions"]:
            order["promotions"] = detail.data["promotions"]
            order["totalSavings"] = round(
                sum(abs(float(p.get("amount") or 0)) for p in detail.data["promotions"]),
                2,
            )
        if detail.data["shipping"] > 0:
            order["shipping"] = detail.data["shipping"]
        if detail.data["gift_wrap"] > 0:
            order["gift_wrap"] = detail.data["gift_wrap"]
        if detail.data.get("subtotals"):
            order["subtotals"] = detail.data["subtotals"]

        warnings = list(order.get("parseWarnings") or [])
        warnings.extend(detail.parse_warnings)
        order["parseWarnings"] = sorted(set(str(item) for item in warnings if item))

        existing_status = str(order.get("parseStatus") or "complete")
        order["parseStatus"] = _merge_parse_status(existing_status, detail.parse_status)
        if detail.unsupported_reason:
            order["unsupportedReason"] = detail.unsupported_reason

    def _maybe_dump_html(self, html: str, filename: str) -> None:
        if self._dump_html_dir is None:
            return
        self._dump_html_dir.mkdir(parents=True, exist_ok=True)
        (self._dump_html_dir / filename).write_text(html, encoding="utf-8")


def _merge_parse_status(current: str, next_status: str) -> str:
    severity = {"complete": 0, "partial": 1, "unsupported": 2}
    return max((current, next_status), key=lambda value: severity.get(value, 0))
