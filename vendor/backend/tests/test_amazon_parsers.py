from __future__ import annotations

from pathlib import Path

import pytest

from lidltool.amazon.parsers import (
    merge_item_details,
    parse_order_detail_html,
    parse_order_list_html,
    parse_promotions_from_details_html,
)
from lidltool.amazon.profiles import get_country_profile


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "amazon"


def test_parse_order_list_html_for_germany_fixture() -> None:
    html = (FIXTURE_DIR / "list_de.html").read_text(encoding="utf-8")
    result = parse_order_list_html(
        html,
        profile=get_country_profile(source_id="amazon_de"),
        page_url="https://www.amazon.de/gp/your-account/order-history",
    )

    assert result.has_next_page is True
    assert [order["orderId"] for order in result.orders] == [
        "111-1111111-1111111",
        "222-2222222-2222222",
    ]
    assert result.orders[0]["parseStatus"] == "complete"
    assert result.orders[0]["items"][0]["itemUrl"] == "https://www.amazon.de/dp/B00TEST111"


def test_parse_order_detail_html_for_germany_fixture() -> None:
    html = (FIXTURE_DIR / "detail_de.html").read_text(encoding="utf-8")
    result = parse_order_detail_html(html, profile=get_country_profile(source_id="amazon_de"))

    assert result.parse_status == "complete"
    assert len(result.data["items"]) == 2
    assert result.data["items"][0]["discount"] == pytest.approx(2.0)
    assert result.data["shipping"] == pytest.approx(3.99)
    assert result.data["gift_wrap"] == pytest.approx(2.0)
    assert result.data["promotions"][0]["category"] == "coupon"


def test_parse_order_detail_html_marks_unsupported_orders() -> None:
    html = (FIXTURE_DIR / "detail_de_unsupported.html").read_text(encoding="utf-8")
    result = parse_order_detail_html(html, profile=get_country_profile(source_id="amazon_de"))

    assert result.parse_status == "unsupported"
    assert result.unsupported_reason == "digital_order"


def test_parse_order_list_and_detail_for_france_fixture() -> None:
    list_html = (FIXTURE_DIR / "list_fr.html").read_text(encoding="utf-8")
    list_result = parse_order_list_html(
        list_html,
        profile=get_country_profile(source_id="amazon_fr"),
        page_url="https://www.amazon.fr/gp/your-account/order-history",
    )
    assert len(list_result.orders) == 1
    assert list_result.orders[0]["parseStatus"] == "complete"
    assert list_result.orders[0]["items"][0]["itemUrl"] == "https://www.amazon.fr/dp/B00FRTEST1"

    detail_html = (FIXTURE_DIR / "detail_fr.html").read_text(encoding="utf-8")
    detail_result = parse_order_detail_html(detail_html, profile=get_country_profile(source_id="amazon_fr"))
    assert detail_result.parse_status == "complete"
    assert detail_result.data["shipping"] == pytest.approx(4.0)
    assert detail_result.data["promotions"][0]["category"] == "coupon"


def test_parse_order_list_and_detail_for_uk_fixture() -> None:
    list_html = (FIXTURE_DIR / "list_gb.html").read_text(encoding="utf-8")
    list_result = parse_order_list_html(
        list_html,
        profile=get_country_profile(source_id="amazon_gb"),
        page_url="https://www.amazon.co.uk/gp/your-account/order-history",
    )
    assert len(list_result.orders) == 1
    assert list_result.orders[0]["currency"] == "GBP"
    assert list_result.orders[0]["items"][0]["itemUrl"] == "https://www.amazon.co.uk/dp/B00GBTEST1"

    detail_html = (FIXTURE_DIR / "detail_gb.html").read_text(encoding="utf-8")
    detail_result = parse_order_detail_html(detail_html, profile=get_country_profile(source_id="amazon_gb"))
    assert detail_result.parse_status == "complete"
    assert detail_result.data["shipping"] == pytest.approx(3.0)
    assert detail_result.data["promotions"][0]["category"] == "coupon"


def test_parse_promotions_and_merge_item_details_regressions() -> None:
    html = """
    <html><body>
      <div>Rabatt - EUR 2,50</div>
      <div>Coupon savings: 1.20 EUR</div>
    </body></html>
    """
    promotions = parse_promotions_from_details_html(
        html,
        profile=get_country_profile(source_id="amazon_de"),
    )
    assert len(promotions) >= 2
    assert sum(float(p["amount"]) for p in promotions) >= 3.7

    merged = merge_item_details(
        [{"title": "Cable", "asin": "B001", "price": 0, "quantity": 1}],
        [
            {"title": "USB Cable", "asin": "B001", "price": 9.99, "qty": 1},
            {"title": "USB Cable", "asin": "B001", "price": 9.99, "qty": 2},
        ],
        profile=get_country_profile(source_id="amazon_de"),
    )
    assert len(merged) == 1
    assert merged[0]["price"] == pytest.approx(9.99)
    assert merged[0]["quantity"] == 3
