from __future__ import annotations

from datetime import datetime
from pathlib import Path
from collections.abc import Callable, Iterator
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
        profile_dir: Path | None = None,
        source_id: str = "amazon_de",
        domain: str | None = None,
        headless: bool = True,
        page_delay_ms: int = 800,
        dump_html_dir: Path | None = None,
        auth_interaction_timeout_s: int = 600,
    ) -> None:
        self._state_file = state_file
        self._profile_dir = profile_dir.expanduser().resolve() if profile_dir is not None else None
        self._profile = get_country_profile(source_id=source_id, domain=domain)
        self._source_id = self._profile.source_id
        self._headless = headless
        self._page_delay_ms = page_delay_ms
        self._dump_html_dir = dump_html_dir
        self._auth_interaction_timeout_s = max(30, auth_interaction_timeout_s)

    @property
    def profile(self) -> AmazonCountryProfile:
        return self._profile

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def domain(self) -> str:
        return self._profile.normalized_domain()

    def fetch_orders(self, *, years: int = 2, max_pages_per_year: int | None = None) -> list[dict[str, Any]]:
        return list(self.iter_orders(years=years, max_pages_per_year=max_pages_per_year))

    def iter_orders(
        self,
        *,
        years: int = 2,
        max_pages_per_year: int | None = None,
        max_pages: int | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
    ) -> Iterator[dict[str, Any]]:
        if not self._session_artifact_exists():
            raise AmazonReauthRequiredError(
                f"Amazon session state missing: {self._state_file}. "
                f"Run 'lidltool connectors auth bootstrap --source-id {self._source_id}' first.",
                auth_state="expired_session",
            )

        seen_order_ids: set[str] = set()
        current_year = datetime.now().year
        pages_visited = 0

        with sync_playwright() as playwright:
            context, browser = self._open_authenticated_context(playwright=playwright)
            page = self._open_work_page(context)

            try:
                for offset in range(max(1, years)):
                    year = current_year - offset
                    year_any = False
                    page_idx = 0
                    last_page_marker: tuple[str, tuple[str, ...]] | None = None
                    while True:
                        if max_pages is not None and pages_visited >= max(1, max_pages):
                            return
                        if max_pages_per_year is not None and page_idx >= max(1, max_pages_per_year):
                            break
                        start_idx = page_idx * 10
                        page_html = self._load_authenticated_html(
                            page=page,
                            context=context,
                            url=self._profile.order_history_url(year=year, start_index=start_idx),
                        )
                        self._maybe_dump_html(page_html, f"order_list_y{year}_p{page_idx}.html")

                        parsed_page = parse_order_list_html(
                            page_html,
                            profile=self._profile,
                            page_url=page.url,
                        )
                        if not parsed_page.orders:
                            break
                        page_signature = tuple(
                            str(row.get("orderId") or "").strip()
                            for row in parsed_page.orders
                            if str(row.get("orderId") or "").strip()
                        )
                        page_marker = (str(page.url), page_signature)
                        if page_signature and page_marker == last_page_marker:
                            break
                        last_page_marker = page_marker
                        pages_visited += 1
                        if progress_cb is not None:
                            progress_cb(
                                {
                                    "pages": pages_visited,
                                    "discovered_receipts": len(seen_order_ids),
                                    "current_year": year,
                                    "current_page": page_idx + 1,
                                }
                            )

                        page_new = 0
                        for row in parsed_page.orders:
                            row.setdefault("pageYear", year)
                            row.setdefault("pageIndex", page_idx)
                            row.setdefault("pageStartIndex", start_idx)
                            row.setdefault(
                                "dateSource",
                                "list_order_date"
                                if str(row.get("orderDate") or "").strip()
                                else "page_year",
                            )
                            order_id = row.get("orderId")
                            if not isinstance(order_id, str) or not order_id or order_id in seen_order_ids:
                                continue
                            seen_order_ids.add(order_id)
                            self._enrich_order_from_details(context, row)
                            if progress_cb is not None:
                                progress_cb(
                                    {
                                        "pages": pages_visited,
                                        "discovered_receipts": len(seen_order_ids),
                                        "current_year": year,
                                        "current_page": page_idx + 1,
                                        "current_record_ref": order_id,
                                    }
                                )
                            yield row
                            page_new += 1

                        if page_new > 0:
                            year_any = True
                        if not parsed_page.has_next_page:
                            break
                        page_idx += 1

                    if not year_any and offset > 0:
                        continue
            finally:
                context.close()
                if browser is not None:
                    browser.close()

    def validate_session(self) -> None:
        if not self._session_artifact_exists():
            raise AmazonReauthRequiredError(
                f"Amazon session state missing: {self._state_file}. "
                f"Run 'lidltool connectors auth bootstrap --source-id {self._source_id}' first.",
                auth_state="expired_session",
            )

        with sync_playwright() as playwright:
            context, browser = self._open_authenticated_context(playwright=playwright)
            page = self._open_work_page(context)
            try:
                self._load_authenticated_html(
                    page=page,
                    context=context,
                    url=self._profile.order_history_url(),
                )
            finally:
                context.close()
                if browser is not None:
                    browser.close()

    def _session_artifact_exists(self) -> bool:
        if self._profile_dir is not None and self._profile_dir.exists():
            try:
                next(self._profile_dir.iterdir())
            except StopIteration:
                pass
            else:
                return True
        return self._state_file.exists()

    def _open_authenticated_context(self, *, playwright: Any) -> tuple[Any, Any | None]:
        from lidltool.connectors.auth.browser_runtime import (
            launch_playwright_chromium,
            launch_playwright_chromium_persistent_context,
        )

        if self._profile_dir is not None and self._profile_dir.exists():
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            try:
                context = launch_playwright_chromium_persistent_context(
                    playwright=playwright,
                    user_data_dir=self._profile_dir,
                    headless=self._headless,
                )
                return context, None
            except Exception as exc:  # noqa: BLE001
                if not _looks_like_profile_in_use_error(exc) or not self._state_file.exists():
                    raise
                browser = launch_playwright_chromium(playwright=playwright, headless=self._headless)
                context = browser.new_context(storage_state=str(self._state_file))
                return context, browser

        browser = launch_playwright_chromium(playwright=playwright, headless=self._headless)
        context = browser.new_context(storage_state=str(self._state_file))
        return context, browser

    def _open_work_page(self, context: BrowserContext) -> Any:
        restored_pages = list(getattr(context, "pages", ()) or ())
        page = context.new_page()
        for restored_page in restored_pages:
            if restored_page is page:
                continue
            try:
                restored_page.close()
            except Exception:  # noqa: BLE001
                continue
        return page

    def _supports_interactive_auth_recovery(self) -> bool:
        return not self._headless and self._profile_dir is not None

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

        fetch_warning: str | None = None
        html: str | None = None
        try:
            response = context.request.get(details_url)
        except Exception:  # noqa: BLE001
            fetch_warning = "detail_request_failed"
        else:
            if response.ok:
                try:
                    html = self._validated_detail_html(
                        url=str(getattr(response, "url", details_url) or details_url),
                        html=response.text(),
                    )
                except AmazonReauthRequiredError:
                    fetch_warning = "detail_request_auth_failed"
            else:
                fetch_warning = "detail_response_not_ok"

        if html is None:
            try:
                html = self._fetch_detail_html_via_page(context=context, details_url=details_url)
            except AmazonReauthRequiredError:
                raise
            except Exception:  # noqa: BLE001
                order.setdefault("parseWarnings", []).append(fetch_warning or "detail_request_failed")
                order["parseStatus"] = "partial"
                return

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
        if detail.data.get("orderDate") and not str(order.get("orderDate") or "").strip():
            order["orderDate"] = detail.data["orderDate"]
            order["dateSource"] = "detail_order_date"
        if detail.data.get("totalAmount") is not None:
            order["totalAmount"] = detail.data["totalAmount"]
        if detail.data.get("subtotals"):
            order["subtotals"] = detail.data["subtotals"]
        self._apply_sparse_item_price_fallback(order)

        warnings = list(order.get("parseWarnings") or [])
        warnings.extend(detail.parse_warnings)
        order["parseWarnings"] = _reconcile_order_warnings(
            order=order,
            warnings=warnings,
        )
        order["parseStatus"] = _final_parse_status(
            order=order,
            fallback_status=_merge_parse_status(str(order.get("parseStatus") or "complete"), detail.parse_status),
        )
        if detail.unsupported_reason:
            order["unsupportedReason"] = detail.unsupported_reason

    def _apply_sparse_item_price_fallback(self, order: dict[str, Any]) -> None:
        items = list(order.get("items") or [])
        if len(items) != 1:
            return
        try:
            total_amount = float(order.get("totalAmount") or 0)
        except (TypeError, ValueError):
            return
        if total_amount <= 0:
            return
        if float(order.get("shipping") or 0) > 0 or float(order.get("gift_wrap") or 0) > 0:
            return
        if any(abs(float(promo.get("amount") or 0)) > 0 for promo in order.get("promotions") or []):
            return
        item = items[0]
        try:
            item_price = float(item.get("price") or 0)
        except (TypeError, ValueError):
            item_price = 0
        if item_price > 0:
            return
        item["price"] = round(total_amount, 2)

    def _maybe_dump_html(self, html: str, filename: str) -> None:
        if self._dump_html_dir is None:
            return
        self._dump_html_dir.mkdir(parents=True, exist_ok=True)
        (self._dump_html_dir / filename).write_text(html, encoding="utf-8")

    def _validated_detail_html(self, *, url: str, html: str) -> str:
        classification = classify_amazon_auth_state(
            url=url,
            html=html,
            profile=self._profile,
            expect_authenticated_session=True,
        )
        if classification.authenticated:
            return html
        raise AmazonReauthRequiredError(
            describe_auth_failure(source_id=self._source_id, classification=classification),
            auth_state=classification.state.value,
        )

    def _fetch_detail_html_via_page(self, *, context: BrowserContext, details_url: str) -> str:
        page = context.new_page()
        try:
            return self._load_authenticated_html(
                page=page,
                context=context,
                url=details_url,
            )
        finally:
            page.close()

    def _load_authenticated_html(
        self,
        *,
        page: Any,
        context: BrowserContext,
        url: str,
        retries: int = 1,
    ) -> str:
        last_error: AmazonReauthRequiredError | None = None
        for attempt in range(max(0, retries) + 1):
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(self._page_delay_ms)
            html = page.content()
            try:
                self._ensure_logged_in(page.url, html)
            except AmazonReauthRequiredError as exc:
                last_error = exc
                if self._supports_interactive_auth_recovery():
                    return self._await_interactive_auth_resolution(
                        page=page,
                        context=context,
                        target_url=url,
                        original_error=exc,
                    )
                if attempt >= max(0, retries):
                    raise
                page.wait_for_timeout(self._page_delay_ms * 2)
                continue
            self._persist_storage_state(context)
            return html
        if last_error is not None:
            raise last_error
        raise AmazonClientError("failed to load authenticated Amazon page")

    def _await_interactive_auth_resolution(
        self,
        *,
        page: Any,
        context: BrowserContext,
        target_url: str,
        original_error: AmazonReauthRequiredError,
    ) -> str:
        print(
            "Amazon needs attention in the browser window. Complete sign-in, MFA, CAPTCHA, or any challenge to continue the import.",
            flush=True,
        )
        attempts = max(1, int((self._auth_interaction_timeout_s * 1000) / max(250, self._page_delay_ms)))
        last_html = ""
        for _ in range(attempts):
            page.wait_for_timeout(max(250, self._page_delay_ms))
            last_html = page.content()
            classification = classify_amazon_auth_state(
                url=page.url,
                html=last_html,
                profile=self._profile,
                expect_authenticated_session=True,
            )
            if not classification.authenticated:
                continue
            page.goto(target_url, wait_until="domcontentloaded")
            page.wait_for_timeout(self._page_delay_ms)
            recovered_html = page.content()
            self._ensure_logged_in(page.url, recovered_html)
            self._persist_storage_state(context)
            print("Amazon challenge resolved. Continuing import.", flush=True)
            return recovered_html
        if last_html:
            self._maybe_dump_html(last_html, "session_probe_auth_attention_timeout.html")
        raise original_error

    def _persist_storage_state(self, context: BrowserContext) -> None:
        storage_state = getattr(context, "storage_state", None)
        if not callable(storage_state):
            return
        try:
            storage_state(path=str(self._state_file))
        except Exception:  # noqa: BLE001
            return


def _merge_parse_status(current: str, next_status: str) -> str:
    severity = {"complete": 0, "partial": 1, "unsupported": 2}
    return max((current, next_status), key=lambda value: severity.get(value, 0))


def _reconcile_order_warnings(*, order: dict[str, Any], warnings: list[Any]) -> list[str]:
    reconciled = {str(item) for item in warnings if item}
    if str(order.get("orderDate") or "").strip():
        reconciled.discard("missing_order_date")
    total_amount = order.get("totalAmount")
    if not (total_amount is None or (isinstance(total_amount, str) and not total_amount.strip())):
        reconciled.discard("missing_total_amount")
    if str(order.get("detailsUrl") or "").strip():
        reconciled.discard("missing_details_url")
    items = order.get("items")
    if isinstance(items, list) and items:
        reconciled.discard("missing_list_items")
    return sorted(reconciled)


def _final_parse_status(*, order: dict[str, Any], fallback_status: str) -> str:
    if order.get("unsupportedReason"):
        return "unsupported"
    warnings = order.get("parseWarnings")
    if isinstance(warnings, list) and warnings:
        return "partial"
    if fallback_status == "unsupported":
        return "unsupported"
    return "complete"


def _looks_like_profile_in_use_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "processsingleton" in message
        or "profile directory is already in use" in message
        or "failed to create a processsingleton" in message
        or "singletonlock" in message
    )
