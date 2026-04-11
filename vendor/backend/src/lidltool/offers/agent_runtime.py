from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from lidltool.ai.codex_oauth import complete_text_with_codex_oauth
from lidltool.ai.config import get_ai_oauth_access_token
from lidltool.ai.runtime import (
    ChatCompletionRequest,
    RuntimeMessage,
    RuntimePolicyMode,
    RuntimeTask,
    resolve_runtime_client,
)
from lidltool.config import AppConfig
from lidltool.connectors.sdk.offer import NormalizedOfferRecord
from lidltool.db.models import OfferSourceConfig
from lidltool.offers.browser_runtime import BrowserOfferPageCapture, capture_offer_page_with_browser

_DEFAULT_MODEL = "gpt-5.2-codex"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def discover_offers_from_source(
    *,
    config: AppConfig,
    source: OfferSourceConfig,
    discovery_limit: int | None = None,
) -> list[NormalizedOfferRecord]:
    capture = _capture_offer_page(config=config, source=source)
    blocked_reason = _browser_capture_blocked_reason(capture)
    if blocked_reason is not None:
        raise RuntimeError(blocked_reason)
    snapshot = _build_page_snapshot(
        source_url=capture.final_url or source.merchant_url,
        html=capture.html,
        browser_notes=capture.notes,
        response_captures=capture.responses,
    )
    payload = _extract_offers_with_ai(
        config=config,
        source=source,
        snapshot=snapshot,
        html=capture.html,
        capture=capture,
        discovery_limit=discovery_limit,
    )
    fetched_at = datetime.now(tz=UTC)
    offers: list[NormalizedOfferRecord] = []
    for raw_offer in payload.get("offers", []):
        if not isinstance(raw_offer, dict):
            continue
        normalized = _normalized_offer_from_payload(
            source=source,
            raw_offer=raw_offer,
            fetched_at=fetched_at,
        )
        if normalized is not None:
            offers.append(normalized)
    return offers


def _capture_offer_page(*, config: AppConfig, source: OfferSourceConfig) -> BrowserOfferPageCapture:
    if not config.offers_browser_enabled:
        fallback_html = _fetch_source_html(source.merchant_url)
        return BrowserOfferPageCapture(
            source_url=source.merchant_url,
            final_url=source.merchant_url,
            page_title=None,
            html=fallback_html,
            notes=["Browser capture disabled by configuration; used direct HTTP fetch."],
            responses=[],
        )
    try:
        return capture_offer_page_with_browser(config=config, source=source)
    except Exception as browser_exc:  # noqa: BLE001
        try:
            fallback_html = _fetch_source_html(source.merchant_url)
        except Exception as http_exc:  # noqa: BLE001
            raise RuntimeError(
                f"browser capture failed for {source.merchant_url}: {browser_exc}; "
                f"direct HTTP fallback also failed: {http_exc}"
            ) from http_exc
        return BrowserOfferPageCapture(
            source_url=source.merchant_url,
            final_url=source.merchant_url,
            page_title=None,
            html=fallback_html,
            notes=[f"Browser capture failed, fell back to direct HTTP fetch: {browser_exc}"],
            responses=[],
        )


def _browser_capture_blocked_reason(capture: BrowserOfferPageCapture) -> str | None:
    for note in capture.notes:
        normalized = note.strip()
        lowered = normalized.lower()
        if "http 4" in lowered and "document response returned" in lowered:
            return normalized
        if any(
            marker in lowered
            for marker in (
                "anti-bot challenge",
                "access denied",
                "forbidden",
                "captcha",
                "security check",
                "unusual traffic",
            )
        ):
            return normalized
    return None


def _fetch_source_html(url: str) -> str:
    response = httpx.get(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        },
        follow_redirects=True,
        timeout=30.0,
    )
    response.raise_for_status()
    return response.text


def _build_page_snapshot(
    *,
    source_url: str,
    html: str,
    browser_notes: list[str] | None = None,
    response_captures: list[Any] | None = None,
) -> str:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    description = ""
    description_tag = soup.find("meta", attrs={"name": "description"})
    if description_tag is not None:
        description = str(description_tag.get("content") or "").strip()

    for tag_name in ("script", "style", "noscript"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    headings = [
        node.get_text(" ", strip=True)
        for node in soup.find_all(["h1", "h2", "h3"])
        if node.get_text(" ", strip=True)
    ][:30]
    list_items = [
        node.get_text(" ", strip=True)
        for node in soup.find_all("li")
        if _looks_offer_like(node.get_text(" ", strip=True))
    ][:120]
    table_rows: list[str] = []
    for row in soup.find_all("tr")[:80]:
        text = " | ".join(cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"]))
        if _looks_offer_like(text):
            table_rows.append(text)

    links: list[str] = []
    for link in soup.find_all("a", href=True)[:200]:
        text = link.get_text(" ", strip=True)
        href = str(link.get("href") or "").strip()
        if not text or not href:
            continue
        if not _looks_offer_like(f"{text} {href}"):
            continue
        links.append(f"{text} -> {urljoin(source_url, href)}")
        if len(links) >= 80:
            break

    json_ld_blocks = [
        script.get_text(" ", strip=True)
        for script in soup.find_all("script", attrs={"type": "application/ld+json"})
        if script.get_text(" ", strip=True)
    ][:10]

    text_chunks: list[str] = []
    for node in soup.find_all(["p", "div", "span"])[:600]:
        text = node.get_text(" ", strip=True)
        if _looks_offer_like(text):
            text_chunks.append(text)
        if len(text_chunks) >= 160:
            break

    sections = [
        f"URL: {source_url}",
        f"PAGE TITLE: {title}" if title else "",
        f"META DESCRIPTION: {description}" if description else "",
        "BROWSER NOTES:",
        "\n".join(f"- {value}" for value in (browser_notes or [])) if browser_notes else "- none",
        "HEADINGS:",
        "\n".join(f"- {value}" for value in headings) if headings else "- none",
        "LIST ITEMS:",
        "\n".join(f"- {value}" for value in list_items) if list_items else "- none",
        "TABLE ROWS:",
        "\n".join(f"- {value}" for value in table_rows) if table_rows else "- none",
        "LINKS:",
        "\n".join(f"- {value}" for value in links) if links else "- none",
        "JSON-LD:",
        "\n".join(json_ld_blocks) if json_ld_blocks else "none",
        "CAPTURED API RESPONSES:",
        _format_captured_responses(response_captures),
        "VISIBLE OFFER-LIKE TEXT:",
        "\n".join(f"- {value}" for value in text_chunks) if text_chunks else "- none",
    ]
    return "\n".join(section for section in sections if section).strip()[:90000]


def _looks_offer_like(text: str) -> bool:
    normalized = " ".join(text.split())
    if not normalized:
        return False
    lowered = normalized.lower()
    keywords = (
        "%",
        "€",
        "eur",
        "angebot",
        "angebote",
        "rabatt",
        "sparen",
        "gültig",
        "kw",
        "statt",
        "coupon",
        "sale",
    )
    return any(keyword in lowered for keyword in keywords)


def _extract_offers_with_ai(
    *,
    config: AppConfig,
    source: OfferSourceConfig,
    snapshot: str,
    html: str,
    capture: BrowserOfferPageCapture,
    discovery_limit: int | None,
) -> dict[str, Any]:
    now = datetime.now().astimezone()
    limit = min(max(discovery_limit or 25, 1), 50)
    prompt = (
        "Extract concrete retail offers from the provided merchant offer page.\n"
        f"Merchant name: {source.merchant_name}\n"
        f"Source URL: {source.merchant_url}\n"
        f"Final browser URL: {capture.final_url}\n"
        f"Country code: {source.country_code}\n"
        f"Current local date: {now.date().isoformat()}\n"
        "Return JSON only with shape:\n"
        "{"
        '"offers":[{'
        '"title":"string",'
        '"summary":"string|null",'
        '"offer_type":"sale|bundle|multibuy|coupon|loyalty|markdown|unknown",'
        '"validity_start":"ISO-8601 datetime or null",'
        '"validity_end":"ISO-8601 datetime or null",'
        '"currency":"EUR",'
        '"price_cents":"integer or null",'
        '"original_price_cents":"integer or null",'
        '"discount_percent":"number or null",'
        '"offer_url":"absolute url or null",'
        '"image_url":"absolute url or null",'
        '"item_title":"string or null",'
        '"alias_candidates":["string"],'
        '"quantity_text":"string or null",'
        '"unit":"string or null",'
        '"size_text":"string or null",'
        '"evidence":"short source quote or summary"'
        "}],"
        '"notes":["string"]'
        "}\n"
        f"Rules:\n"
        f"- Include at most {limit} offers.\n"
        "- Use only offers explicitly present in the page content.\n"
        "- Ignore navigation, category links, and generic marketing copy.\n"
        "- If dates are missing, leave validity_start or validity_end null.\n"
        "- If a price or discount is missing, keep it null.\n"
        "- Resolve relative URLs against the source URL.\n"
        "- Prefer one item per offer unless the page clearly bundles multiple products.\n"
        "- Prefer concrete API payloads and rendered browser content over generic marketing copy.\n"
        "- If the page is blocked, empty, or lacks concrete offers, return an empty offers list and explain why in notes.\n\n"
        "PAGE SNAPSHOT:\n"
        f"{snapshot}\n\n"
        "RENDERED HTML EXCERPT:\n"
        f"{html[:30000]}"
    )
    text = _complete_offer_extraction_prompt(config=config, prompt=prompt)
    data = _parse_json_response(text)
    if not isinstance(data, dict):
        raise RuntimeError("offer extraction model returned invalid JSON")
    return data


def _complete_offer_extraction_prompt(*, config: AppConfig, prompt: str) -> str:
    oauth_provider = (config.ai_oauth_provider or "").strip().lower()
    bearer_token = (get_ai_oauth_access_token(config) or "").strip()
    if oauth_provider == "openai-codex" and bearer_token:
        return _complete_with_chatgpt_oauth(config=config, prompt=prompt)

    base_url = (config.ai_base_url or "").strip()
    if base_url:
        runtime = resolve_runtime_client(
            config,
            task=RuntimeTask.PI_AGENT,
            policy_mode=RuntimePolicyMode.REMOTE_ALLOWED,
        )
        if runtime is None or runtime.capabilities().local:
            raise RuntimeError("remote AI runtime is not configured for offer extraction")
        response = runtime.complete_chat(
            ChatCompletionRequest(
                task=RuntimeTask.PI_AGENT,
                model_name=runtime.model_name or (config.ai_model or _DEFAULT_MODEL),
                temperature=0,
                messages=[
                    RuntimeMessage(
                        role="system",
                        content=(
                            "You extract structured offers from merchant pages. "
                            "Return JSON only and do not add markdown fences."
                        ),
                    ),
                    RuntimeMessage(role="user", content=prompt),
                ],
            )
        )
        return response.text
    return _complete_with_chatgpt_oauth(config=config, prompt=prompt)


def _complete_with_chatgpt_oauth(*, config: AppConfig, prompt: str) -> str:
    bearer_token = (get_ai_oauth_access_token(config) or "").strip()
    if not bearer_token:
        raise RuntimeError("AI assistant credentials are required for offer extraction")
    response = complete_text_with_codex_oauth(
        bearer_token=bearer_token,
        model=(config.ai_model or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL,
        instructions=(
            "You extract structured offers from merchant pages. "
            "Return JSON only and do not add markdown fences."
        ),
        input_items=[{"role": "user", "content": prompt}],
        timeout_s=120.0,
    )
    return response.text


def _parse_json_response(text: str) -> Any:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[1] if "\n" in candidate else candidate
        if candidate.endswith("```"):
            candidate = candidate[:-3]
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end >= start:
        candidate = candidate[start : end + 1]
    return json.loads(candidate)


def _format_captured_responses(response_captures: list[Any] | None) -> str:
    if not response_captures:
        return "none"
    chunks: list[str] = []
    for response in response_captures[:12]:
        url = _optional_text(
            getattr(response, "url", None) if not isinstance(response, dict) else response.get("url")
        )
        status = getattr(response, "status", None) if not isinstance(response, dict) else response.get("status")
        content_type = _optional_text(
            getattr(response, "content_type", None)
            if not isinstance(response, dict)
            else response.get("content_type")
        )
        resource_type = _optional_text(
            getattr(response, "resource_type", None)
            if not isinstance(response, dict)
            else response.get("resource_type")
        )
        body_excerpt = _optional_text(
            getattr(response, "body_excerpt", None)
            if not isinstance(response, dict)
            else response.get("body_excerpt")
        )
        if not body_excerpt:
            continue
        chunks.append(
            "\n".join(
                [
                    f"URL: {url or 'unknown'}",
                    f"STATUS: {status if status is not None else 'unknown'}",
                    f"RESOURCE TYPE: {resource_type or 'unknown'}",
                    f"CONTENT TYPE: {content_type or 'unknown'}",
                    "BODY:",
                    body_excerpt,
                ]
            )
        )
    return "\n\n".join(chunks) if chunks else "none"


def _normalized_offer_from_payload(
    *,
    source: OfferSourceConfig,
    raw_offer: dict[str, Any],
    fetched_at: datetime,
) -> NormalizedOfferRecord | None:
    title = str(raw_offer.get("title") or raw_offer.get("item_title") or "").strip()
    if not title:
        return None

    price_cents = _coerce_int(raw_offer.get("price_cents"))
    original_price_cents = _coerce_int(raw_offer.get("original_price_cents"))
    discount_percent = _coerce_float(raw_offer.get("discount_percent"))
    if price_cents is None and original_price_cents is None and discount_percent is None:
        return None

    validity_start = _coerce_datetime(raw_offer.get("validity_start")) or fetched_at
    validity_end = _coerce_datetime(raw_offer.get("validity_end")) or (
        validity_start + timedelta(days=7)
    )
    if validity_end < validity_start:
        validity_end = validity_start + timedelta(days=7)

    offer_url = _coerce_url(source.merchant_url, raw_offer.get("offer_url"))
    image_url = _coerce_url(source.merchant_url, raw_offer.get("image_url"))
    item_title = str(raw_offer.get("item_title") or title).strip()
    alias_candidates = raw_offer.get("alias_candidates")
    if not isinstance(alias_candidates, list):
        alias_candidates = []
    alias_candidates = [str(item).strip() for item in alias_candidates if str(item).strip()]

    stable_key = "|".join(
        [
            source.source_id,
            title,
            offer_url or "",
            validity_start.astimezone(UTC).isoformat(),
            validity_end.astimezone(UTC).isoformat(),
            str(price_cents or ""),
            str(original_price_cents or ""),
        ]
    )
    source_offer_id = sha256(stable_key.encode("utf-8")).hexdigest()[:24]
    fingerprint = sha256(f"{source.source_id}|{source_offer_id}".encode("utf-8")).hexdigest()

    evidence = str(raw_offer.get("evidence") or "").strip()
    return NormalizedOfferRecord.model_validate(
        {
            "source_offer_id": source_offer_id,
            "fingerprint": fingerprint,
            "merchant_name": source.merchant_name,
            "merchant_id": source.source_id,
            "title": title,
            "summary": _optional_text(raw_offer.get("summary")),
            "offer_type": _optional_text(raw_offer.get("offer_type")) or "unknown",
            "validity_start": validity_start.astimezone(UTC).isoformat(),
            "validity_end": validity_end.astimezone(UTC).isoformat(),
            "currency": _optional_text(raw_offer.get("currency")) or "EUR",
            "price_cents": price_cents,
            "original_price_cents": original_price_cents,
            "discount_percent": discount_percent,
            "offer_url": offer_url,
            "image_url": image_url,
            "scope": {
                "country_code": source.country_code,
                "store_name": source.display_name,
            },
            "items": [
                {
                    "line_no": 1,
                    "title": item_title,
                    "alias_candidates": alias_candidates,
                    "quantity_text": _optional_text(raw_offer.get("quantity_text")),
                    "unit": _optional_text(raw_offer.get("unit")),
                    "size_text": _optional_text(raw_offer.get("size_text")),
                    "price_cents": price_cents,
                    "original_price_cents": original_price_cents,
                    "discount_percent": discount_percent,
                    "raw_payload": {"evidence": evidence} if evidence else {},
                }
            ],
            "raw_payload": {
                "source_kind": "agent_url",
                "merchant_url": source.merchant_url,
                "extracted_offer": raw_offer,
            },
            "metadata": {
                "source_config_id": source.id,
                "source_kind": "agent_url",
                "validity_inferred": raw_offer.get("validity_start") is None
                or raw_offer.get("validity_end") is None,
            },
        }
    )


def _coerce_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        normalized = value.strip().replace("€", "").replace("EUR", "").replace(",", ".")
        try:
            if "." in normalized:
                return int(round(float(normalized)))
            return int(normalized)
        except ValueError:
            return None
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().replace("%", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _coerce_url(base_url: str, value: Any) -> str | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    return urljoin(base_url, normalized)
