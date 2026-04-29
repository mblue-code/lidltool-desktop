from __future__ import annotations

import base64
import importlib
import inspect
import logging
import re
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast
from urllib.parse import urlparse

import httpx

from lidltool.config import AppConfig
from lidltool.lidl.models_raw import ReceiptPage

if TYPE_CHECKING:
    from lidltool.auth.token_store import TokenStore

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


class LidlClientError(RuntimeError):
    pass


class LidlAuthError(LidlClientError):
    pass


class LidlReauthRequiredError(LidlAuthError):
    """Refresh token was rejected by the auth server. Re-run 'lidltool auth bootstrap'."""

    pass


class LidlClient(Protocol):
    def list_receipts(self, page_token: str | None = None, page_size: int = 50) -> ReceiptPage: ...

    def get_receipt(self, receipt_id: str) -> dict[str, Any]: ...


def _validate_endpoint_security(config: AppConfig, url: str, *, endpoint_name: str) -> None:
    parsed = urlparse(url)
    if not parsed.scheme:
        raise LidlClientError(f"{endpoint_name} must include URL scheme")
    if parsed.scheme.lower() != "https" and not config.allow_insecure_transport:
        raise LidlClientError(
            f"{endpoint_name} must use https (set LIDLTOOL_ALLOW_INSECURE_TRANSPORT=true only for local testing)"
        )


class RateLimiter:
    def __init__(self, max_per_second: float) -> None:
        self._interval = 1.0 / max(max_per_second, 0.1)
        self._last_call = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last_call = time.monotonic()


# ---------------------------------------------------------------------------
# MRE API client (primary) — www.lidl.de/mre/api/v1
# ---------------------------------------------------------------------------

_VAT_TYPE_MAP: dict[str, float] = {"A": 0.07, "B": 0.19}
_DISCOUNT_AMOUNT_RE = re.compile(r"-\d+[,\.]\d{1,2}")
_ANON_AMOUNT_RE = re.compile(r"^-?\d+[,\.]\d{1,2}$")


def _classify_discount(promotion_id: str) -> str:
    """Map a promotion-id to a discount type label.

    Known patterns observed in German receipts:
    - ``_DISCOUNT2``        → MHD (best-before 20 % discount)
    - ``100001000-*`` / ``100001001-*`` → Lidl Plus member discount
    - anything else         → generic promotional discount
    """
    if promotion_id == "_DISCOUNT2":
        return "mhd"
    if promotion_id.startswith(("100001000-", "100001001-")):
        return "lidl_plus"
    return "promotion"


def _parse_discount_amount(text: str) -> int:
    """Return the discount amount in cents (negative int) from visible text.

    Example inputs: ``'RABATT 20% -0,86'``, ``'Lidl Plus Rabatt -0,65'``.
    Returns 0 when no amount can be extracted.
    """
    m = _DISCOUNT_AMOUNT_RE.search(text)
    if not m:
        return 0
    raw = m.group().replace(",", ".")
    try:
        return int(round(float(raw) * 100))
    except ValueError:
        return 0


def _format_ticket_total_amount(value: Any) -> Any:
    """Preserve Lidl summary totals as euro values, even when the API returns an int.

    The MRE list endpoint returns ``totalAmount`` in euros. When a receipt total is a
    whole-euro amount, the JSON parser hands us an ``int`` (for example ``19``). The
    generic normalizer treats plain ints as cents, so we coerce numeric values back to
    a two-decimal euro string before they reach ``normalize_receipt``.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        try:
            return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"
        except (InvalidOperation, ValueError):
            return value
    return value


class _MreReceiptParser(HTMLParser):
    """Extract line items (and their discounts) from Lidl MRE HTML receipts.

    Article spans carry item data in ``data-*`` attributes.
    Discount spans immediately follow their article and carry a
    ``data-promotion-id`` plus the discount label/amount as visible text.
    A single article can have multiple discounts (e.g. MHD + Lidl Plus).

    Anonymous receipt lines (no article class, no promotion-id) cover:
    - Pfandrückgabe: deposit returns (negative amount, added as deposit item)
    - Aktionsrabatt / store discounts: added as discount on the previous item
    Multiple sibling spans share the same purchase_list_line_N id; we collect
    all their text and finalize when the line id changes.
    """

    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, Any]] = []
        self._seen: set[str] = set()
        # State for the discount span currently being parsed
        self._cur_discount: dict[str, Any] | None = None
        self._discount_text: list[str] = []
        self._discount_depth: int = 0
        # State for anonymous receipt lines (Pfandrückgabe, Aktionsrabatt, …)
        self._cur_anon_id: str | None = None
        self._anon_texts: list[str] = []

    def _finalize_anon(self) -> None:
        """Process accumulated text for the current anonymous receipt line."""
        if not self._cur_anon_id:
            return
        texts = self._anon_texts
        self._cur_anon_id = None
        self._anon_texts = []
        if not texts:
            return
        amount_str = next((t for t in texts if _ANON_AMOUNT_RE.match(t)), None)
        if amount_str is None:
            return
        non_amount_texts = [t for t in texts if not _ANON_AMOUNT_RE.match(t)]
        if not non_amount_texts:
            return
        label = non_amount_texts[0]
        if len(label) == 1 and label.isalpha():
            return
        if not any(ch.isalpha() for ch in label):
            return
        try:
            amount = float(amount_str.replace(",", "."))
        except ValueError:
            return
        label_lower = label.lower()
        tax_marker = next(
            (
                candidate.upper()
                for candidate in reversed(non_amount_texts[1:])
                if len(candidate) == 1 and candidate.upper() in _VAT_TYPE_MAP
            ),
            None,
        )
        if "pfand" in label_lower:
            # Pfandrückgabe — negative deposit return, tracked as a deposit item
            item: dict[str, Any] = {
                "name": label,
                "qty": 1.0,
                "unitPrice": amount,
                "lineTotal": amount,
                "discounts": [],
            }
            if tax_marker is not None:
                item["vatRate"] = _VAT_TYPE_MAP[tax_marker]
            self.items.append(item)
        elif any(k in label_lower for k in (
            "rabatt", "aktions", "reduz", "bonus",
            "preisvorteil", "vorteil", "preisreduz",
            "sonderpreis", "sonderangebot", "treue",
            "nachlass", "ersparnis",
        )):
            # Store/promotional discount without a promotion-id — attach to previous item
            if self.items:
                promo_id = "_ANON_" + re.sub(r"[^A-Z0-9]", "_", label.upper())
                self.items[-1]["discounts"].append(
                    {
                        "type": "promotion",
                        "promotion_id": promo_id,
                        "amount_cents": int(round(amount * 100)),
                        "label": label,
                    }
                )
        else:
            item = {
                "name": label,
                "qty": 1.0,
                "unitPrice": amount,
                "lineTotal": amount,
                "discounts": [],
            }
            if tax_marker is not None:
                item["vatRate"] = _VAT_TYPE_MAP[tax_marker]
            self.items.append(item)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # While inside a discount span, count nested tags so we know when it ends.
        if self._cur_discount is not None:
            if tag == "span":
                self._discount_depth += 1
            return

        if tag != "span":
            return
        d = dict(attrs)
        span_id = d.get("id") or ""
        span_class = d.get("class") or ""
        if not span_id.startswith("purchase_list_line_"):
            return

        if "article" in span_class:
            self._finalize_anon()
            if span_id in self._seen:
                return
            desc = d.get("data-art-description")
            if not desc:
                return
            self._seen.add(span_id)
            try:
                unit_price = float((d.get("data-unit-price") or "0").replace(",", "."))
                qty = float((d.get("data-art-quantity") or "1").replace(",", "."))
            except ValueError:
                return
            previous_item = self.items[-1] if self.items else None
            if (
                previous_item is not None
                and previous_item.get("name") == desc
                and previous_item.get("qty") == qty
                and previous_item.get("unitPrice") == unit_price
                and not float(qty).is_integer()
            ):
                return
            item: dict[str, Any] = {
                "name": desc,
                "qty": qty,
                "unitPrice": unit_price,
                "lineTotal": round(unit_price * qty, 2),
                "discounts": [],
            }
            vat_key = (d.get("data-tax-type") or "").upper()
            if vat_key in _VAT_TYPE_MAP:
                item["vatRate"] = _VAT_TYPE_MAP[vat_key]
            self.items.append(item)

        elif "discount" in span_class and self.items:
            self._finalize_anon()
            promotion_id = d.get("data-promotion-id") or ""
            self._cur_discount = {
                "type": _classify_discount(promotion_id),
                "promotion_id": promotion_id,
            }
            self._discount_text = []
            self._discount_depth = 1

        else:
            # Anonymous receipt line (Pfandrückgabe, Aktionsrabatt, etc.)
            if self._cur_anon_id != span_id:
                self._finalize_anon()
                self._cur_anon_id = span_id

    def handle_endtag(self, tag: str) -> None:
        if self._cur_discount is not None and tag == "span":
            self._discount_depth -= 1
            if self._discount_depth == 0:
                text = " ".join(self._discount_text).strip()
                self.items[-1]["discounts"].append(
                    {
                        "type": self._cur_discount["type"],
                        "promotion_id": self._cur_discount["promotion_id"],
                        "amount_cents": _parse_discount_amount(text),
                        "label": text,
                    }
                )
                self._cur_discount = None
                self._discount_text = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if not stripped:
            return
        if self._cur_discount is not None:
            self._discount_text.append(stripped)
        elif self._cur_anon_id is not None:
            self._anon_texts.append(stripped)


def _merge_item_discounts(discounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge sibling discount spans that share the same promotion_id.

    Lidl's HTML represents a single logical discount as several sibling spans:
    one or more whitespace/structural spans, a label span ("Lidl Plus Rabatt"),
    and an amount span ("-0,65"). All share the same id and promotion_id.
    This function collapses them into one entry per promotion_id.
    """
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for d in discounts:
        pid = d["promotion_id"]
        if pid in seen:
            prev = seen[pid]
            parts = [prev["label"], d["label"]]
            prev["label"] = " ".join(p for p in parts if p).strip()
            if d["amount_cents"] < prev["amount_cents"]:
                prev["amount_cents"] = d["amount_cents"]
        else:
            entry = dict(d)
            seen[pid] = entry
            order.append(pid)
    # Drop entries that have no label and no amount (pure structural whitespace spans)
    return [seen[pid] for pid in order if seen[pid]["label"] or seen[pid]["amount_cents"] != 0]


def _parse_mre_html_items(html: str) -> list[dict[str, Any]]:
    parser = _MreReceiptParser()
    parser.feed(html)
    parser._finalize_anon()  # flush any trailing anonymous line
    for item in parser.items:
        item["discounts"] = _merge_item_discounts(item["discounts"])
    return parser.items


class MreApiClient:
    """
    Client for www.lidl.de/mre/api/v1 (the web receipt viewer API).

    Auth: LidlPlusNativeClient Bearer token, auto-refreshed from stored refresh_token.
    List: paginated at server page size (~10/page), page_token = page number string.
    Detail: full receipt with HTML-embedded line items parsed via data-* attributes.
    Note: totalAmount is always 0 in the detail response; it is intentionally omitted
    so that normalize_receipt() can pick it up from the list summary instead.
    """

    _MRE_BASE = "https://www.lidl.de/mre/api/v1"
    _AUTH_URL = "https://accounts.lidl.com/connect/token"
    _CLIENT_ID = "LidlPlusNativeClient"

    # Proactively refresh this many seconds before expiry
    _EXPIRY_BUFFER_S = 300  # 5 minutes

    def __init__(
        self,
        refresh_token: str,
        config: AppConfig,
        token_store: TokenStore | None = None,
    ) -> None:
        self._refresh_token = refresh_token
        self._config = config
        self._token_store = token_store
        source_suffix = config.source.rsplit("_", 1)[-1]  # "lidl_plus_de" -> "de"
        self._country = source_suffix.upper()
        self._language = source_suffix.lower()
        self._rate_limiter = RateLimiter(config.max_requests_per_second)
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        _validate_endpoint_security(config, self._MRE_BASE, endpoint_name="Lidl MRE API base URL")
        _validate_endpoint_security(config, self._AUTH_URL, endpoint_name="Lidl auth endpoint URL")
        self._http = httpx.Client(
            timeout=config.request_timeout_s,
            verify=not config.allow_insecure_tls_verify,
        )
        self._load_cached_token()

    def _load_cached_token(self) -> None:
        """Seed in-memory state from the persisted access-token cache."""
        if self._token_store is None:
            return
        cached = self._token_store.get_access_cache()
        if cached is None:
            return
        token, expires_at = cached
        if self._is_token_fresh(expires_at):
            self._access_token = token
            self._token_expires_at = expires_at
            LOGGER.debug("Loaded cached access token (expires %s)", expires_at.isoformat())

    def _is_token_fresh(self, expires_at: datetime) -> bool:
        cutoff = datetime.now(UTC) + timedelta(seconds=self._EXPIRY_BUFFER_S)
        return expires_at > cutoff

    def _ensure_token(self) -> str:
        if (
            self._access_token
            and self._token_expires_at
            and self._is_token_fresh(self._token_expires_at)
        ):
            return self._access_token
        return self._do_refresh()

    def _do_refresh(self) -> str:
        """Exchange refresh_token for a new access_token and persist the result."""
        secret = base64.b64encode(f"{self._CLIENT_ID}:secret".encode()).decode()
        resp = self._http.post(
            self._AUTH_URL,
            headers={
                "Authorization": f"Basic {secret}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            content=f"grant_type=refresh_token&refresh_token={self._refresh_token}".encode(),
        )
        if resp.status_code in {401, 403}:
            LOGGER.error("Refresh token rejected (HTTP %s) — re-auth required", resp.status_code)
            if self._token_store is not None:
                self._token_store.set_reauth_required()
            raise LidlReauthRequiredError(
                "Refresh token rejected. Run 'lidltool auth bootstrap' to re-authenticate."
            )
        resp.raise_for_status()
        payload = resp.json()
        access_token = str(payload["access_token"])
        expires_in = float(payload.get("expires_in", 3600))
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        self._access_token = access_token
        self._token_expires_at = expires_at
        if self._token_store is not None:
            self._token_store.set_access_cache(access_token, expires_at)
            new_refresh = payload.get("refresh_token")
            if isinstance(new_refresh, str) and new_refresh:
                self._refresh_token = new_refresh
                self._token_store.set_refresh_token(new_refresh)
                LOGGER.debug("Refresh token rotated and persisted")
        LOGGER.debug("Access token refreshed, expires at %s", expires_at.isoformat())
        return access_token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._ensure_token()}", "Accept": "application/json"}

    def _request(self, method: str, url: str, params: dict[str, Any] | None = None) -> Any:
        attempts = max(1, self._config.retry_attempts)
        base_delay = max(0.1, self._config.retry_base_delay_s)
        last_error: Exception | None = None
        auth_retried = False  # allow exactly one force-refresh on 401/403
        attempt = 0
        while attempt < attempts:
            attempt += 1
            self._rate_limiter.wait()
            try:
                resp = self._http.request(method, url, params=params, headers=self._headers())
                if resp.status_code in {401, 403}:
                    if not auth_retried:
                        LOGGER.warning(
                            "Bearer token rejected (HTTP %s); force-refreshing and retrying",
                            resp.status_code,
                        )
                        auth_retried = True
                        self._access_token = None  # force _ensure_token to call _do_refresh
                        attempt -= 1  # don't count this against retry budget
                        continue
                    raise LidlAuthError("Bearer token rejected even after force-refresh")
                if resp.status_code in {429, 500, 502, 503, 504}:
                    raise LidlClientError(f"transient status {resp.status_code}")
                resp.raise_for_status()
                return resp.json()
            except LidlAuthError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == attempts:
                    break
                sleep_s = base_delay * (2 ** (attempt - 1))
                LOGGER.warning("MRE API transient error, retrying in %.2fs: %s", sleep_s, exc)
                time.sleep(sleep_s)
        raise LidlClientError(f"MRE API request failed: {last_error}")

    def list_receipts(self, page_token: str | None = None, page_size: int = 50) -> ReceiptPage:
        page_num = int(page_token) if page_token else 1
        data = self._request(
            "GET",
            f"{self._MRE_BASE}/tickets",
            params={"country": self._country, "page": page_num},
        )
        total = int(data.get("totalCount", 0))
        server_size = int(data.get("size", 10))
        receipts: list[dict[str, Any]] = [
            {
                "id": item["id"],
                "purchasedAt": item.get("date"),
                "totalAmount": _format_ticket_total_amount(item.get("totalAmount")),
                "storeName": item.get("store"),
                "articlesCount": item.get("articlesCount"),
            }
            for item in data.get("items", [])
        ]
        next_token = str(page_num + 1) if page_num * server_size < total else None
        return ReceiptPage(receipts=receipts, next_page_token=next_token)

    def get_receipt(self, receipt_id: str) -> dict[str, Any]:
        data = self._request(
            "GET",
            f"{self._MRE_BASE}/tickets/{receipt_id}",
            params={
                "country": self._country,
                "languageCode": f"{self._language}-{self._country}",
            },
        )
        ticket = data.get("ticket") or {}
        store = ticket.get("store") or {}
        address = " ".join(
            filter(None, [store.get("address"), store.get("postalCode"), store.get("locality")])
        )
        html = ticket.get("htmlPrintedReceipt") or ""
        # Intentionally omit totalAmount: the detail endpoint always returns 0.
        # normalize_receipt() will pick up totalAmount from the list summary via setdefault.
        return {
            "id": ticket.get("id") or receipt_id,
            "purchasedAt": ticket.get("date"),
            "store": store,
            "storeId": store.get("id"),
            "storeName": store.get("name"),
            "storeAddress": address or None,
            "currency": "EUR",
            "receiptHtmlAvailable": bool(str(html).strip()),
            "items": _parse_mre_html_items(html),
        }


# ---------------------------------------------------------------------------
# lidl-plus library client (fallback)
# ---------------------------------------------------------------------------


class LidlPlusLibraryClient:
    def __init__(self, refresh_token: str, config: AppConfig) -> None:
        self._refresh_token = refresh_token
        self._config = config
        self._rate_limiter = RateLimiter(config.max_requests_per_second)
        self._api = self._create_lidlplus_api(refresh_token)
        self._ticket_cache: list[dict[str, Any]] | None = None

    def _create_lidlplus_api(self, refresh_token: str) -> Any:
        try:
            module = importlib.import_module("lidlplus")
        except ImportError as exc:
            raise LidlClientError("lidl-plus package is not installed") from exc

        api_cls = getattr(module, "LidlPlusApi", None)
        if api_cls is None:
            raise LidlClientError("lidlplus.LidlPlusApi not found")

        # Inspect constructor to handle different lidl-plus versions.
        # v0.3.x shape: LidlPlusApi(language, country, refresh_token="")
        try:
            sig = inspect.signature(api_cls.__init__)
            param_names = [p for p in sig.parameters if p != "self"]
        except (ValueError, TypeError):
            param_names = []

        if "language" in param_names and "country" in param_names:
            source_suffix = self._config.source.rsplit("_", 1)[-1]
            language = source_suffix.lower()
            country = source_suffix.upper()
            return api_cls(language, country, refresh_token)

        candidate_kwargs = [
            {"refresh_token": refresh_token},
            {"token": refresh_token},
            {"refreshToken": refresh_token},
        ]
        for kwargs in candidate_kwargs:
            try:
                return api_cls(**kwargs)
            except TypeError:
                continue

        api = api_cls()
        if hasattr(api, "set_refresh_token") and callable(api.set_refresh_token):
            api.set_refresh_token(refresh_token)
            return api
        if hasattr(api, "refresh_token"):
            api.refresh_token = refresh_token
            return api
        raise LidlClientError("Unable to initialize lidl-plus API with provided refresh token")

    def _call_with_retry(self, fn: Callable[[], T]) -> T:
        attempts = max(1, self._config.retry_attempts)
        delay = max(0.1, self._config.retry_base_delay_s)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            self._rate_limiter.wait()
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if not self._is_transient_error(exc) or attempt == attempts:
                    break
                sleep_seconds = delay * (2 ** (attempt - 1))
                LOGGER.warning("Transient Lidl API error, retrying in %.2fs", sleep_seconds)
                time.sleep(sleep_seconds)

        raise LidlClientError(f"Lidl API call failed: {last_error}")

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError)):
            return True
        message = str(exc).lower()
        transient_fragments = ["timeout", "tempor", "rate limit", "429", "502", "503", "504"]
        return any(fragment in message for fragment in transient_fragments)

    @staticmethod
    def _coerce_dict(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if hasattr(payload, "model_dump") and callable(payload.model_dump):
            return cast(dict[str, Any], payload.model_dump())
        if hasattr(payload, "dict") and callable(payload.dict):
            return cast(dict[str, Any], payload.dict())
        return {"value": payload}

    def _load_all_receipts(self) -> list[dict[str, Any]]:
        # lidl-plus hardcodes _TIMEOUT = 10; override with our config value
        if hasattr(self._api, "_TIMEOUT"):
            self._api._TIMEOUT = int(self._config.request_timeout_s)

        method_names = ["tickets", "get_tickets", "receipts", "get_receipts"]
        method: Callable[..., Any] | None = None
        for name in method_names:
            candidate = getattr(self._api, name, None)
            if callable(candidate):
                method = candidate
                break
        if method is None:
            raise LidlClientError("No ticket listing method found in lidl-plus API object")

        payload = self._call_with_retry(lambda: method())

        if isinstance(payload, dict):
            for key in ("tickets", "receipts", "items", "results", "data"):
                maybe_list = payload.get(key)
                if isinstance(maybe_list, list):
                    return [self._coerce_dict(item) for item in maybe_list]
            return [self._coerce_dict(payload)]

        if isinstance(payload, list):
            return [self._coerce_dict(item) for item in payload]

        if isinstance(payload, tuple):
            return [self._coerce_dict(item) for item in payload]

        try:
            iterable = list(payload)
            return [self._coerce_dict(item) for item in iterable]
        except TypeError:
            return [self._coerce_dict(payload)]

    def list_receipts(self, page_token: str | None = None, page_size: int = 50) -> ReceiptPage:
        if self._ticket_cache is None:
            self._ticket_cache = self._load_all_receipts()

        start = int(page_token) if page_token else 0
        end = start + page_size
        chunk = self._ticket_cache[start:end]
        next_token = str(end) if end < len(self._ticket_cache) else None
        return ReceiptPage(receipts=chunk, next_page_token=next_token)

    def get_receipt(self, receipt_id: str) -> dict[str, Any]:
        method_names = ["ticket", "get_ticket", "receipt", "get_receipt"]
        method: Callable[..., Any] | None = None
        for name in method_names:
            candidate = getattr(self._api, name, None)
            if callable(candidate):
                method = candidate
                break
        if method is None:
            raise LidlClientError("No ticket detail method found in lidl-plus API object")

        payload = self._call_with_retry(lambda: method(receipt_id))
        return self._coerce_dict(payload)


# ---------------------------------------------------------------------------
# Direct httpx client (fallback for custom API_BASE_URL)
# ---------------------------------------------------------------------------


class HttpxLidlClient:
    def __init__(self, refresh_token: str, config: AppConfig) -> None:
        if not config.api_base_url:
            raise LidlClientError("LIDLTOOL_API_BASE_URL is required for httpx backend")
        _validate_endpoint_security(config, config.api_base_url, endpoint_name="Lidl API base URL")
        self._config = config
        self._refresh_token = refresh_token
        self._rate_limiter = RateLimiter(config.max_requests_per_second)
        self._client = httpx.Client(
            base_url=config.api_base_url,
            timeout=config.request_timeout_s,
            verify=not config.allow_insecure_tls_verify,
            headers={
                "Authorization": f"Bearer {refresh_token}",
                "Accept": "application/json",
                "User-Agent": "lidltool/0.1.0",
            },
        )

    def _request_with_retry(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        attempts = max(1, self._config.retry_attempts)
        base_delay = max(0.1, self._config.retry_base_delay_s)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            self._rate_limiter.wait()
            try:
                response = self._client.request(method, path, params=params)
                if response.status_code in {401, 403}:
                    raise LidlAuthError("Authentication failed; refresh token may be expired")
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise LidlClientError(f"transient status code {response.status_code}")
                response.raise_for_status()
                return response.json()
            except LidlAuthError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == attempts:
                    break
                sleep_seconds = base_delay * (2 ** (attempt - 1))
                time.sleep(sleep_seconds)

        raise LidlClientError(f"HTTP client failed after retries: {last_error}")

    def list_receipts(self, page_token: str | None = None, page_size: int = 50) -> ReceiptPage:
        params: dict[str, Any] = {"limit": page_size}
        if page_token:
            params["page_token"] = page_token

        payload = self._request_with_retry("GET", "/receipts", params=params)
        receipts = payload.get("receipts") or payload.get("items") or payload.get("results") or []
        next_token = payload.get("next_page_token") or payload.get("next")
        return ReceiptPage(
            receipts=[self._coerce_dict(r) for r in receipts], next_page_token=next_token
        )

    def get_receipt(self, receipt_id: str) -> dict[str, Any]:
        payload = self._request_with_retry("GET", f"/receipts/{receipt_id}")
        if isinstance(payload, dict):
            detail = payload.get("receipt") or payload.get("data") or payload
            return self._coerce_dict(detail)
        return self._coerce_dict(payload)

    @staticmethod
    def _coerce_dict(payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        return {"value": payload}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_lidl_client(
    config: AppConfig,
    refresh_token: str,
    token_store: TokenStore | None = None,
) -> LidlClient:
    # MreApiClient is the primary: uses www.lidl.de/mre/api/v1 with Bearer token.
    # The old tickets.lidlplus.com endpoint is unreachable; this one works.
    try:
        return MreApiClient(refresh_token=refresh_token, config=config, token_store=token_store)
    except LidlClientError as exc:
        LOGGER.warning("MreApiClient init failed (%s); trying fallbacks", exc)

    if config.use_lidl_plus:
        try:
            return LidlPlusLibraryClient(refresh_token=refresh_token, config=config)
        except LidlClientError:
            if not config.api_base_url:
                raise
            LOGGER.warning("Falling back to httpx client because lidl-plus backend failed")

    if config.api_base_url:
        return HttpxLidlClient(refresh_token=refresh_token, config=config)

    raise LidlClientError("No viable Lidl API client could be initialized")
