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


def test_parse_order_list_html_prefers_search_detail_links_for_software_orders() -> None:
    html = """
    <html><body>
      <div class="a-box-group order">
        <div>Bestellung aufgegeben 16. März 2023</div>
        <div>Summe 87,98 €</div>
        <div>Bestellnr. 302-3666426-1500361</div>
        <a href="/your-orders/search?search=D01-0721938-6594205&ref=ppx_yo2ov_dt_b_fed_dss_shell_od_hz_search">Bestelldetails anzeigen</a>
        <a href="/your-orders/invoice/popover?orderId=D01-0721938-6594205">Rechnung</a>
        <a href="/dp/B00ISRZFES">Microsoft 365 Single</a>
      </div>
    </body></html>
    """

    result = parse_order_list_html(
        html,
        profile=get_country_profile(source_id="amazon_de"),
        page_url="https://www.amazon.de/gp/your-account/order-history",
    )

    assert len(result.orders) == 1
    assert result.orders[0]["detailsUrl"] == (
        "https://www.amazon.de/your-orders/search?search=D01-0721938-6594205"
        "&ref=ppx_yo2ov_dt_b_fed_dss_shell_od_hz_search"
    )


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
    assert result.unsupported_reason == "canceled_only"


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


def test_parse_order_detail_html_ignores_summary_rows_and_pack_sizes_in_titles() -> None:
    html = """
    <html><body>
      <div>Mein Prime Video</div>
      <div class="a-box-group">
        <div class="a-fixed-left-grid-inner">
          <a class="a-link-normal" href="/dp/B0TEST1234"><img alt="Monster Energy Ultra White (12 x 500 ml)" src="cover.jpg" /></a>
          <div class="a-row">
            <a class="a-link-normal" href="/dp/B0TEST1234">
              Monster Energy Ultra White (12 x 500 ml)
            </a>
          </div>
          <span class="a-color-price">17,88€</span>
        </div>
        <div class="a-fixed-left-grid-inner">
          <span class="a-text-bold">Gesamtsumme:</span>
          <span class="a-color-price">19,04€</span>
        </div>
      </div>
      <div class="a-spacing-mini a-spacing-top-mini">
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Verpackung &amp; Versand:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">0,00 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Gutschein eingelöst:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">-1,16 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Gesamtsumme:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base a-text-bold">19,04 €</span></div>
        </div>
      </div>
    </body></html>
    """

    result = parse_order_detail_html(html, profile=get_country_profile(source_id="amazon_de"))

    assert result.parse_status == "complete"
    assert result.unsupported_reason is None
    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["title"] == "Monster Energy Ultra White (12 x 500 ml)"
    assert result.data["items"][0]["qty"] == 1
    assert result.data["items"][0]["price"] == pytest.approx(17.88)
    assert result.data["totalAmount"] == pytest.approx(19.04)
    assert result.data["promotions"] == [
        {"description": "Gutschein eingelöst:", "amount": pytest.approx(1.16), "category": "coupon"}
    ]


def test_parse_order_detail_html_extracts_digital_titles_and_german_subtotal_kinds() -> None:
    html = """
    <html><body>
      <div class="a-box-group">
        <div class="a-fixed-left-grid-inner">
          <div class="aok-relative">
            <a class="a-link-normal" href="/your-orders/order-details?orderID=D01-1906591-4994257">
              <img alt="Send files to TV - SFTTV" src="cover.jpg" />
            </a>
          </div>
          <div class="a-row">
            <a class="a-link-normal" href="/your-orders/order-details?orderID=D01-1906591-4994257">
              Send files to TV - SFTTV
            </a>
          </div>
          <div data-component="unitPrice">
            <span class="a-price a-text-price"><span class="a-offscreen">0,00€</span></span>
          </div>
          <div class="a-row">
            <span class="a-size-small a-color-secondary"><span class="a-text-bold a-nowrap">Amazon Appstore</span></span>
          </div>
        </div>
      </div>
      <div class="a-spacing-mini a-spacing-top-mini">
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Artikel-Zwischensumme:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">3,35 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Gesamtbetrag vor Steuern:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">3,35 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>MwSt:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">0,64 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Gesamtbetrag für diese Bestellung:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base a-text-bold">3,99 €</span></div>
        </div>
      </div>
    </body></html>
    """

    result = parse_order_detail_html(html, profile=get_country_profile(source_id="amazon_de"))

    assert len(result.data["items"]) == 1
    assert result.data["items"][0]["title"] == "Send files to TV - SFTTV"
    assert [entry["category"] for entry in result.data["subtotals"]] == [
        "subtotal",
        "pre_tax_total",
        "tax",
        "order_total",
    ]


def test_parse_order_detail_html_ignores_refund_summary_rows_as_promotions() -> None:
    html = """
    <html><body>
      <div class="a-box-group">
        <div class="a-fixed-left-grid-inner">
          <a class="a-link-normal" href="/dp/B07H9DVLBB">
            SanDisk Extreme Pro SDXC UHS-I Speicherkarte 128GB
          </a>
          <span class="a-price a-text-price"><span class="a-offscreen">26,37€</span></span>
          <span>Menge: 2</span>
        </div>
      </div>
      <div class="a-spacing-mini a-spacing-top-mini">
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Zwischensumme:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">50,32 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Anzurechnende MwSt.:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">9,66 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Summe:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base a-text-bold">59,98 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Summe der Erstattung</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base a-text-bold">10,00 €</span></div>
        </div>
      </div>
    </body></html>
    """

    result = parse_order_detail_html(html, profile=get_country_profile(source_id="amazon_de"))

    assert result.parse_status == "complete"
    assert result.data["promotions"] == []
    assert [entry["category"] for entry in result.data["subtotals"]] == [
        "subtotal",
        "tax",
        "order_total",
        "refund_info",
    ]


def test_parse_order_detail_html_infers_hidden_deposit_for_de_can_packs() -> None:
    html = """
    <html><body>
      <div>Meine Bestellungen</div>
      <div data-component="default">
        <span>Bestellung aufgegeben</span>
        <span>4. April 2026</span>
      </div>
      <div class="a-box-group" data-component="shipments">
        <div class="a-fixed-left-grid-inner" data-component="purchasedItems">
          <a class="a-link-normal" href="/dp/B0TEST1234">
            Monster Energy Ultra White - in praktischen Einweg Dosen (12 x 500 ml)
          </a>
          <div data-component="unitPrice">
            <span class="a-price a-text-price"><span class="a-offscreen">17,88€</span></span>
            <span class="a-price a-text-price"><span class="a-offscreen">17,88€</span></span>
          </div>
        </div>
      </div>
      <div data-component="chargeSummary">
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Zwischensumme:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">15,03 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Verpackung &amp; Versand:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">0,00 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Summe:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">20,88 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Gutschein eingelöst:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base">-1,84 €</span></div>
        </div>
        <div class="a-row od-line-item-row">
          <div class="a-column a-span7 od-line-item-row-label"><span>Gesamtsumme:</span></div>
          <div class="a-column a-span5 od-line-item-row-content a-span-last"><span class="a-size-base a-color-base a-text-bold">19,04 €</span></div>
        </div>
      </div>
    </body></html>
    """

    result = parse_order_detail_html(html, profile=get_country_profile(source_id="amazon_de"))
    merged = merge_item_details([], result.data["items"], profile=get_country_profile(source_id="amazon_de"))

    assert result.data["orderDate"] == "4. April 2026"
    assert len(result.data["items"]) == 2
    deposit_item = next(item for item in result.data["items"] if item.get("isDeposit"))
    assert deposit_item["title"] == "Einwegpfand"
    assert deposit_item["price"] == pytest.approx(3.0)
    assert deposit_item["category"] == "deposit"
    merged_deposit_item = next(item for item in merged if item.get("isDeposit"))
    assert merged_deposit_item["category"] == "deposit"


def test_parse_order_list_html_does_not_infer_total_from_order_date_on_unbilled_cancellations() -> None:
    html = """
    <html><body>
      <div class="order-card">
        <span>Bestellung aufgegeben</span>
        <span>1. Februar 2026</span>
        <span>Bestellnr.</span>
        <span>302-2956157-7140343</span>
        <span>Storniert</span>
        <span>Diese Bestellung wurde dir nicht in Rechnung gestellt.</span>
        <a href="/dp/B06XSFWLWJ">USB Kabel</a>
      </div>
    </body></html>
    """

    result = parse_order_list_html(
        html,
        profile=get_country_profile(source_id="amazon_de"),
        page_url="https://www.amazon.de/gp/your-account/order-history",
    )

    assert len(result.orders) == 1
    assert result.orders[0]["totalAmount"] == pytest.approx(0.0)
    assert result.orders[0]["parseWarnings"] == ["missing_total_amount", "missing_details_url"]
    assert result.orders[0]["unsupportedReason"] == "canceled_only"


def test_parse_order_list_html_does_not_mark_return_eligible_orders_as_unsupported() -> None:
    html = """
    <html><body>
      <div class="order-card">
        <span>Bestellung aufgegeben</span>
        <span>14. April 2025</span>
        <span>Bestellnr.</span>
        <span>304-8691348-5469157</span>
        <a href="/your-orders/order-details?orderID=304-8691348-5469157">Bestelldetails anzeigen</a>
        <a href="/dp/B00650P2ZC">Artikel A</a>
        <a href="/dp/B07G8V5SPY">Artikel B</a>
        <span>Rücksendungsberechtigung</span>
        <span>Artikel ersetzen</span>
      </div>
    </body></html>
    """

    result = parse_order_list_html(
        html,
        profile=get_country_profile(source_id="amazon_de"),
        page_url="https://www.amazon.de/gp/your-account/order-history",
    )

    assert len(result.orders) == 1
    assert result.orders[0]["unsupportedReason"] is None
    assert result.orders[0]["parseStatus"] == "partial"


def test_parse_order_list_html_keeps_digital_d01_orders_and_prefers_order_details_links() -> None:
    html = """
    <html><body>
      <div class="order-card js-order-card">
        <div class="order-header">
          <li class="order-header__header-list-item">
            <div class="a-row a-size-mini"><span class="a-color-secondary a-text-caps">Bestellung aufgegeben</span></div>
            <div class="a-row"><span class="a-size-base a-color-secondary">25. April 2025</span></div>
          </li>
          <li class="order-header__header-list-item">
            <div class="a-row a-size-mini"><span class="a-color-secondary a-text-caps">Summe</span></div>
            <div class="a-row"><span class="a-size-base a-color-secondary">4,46 €</span></div>
          </li>
          <li class="order-header__header-list-item yohtmlc-order-level-connections">
            <div class="yohtmlc-order-id">
              <span class="a-color-secondary a-text-caps">Bestellnr.</span>
              <span class="a-color-secondary" dir="ltr">D01-2396164-3487030</span>
            </div>
            <a class="a-link-normal" href="/gp/css/order-details?orderID=D01-2396164-3487030&ref=ppx_yo2ov_dt_b_fed_digi_order_details_351">
              Bestelldetails anzeigen
            </a>
            <a class="a-link-normal" href="/your-orders/invoice/popover?orderId=D01-2396164-3487030&relatedRequestId=ABC123&ref_=fed_digi_order_invoice_ajax">
              Rechnung
            </a>
          </li>
        </div>
        <div class="a-fixed-left-grid-inner item-box">
          <a class="a-link-normal" href="/dp/B0DFTZTJ3Z?ref=ppx_yo2ov_dt_b_fed_digi_asin_title_351">
            Bound: The Gift of Desire (English Edition)
          </a>
        </div>
      </div>
    </body></html>
    """

    result = parse_order_list_html(
        html,
        profile=get_country_profile(source_id="amazon_de"),
        page_url="https://www.amazon.de/gp/your-account/order-history",
    )

    assert len(result.orders) == 1
    assert result.orders[0]["orderId"] == "D01-2396164-3487030"
    assert result.orders[0]["detailsUrl"] == (
        "https://www.amazon.de/gp/css/order-details?orderID=D01-2396164-3487030"
        "&ref=ppx_yo2ov_dt_b_fed_digi_order_details_351"
    )
    assert result.orders[0]["totalAmount"] == pytest.approx(4.46)


def test_parse_order_detail_html_uses_explicit_qty_badges_and_ignores_refund_summary_rows() -> None:
    html = """
    <html><body>
      <div class="a-box-group">
        <div class="a-fixed-left-grid-inner">
          <div class="aok-relative">
            <a class="a-link-normal" href="/dp/B07ZFGGYWC">
              <img alt="Generic variant title" src="item-a.jpg" />
            </a>
            <div class="od-item-view-qty"><span>2</span></div>
          </div>
          <div class="a-row">
            <a class="a-link-normal" href="/dp/B07ZFGGYWC">
              KFZ Stromdieb Stromabgreifer in 4 Größen zum Auswählen mini kurz, micro2, mini, regulär (mini)
            </a>
          </div>
          <span class="a-color-price">2,85€</span>
        </div>
        <div class="a-fixed-left-grid-inner">
          <a class="a-link-normal" href="/dp/B07K46B7ZC">
            RUNCCI-YUN 120Pcs T-Tap Elektrische Steckverbinder, Stromdieb,60 T-Abzweigverbinder + 60Flachstecker
          </a>
          <span class="a-color-price">9,55€</span>
        </div>
        <div class="a-fixed-left-grid-inner">
          <span class="a-text-bold">Summe der Erstattung</span>
          <span class="a-color-price">19,90€</span>
        </div>
      </div>
    </body></html>
    """

    result = parse_order_detail_html(html, profile=get_country_profile(source_id="amazon_de"))

    assert result.parse_status == "complete"
    assert [item["asin"] for item in result.data["items"]] == ["B07ZFGGYWC", "B07K46B7ZC"]
    assert result.data["items"][0]["qty"] == 2
    assert result.data["items"][0]["title"].endswith("(mini)")
    assert result.data["items"][1]["qty"] == 1
    assert "120Pcs" in result.data["items"][1]["title"]
