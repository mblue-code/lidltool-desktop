from __future__ import annotations

import sys
import unittest
from pathlib import Path

DESKTOP_ROOT = Path(__file__).resolve().parents[2]
VENDOR_BACKEND_SRC = DESKTOP_ROOT / "vendor" / "backend" / "src"

if str(VENDOR_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_BACKEND_SRC))

from lidltool.lidl.client import _format_ticket_total_amount, _parse_mre_html_items  # noqa: E402


class LidlReceiptParserTests(unittest.TestCase):
    def test_parses_anonymous_product_lines_with_amounts(self) -> None:
        html = """
        <span id="purchase_list_line_1" class="currency css_bold">EUR</span>
        <span id="purchase_list_line_2" class="article css_bold" data-art-description="Extra Himbe.Granatap" data-unit-price="3,45">Extra Himbe.Granatap</span>
        <span id="purchase_list_line_2" class="article css_bold" data-art-description="Extra Himbe.Granatap" data-unit-price="3,45">3,45</span>
        <span id="purchase_list_line_3" class="css_bold">LC Starterpa-1801429</span>
        <span id="purchase_list_line_3" class="css_bold">9,99</span>
        <span id="purchase_list_line_3" class="css_bold">B</span>
        <span id="purchase_list_line_4" class="css_bold">Seriennr.: 0026255204725579</span>
        <span id="purchase_list_line_5" class="css_bold">Pfandrückgabe</span>
        <span id="purchase_list_line_5" class="css_bold">-0,25</span>
        <span id="purchase_list_line_5" class="css_bold">B</span>
        """

        items = _parse_mre_html_items(html)

        self.assertEqual([item["name"] for item in items], [
            "Extra Himbe.Granatap",
            "LC Starterpa-1801429",
            "Pfandrückgabe",
        ])
        self.assertEqual(items[1]["lineTotal"], 9.99)
        self.assertEqual(items[1]["vatRate"], 0.19)
        self.assertEqual(items[2]["lineTotal"], -0.25)

    def test_keeps_repeated_identical_article_lines_when_ids_differ(self) -> None:
        html = """
        <span id="purchase_list_line_2" class="article css_bold" data-art-description="Wasser" data-unit-price="0,89">Wasser</span>
        <span id="purchase_list_line_3" class="article css_bold" data-art-description="Wasser" data-unit-price="0,89">Wasser</span>
        """

        items = _parse_mre_html_items(html)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["name"], "Wasser")
        self.assertEqual(items[1]["name"], "Wasser")

    def test_skips_weighted_item_detail_continuation_and_deposit_count_lines(self) -> None:
        html = """
        <span id="purchase_list_line_2" class="article css_bold" data-art-description="Zucchini kg" data-art-quantity="0,304" data-unit-price="1,99">Zucchini kg</span>
        <span id="purchase_list_line_2" class="article css_bold" data-art-description="Zucchini kg" data-art-quantity="0,304" data-unit-price="1,99">0,60</span>
        <span id="purchase_list_line_3" class="article css_bold" data-art-description="Zucchini kg" data-art-quantity="0,304" data-unit-price="1,99">0,304</span>
        <span id="purchase_list_line_3" class="article css_bold" data-art-description="Zucchini kg" data-art-quantity="0,304" data-unit-price="1,99">kg x</span>
        <span id="purchase_list_line_3" class="article css_bold" data-art-description="Zucchini kg" data-art-quantity="0,304" data-unit-price="1,99">1,99</span>
        <span id="purchase_list_line_3" class="article css_bold" data-art-description="Zucchini kg" data-art-quantity="0,304" data-unit-price="1,99">EUR/kg</span>
        <span id="purchase_list_line_5" class="css_bold">Pfandrückgabe</span>
        <span id="purchase_list_line_5" class="css_bold">-7,00</span>
        <span id="purchase_list_line_5" class="css_bold">B</span>
        <span id="purchase_list_line_6" class="css_bold">-28</span>
        <span id="purchase_list_line_6" class="css_bold">x</span>
        <span id="purchase_list_line_6" class="css_bold">0,25</span>
        """

        items = _parse_mre_html_items(html)

        self.assertEqual([item["name"] for item in items], ["Zucchini kg", "Pfandrückgabe"])
        self.assertEqual(items[0]["lineTotal"], 0.6)
        self.assertEqual(items[1]["lineTotal"], -7.0)

    def test_formats_integer_summary_totals_as_euro_amounts(self) -> None:
        self.assertEqual(_format_ticket_total_amount(19), "19.00")
        self.assertEqual(_format_ticket_total_amount(30.01), "30.01")


if __name__ == "__main__":
    unittest.main()
