#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "vendor" / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from lidltool.amazon.client_playwright import (  # noqa: E402
    AmazonClientError,
    AmazonPlaywrightClient,
    AmazonReauthRequiredError,
)
from lidltool.amazon.parsers import parse_order_detail_html  # noqa: E402
from lidltool.amazon.session import default_amazon_profile_dir, default_amazon_state_file  # noqa: E402
from lidltool.config import AppConfig  # noqa: E402


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _details_url_kind(url: str) -> str:
    lowered = url.lower()
    if "/your-orders/invoice/popover" in lowered:
        return "invoice_popover"
    if "/documents/download/" in lowered and "invoice.pdf" in lowered:
        return "invoice_pdf"
    if "order-details" in lowered or "/your-orders/order-details" in lowered or "/gp/css/order-details" in lowered:
        return "order_detail"
    if "orderid=" in lowered:
        return "orderid_link"
    return "other"


def _is_invoice_like_url(url: str) -> bool:
    return _details_url_kind(url) in {"invoice_popover", "invoice_pdf"}


def _write_html(path: Path, html: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return str(path)


def _parse_amount(text: str) -> tuple[float | None, str | None]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return None, None
    currency = "EUR" if "€" in cleaned else None
    match = re.search(r"(-?\d[\d\.\s]*,\d{2}|-?\d+(?:,\d{2})?)", cleaned)
    if match is None:
        return None, currency
    amount_text = match.group(1).replace(".", "").replace(" ", "").replace(",", ".")
    try:
        return float(amount_text), currency
    except ValueError:
        return None, currency


def _extract_order_id_from_url(url: str) -> str | None:
    match = re.search(r"([A-Z0-9]{3}-\d{7}-\d{7})", url or "", re.IGNORECASE)
    return match.group(1) if match else None


def _extract_order_cards(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
() => {
  const normalize = (value) => (value || "").replace(/\\s+/g, " ").trim();
  const absoluteUrl = (href) => {
    try {
      return new URL(href || "", window.location.href).toString();
    } catch {
      return href || "";
    }
  };
  const headerValue = (card, labelNeedle) => {
    const items = Array.from(card.querySelectorAll(".order-header__header-list-item"));
    for (const item of items) {
      const label = normalize(item.querySelector(".a-text-caps")?.textContent || "").toLowerCase();
      if (!label.includes(labelNeedle)) {
        continue;
      }
      const rows = Array.from(item.querySelectorAll(".a-row"))
        .map((row) => normalize(row.textContent))
        .filter(Boolean);
      if (rows.length >= 2) {
        return rows[rows.length - 1];
      }
      return normalize(item.textContent);
    }
    return "";
  };
  const cards = Array.from(document.querySelectorAll(".order-card.js-order-card, .order-card, .js-order-card"));
  const orderCards = cards.map((card, index) => {
    const linkCandidates = Array.from(card.querySelectorAll("a[href]")).map((link) => ({
      href: link.getAttribute("href") || "",
      absolute_url: absoluteUrl(link.getAttribute("href") || ""),
      text: normalize(link.textContent),
    }));
    const detailsLink = linkCandidates.find((link) => /\\/(your-orders|gp\\/css)\\/order-details/i.test(link.absolute_url));
    return {
      index,
      orderId: normalize(card.querySelector(".yohtmlc-order-id span[dir='ltr']")?.textContent || ""),
      orderDate: headerValue(card, "bestellung aufgegeben"),
      totalText: headerValue(card, "gesamt"),
      orderStatus: normalize(card.querySelector(".delivery-box__primary-text, .yohtmlc-shipment-status-primaryText")?.textContent || ""),
      detailsUrl: detailsLink ? detailsLink.absolute_url : "",
      listItemCount: card.querySelectorAll(".item-box").length,
      linkCandidates,
      rawText: normalize(card.textContent),
    };
  });
  const nextLink =
    document.querySelector("ul.a-pagination li.a-last a") ||
    document.querySelector("a[aria-label*='Weiter']") ||
    document.querySelector("a[aria-label*='next']");
  return {
    orderCards,
    nextPageUrl: nextLink ? absoluteUrl(nextLink.getAttribute("href") || "") : "",
    finalUrl: window.location.href,
    title: document.title,
  };
}
"""
    )


@dataclass(slots=True)
class GroundTruthConfig:
    source_id: str
    years: int
    headless: bool
    auth_interaction_timeout_s: int
    page_delay_ms: int
    db_path: Path
    html_dir: Path
    state_file: Path
    profile_dir: Path | None


SCHEMA_SQL = """
create table if not exists crawl_run (
  run_id text primary key,
  source_id text not null,
  started_at text not null,
  finished_at text,
  status text not null,
  years_requested integer not null,
  browser_mode text not null,
  state_file text,
  profile_dir text,
  notes text,
  error text
);

create table if not exists history_page (
  page_id integer primary key autoincrement,
  run_id text not null,
  year integer not null,
  page_index integer not null,
  start_index integer not null,
  page_url text not null,
  final_url text not null,
  fetched_at text not null,
  html_path text,
  html_sha256 text,
  raw_order_count integer not null,
  parsed_order_count integer not null,
  has_next_page integer not null
);

create table if not exists order_ref (
  order_ref_id integer primary key autoincrement,
  run_id text not null,
  page_id integer not null,
  order_id text,
  order_date_text text,
  total_amount real,
  currency text,
  order_status_text text,
  details_url text,
  details_url_kind text,
  parse_status text,
  parse_warnings_json text,
  unsupported_reason text,
  list_item_count integer not null,
  raw_json text not null
);

create table if not exists order_link_candidate (
  candidate_id integer primary key autoincrement,
  run_id text not null,
  page_id integer not null,
  order_ref_id integer,
  href text not null,
  absolute_url text not null,
  link_text text,
  details_url_kind text not null,
  is_invoice_like integer not null
);

create table if not exists detail_fetch (
  fetch_id integer primary key autoincrement,
  run_id text not null,
  order_ref_id integer not null,
  fetch_method text not null,
  requested_url text not null,
  final_url text,
  fetched_at text not null,
  outcome text not null,
  html_path text,
  html_sha256 text,
  parse_status text,
  parse_warnings_json text,
  unsupported_reason text,
  order_date text,
  total_amount real,
  shipping real,
  gift_wrap real,
  item_count integer,
  promotion_count integer,
  raw_json text
);

create table if not exists invoice_anomaly (
  anomaly_id integer primary key autoincrement,
  run_id text not null,
  page_id integer,
  order_ref_id integer,
  fetch_id integer,
  anomaly_type text not null,
  url text not null,
  detail text,
  observed_at text not null
);
"""


def _create_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def _build_client(cfg: GroundTruthConfig) -> AmazonPlaywrightClient:
    return AmazonPlaywrightClient(
        state_file=cfg.state_file,
        profile_dir=cfg.profile_dir,
        source_id=cfg.source_id,
        headless=cfg.headless,
        dump_html_dir=cfg.html_dir / "client-dump",
        page_delay_ms=cfg.page_delay_ms,
        auth_interaction_timeout_s=cfg.auth_interaction_timeout_s,
    )


def _insert_history_page(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    year: int,
    page_index: int,
    start_index: int,
    page_url: str,
    final_url: str,
    html_path: str,
    html: str,
    raw_order_count: int,
    parsed_order_count: int,
    has_next_page: bool,
) -> int:
    cur = conn.execute(
        """
        insert into history_page (
          run_id, year, page_index, start_index, page_url, final_url,
          fetched_at, html_path, html_sha256, raw_order_count, parsed_order_count, has_next_page
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            year,
            page_index,
            start_index,
            page_url,
            final_url,
            _utc_now(),
            html_path,
            _sha256(html),
            raw_order_count,
            parsed_order_count,
            1 if has_next_page else 0,
        ),
    )
    return int(cur.lastrowid)


def _insert_order_ref(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    page_id: int,
    row: dict[str, Any],
) -> int:
    cur = conn.execute(
        """
        insert into order_ref (
          run_id, page_id, order_id, order_date_text, total_amount, currency,
          order_status_text, details_url, details_url_kind, parse_status,
          parse_warnings_json, unsupported_reason, list_item_count, raw_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            page_id,
            row.get("orderId"),
            row.get("orderDate"),
            row.get("totalAmount"),
            row.get("currency"),
            row.get("orderStatus"),
            row.get("detailsUrl"),
            _details_url_kind(str(row.get("detailsUrl") or "")),
            row.get("parseStatus"),
            json.dumps(row.get("parseWarnings") or [], ensure_ascii=False),
            row.get("unsupportedReason"),
            len(row.get("items") or []),
            json.dumps(row, ensure_ascii=False),
        ),
    )
    return int(cur.lastrowid)


def _insert_detail_fetch(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    order_ref_id: int,
    fetch_method: str,
    requested_url: str,
    final_url: str,
    outcome: str,
    html_path: str | None,
    html: str | None,
    detail_parse: Any | None,
) -> int:
    detail_data = detail_parse.data if detail_parse is not None else {}
    cur = conn.execute(
        """
        insert into detail_fetch (
          run_id, order_ref_id, fetch_method, requested_url, final_url, fetched_at, outcome,
          html_path, html_sha256, parse_status, parse_warnings_json, unsupported_reason,
          order_date, total_amount, shipping, gift_wrap, item_count, promotion_count, raw_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            order_ref_id,
            fetch_method,
            requested_url,
            final_url,
            _utc_now(),
            outcome,
            html_path,
            _sha256(html) if html is not None else None,
            detail_parse.parse_status if detail_parse is not None else None,
            json.dumps(list(detail_parse.parse_warnings), ensure_ascii=False) if detail_parse is not None else None,
            detail_parse.unsupported_reason if detail_parse is not None else None,
            detail_data.get("orderDate"),
            detail_data.get("totalAmount"),
            detail_data.get("shipping"),
            detail_data.get("gift_wrap"),
            len(detail_data.get("items") or []),
            len(detail_data.get("promotions") or []),
            json.dumps(detail_data, ensure_ascii=False) if detail_parse is not None else None,
        ),
    )
    return int(cur.lastrowid)


def _record_invoice_anomaly(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    page_id: int | None,
    order_ref_id: int | None,
    fetch_id: int | None,
    anomaly_type: str,
    url: str,
    detail: str | None = None,
) -> None:
    conn.execute(
        """
        insert into invoice_anomaly (
          run_id, page_id, order_ref_id, fetch_id, anomaly_type, url, detail, observed_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, page_id, order_ref_id, fetch_id, anomaly_type, url, detail, _utc_now()),
    )


def _extract_orders(cfg: GroundTruthConfig) -> None:
    run_id = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.html_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.db_path)
    try:
        _create_db(conn)
        conn.execute(
            """
            insert into crawl_run (run_id, source_id, started_at, status, years_requested, browser_mode, state_file, profile_dir)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                cfg.source_id,
                _utc_now(),
                "running",
                cfg.years,
                "headless" if cfg.headless else "headful",
                str(cfg.state_file),
                str(cfg.profile_dir) if cfg.profile_dir is not None else None,
            ),
        )
        conn.commit()

        client = _build_client(cfg)
        seen_order_ids: set[str] = set()
        with sync_playwright() as playwright:
            context, browser = client._open_authenticated_context(playwright=playwright)  # noqa: SLF001
            page = client._open_work_page(context)  # noqa: SLF001
            try:
                current_year = datetime.now().year
                for offset in range(max(1, cfg.years)):
                    year = current_year - offset
                    page_index = 0
                    last_page_marker: tuple[str, tuple[str, ...]] | None = None
                    while True:
                        start_index = page_index * 10
                        page_url = client.profile.order_history_url(year=year, start_index=start_index)
                        html = client._load_authenticated_html(page=page, context=context, url=page_url)  # noqa: SLF001
                        snapshot = _extract_order_cards(page)
                        extracted_orders = list(snapshot.get("orderCards") or [])
                        html_path = _write_html(
                            cfg.html_dir / f"history" / f"year-{year}-page-{page_index:03d}.html",
                            html,
                        )
                        page_id = _insert_history_page(
                            conn,
                            run_id=run_id,
                            year=year,
                            page_index=page_index,
                            start_index=start_index,
                            page_url=page_url,
                            final_url=page.url,
                            html_path=html_path,
                            html=html,
                            raw_order_count=len(extracted_orders),
                            parsed_order_count=len(extracted_orders),
                            has_next_page=bool(snapshot.get("nextPageUrl")),
                        )
                        conn.commit()

                        if not extracted_orders:
                            break

                        page_signature = tuple(
                            str(row.get("orderId") or "").strip()
                            or str(_extract_order_id_from_url(str(row.get("detailsUrl") or "")) or "")
                            for row in extracted_orders
                            if str(row.get("orderId") or "").strip()
                            or str(_extract_order_id_from_url(str(row.get("detailsUrl") or "")) or "")
                        )
                        page_marker = (str(page.url), page_signature)
                        if page_signature and page_marker == last_page_marker:
                            break
                        last_page_marker = page_marker

                        for row in extracted_orders:
                            total_amount, currency = _parse_amount(str(row.get("totalText") or ""))
                            order_id = str(row.get("orderId") or "").strip() or _extract_order_id_from_url(str(row.get("detailsUrl") or ""))
                            link_candidates = list(row.get("linkCandidates") or [])
                            db_row = {
                                "orderId": order_id,
                                "orderDate": row.get("orderDate"),
                                "totalAmount": total_amount,
                                "currency": currency,
                                "orderStatus": row.get("orderStatus"),
                                "detailsUrl": row.get("detailsUrl"),
                                "parseStatus": "dom_extracted",
                                "parseWarnings": [],
                                "unsupportedReason": None,
                                "items": [{}] * int(row.get("listItemCount") or 0),
                                "rawText": row.get("rawText"),
                                "linkCandidates": link_candidates,
                            }
                            order_ref_id = _insert_order_ref(conn, run_id=run_id, page_id=page_id, row=db_row)
                            for candidate in link_candidates:
                                conn.execute(
                                    """
                                    insert into order_link_candidate (
                                      run_id, page_id, order_ref_id, href, absolute_url, link_text, details_url_kind, is_invoice_like
                                    ) values (?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        run_id,
                                        page_id,
                                        order_ref_id,
                                        candidate.get("href") or "",
                                        candidate.get("absolute_url") or "",
                                        candidate.get("text") or "",
                                        _details_url_kind(str(candidate.get("absolute_url") or "")),
                                        1 if _is_invoice_like_url(str(candidate.get("absolute_url") or "")) else 0,
                                    ),
                                )

                            details_url = str(db_row.get("detailsUrl") or "").strip()
                            if _is_invoice_like_url(details_url):
                                _record_invoice_anomaly(
                                    conn,
                                    run_id=run_id,
                                    page_id=page_id,
                                    order_ref_id=order_ref_id,
                                    fetch_id=None,
                                    anomaly_type="invoice_like_details_url",
                                    url=details_url,
                                    detail="list parser selected invoice-like URL as detailsUrl",
                                )

                            if not details_url:
                                conn.commit()
                                continue

                            if order_id in seen_order_ids:
                                conn.commit()
                                continue
                            if order_id:
                                seen_order_ids.add(order_id)

                            detail_html = None
                            detail_final_url = details_url
                            fetch_method = "request"
                            outcome = "ok"
                            detail_parse = None
                            try:
                                response = context.request.get(details_url)
                                detail_final_url = str(getattr(response, "url", details_url) or details_url)
                                if not response.ok:
                                    outcome = "not_ok"
                                    fetch_method = "page"
                                else:
                                    detail_html = client._validated_detail_html(  # noqa: SLF001
                                        url=detail_final_url,
                                        html=response.text(),
                                    )
                            except AmazonReauthRequiredError:
                                outcome = "auth_block"
                            except Exception:
                                outcome = "request_error"

                            if detail_html is None and outcome not in {"auth_block"}:
                                fetch_method = "page"
                                try:
                                    detail_page = context.new_page()
                                    try:
                                        detail_html = client._load_authenticated_html(  # noqa: SLF001
                                            page=detail_page,
                                            context=context,
                                            url=details_url,
                                        )
                                        detail_final_url = detail_page.url
                                    finally:
                                        detail_page.close()
                                except AmazonReauthRequiredError:
                                    outcome = "auth_block"
                                except Exception:
                                    outcome = "page_error"

                            detail_html_path = None
                            if detail_html is not None:
                                detail_html_path = _write_html(
                                    cfg.html_dir / "details" / f"{order_id or order_ref_id}.html",
                                    detail_html,
                                )
                                try:
                                    detail_parse = parse_order_detail_html(detail_html, profile=client.profile)
                                except Exception:
                                    outcome = "parse_error"
                                if _is_invoice_like_url(detail_final_url):
                                    outcome = "invoice_page"

                            fetch_id = _insert_detail_fetch(
                                conn,
                                run_id=run_id,
                                order_ref_id=order_ref_id,
                                fetch_method=fetch_method,
                                requested_url=details_url,
                                final_url=detail_final_url,
                                outcome=outcome,
                                html_path=detail_html_path,
                                html=detail_html,
                                detail_parse=detail_parse,
                            )

                            if _is_invoice_like_url(detail_final_url):
                                _record_invoice_anomaly(
                                    conn,
                                    run_id=run_id,
                                    page_id=page_id,
                                    order_ref_id=order_ref_id,
                                    fetch_id=fetch_id,
                                    anomaly_type="invoice_detail_fetch",
                                    url=detail_final_url,
                                    detail=f"fetch_method={fetch_method}",
                                )
                            conn.commit()

                        if not snapshot.get("nextPageUrl"):
                            break
                        page_index += 1

                conn.execute(
                    "update crawl_run set finished_at = ?, status = ? where run_id = ?",
                    (_utc_now(), "completed", run_id),
                )
                conn.commit()
            finally:
                context.close()
                if browser is not None:
                    browser.close()
    except Exception as exc:  # noqa: BLE001
        conn.execute(
            "update crawl_run set finished_at = ?, status = ?, error = ? where run_id = ?",
            (_utc_now(), "failed", str(exc), run_id),
        )
        conn.commit()
        raise
    finally:
        conn.close()


def _app_config() -> AppConfig:
    home = Path.home()
    app_support = home / "Library" / "Application Support" / "lidltool-desktop"
    return AppConfig(
        db_path=app_support / "lidltool.sqlite",
        config_dir=app_support / "config",
        credential_encryption_key=(app_support / "credential_encryption_key.txt").read_text(encoding="utf-8").strip(),
        connector_live_sync_enabled=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an independent Amazon ground-truth crawl database.")
    parser.add_argument("--source-id", default="amazon_de")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--headless", action="store_true", default=False)
    parser.add_argument("--auth-interaction-timeout-s", type=int, default=900)
    parser.add_argument("--db", type=Path, default=REPO_ROOT / ".amazon-debug" / "ground-truth" / "amazon_ground_truth.sqlite")
    parser.add_argument("--html-dir", type=Path, default=REPO_ROOT / ".amazon-debug" / "ground-truth" / "html")
    parser.add_argument("--page-delay-ms", type=int, default=800)
    args = parser.parse_args()

    config = _app_config()
    state_file = default_amazon_state_file(config, source_id=args.source_id)
    profile_dir = default_amazon_profile_dir(config, source_id=args.source_id)
    cfg = GroundTruthConfig(
        source_id=args.source_id,
        years=max(1, args.years),
        headless=bool(args.headless),
        auth_interaction_timeout_s=max(30, args.auth_interaction_timeout_s),
        page_delay_ms=max(100, args.page_delay_ms),
        db_path=args.db,
        html_dir=args.html_dir,
        state_file=state_file,
        profile_dir=profile_dir if profile_dir.exists() else None,
    )
    _extract_orders(cfg)
    print(f"Ground-truth database written to {cfg.db_path}")


if __name__ == "__main__":
    main()
