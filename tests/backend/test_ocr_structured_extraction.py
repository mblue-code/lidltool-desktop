from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

from lidltool.config import build_config
from lidltool.ocr.structured_extraction import OcrStructuredReceiptExtractor


class _FakeRuntime:
    def __init__(self, payload: dict[str, object] | list[dict[str, object]]) -> None:
        self._payloads = payload if isinstance(payload, list) else [payload]
        self.requests = []
        self.model_name = "fake-structured-model"
        self.provider_kind = SimpleNamespace(value="fake_runtime")

    def complete_json(self, request):  # noqa: ANN001
        self.requests.append(request)
        if not self._payloads:
            raise RuntimeError("no fake payloads left")
        return SimpleNamespace(data=self._payloads.pop(0))


_REWE_TEXT = """REWE Martin Bornemann oHG
38527 Meine
RUEG.TEEW.GROB                   2,29 B
1 x Frischerabatt               -0,69 B
MIREE DATTEL-CUR                 1,11 B
BANANE                           1,12 B
0,562 kg x   1,99 EUR/kg
KNUS.MUESLI HON                  2,99 B
KNUSPER KROK.                    3,79 B
PESTO ROSSO                      1,99 B
FEINE GUERKCHEN                  2,19 B
TORTILLAS KAESE                  2,98 B
2 Stk x    1,49
DIP HOT CHEESE                   2,49 B
FUSION BBQ HONEY                 1,69 B
SUMME EUR 21,95
Geg. Mastercard EUR 21,95
Datum: 18.04.2026
AS-Zeit 18.04. 17:00 Uhr
Betrag EUR 21,95
TSE-Start: 2026-04-18T17:00:08.000
Mit diesem Einkauf hast du 0,83 EUR
Bonus-Aktion(en) 0,20 EUR
10% auf REWE Beste W 0,63 EUR
Aktuelles Bonus-Guthaben: 1,03 EUR
"""


def _config() -> object:
    return build_config(db_override=Path("/tmp/test-ocr-structured.sqlite"))


class StructuredReceiptExtractionTest(unittest.TestCase):
    def test_structured_extraction_prefers_model_output_for_items_and_discounts(self) -> None:
        extractor = OcrStructuredReceiptExtractor(
            config=_config(),
            runtime=_FakeRuntime(
                {
                    "store_name": "REWE Martin Bornemann oHG",
                    "purchased_at": "2026-04-18T00:00:00+00:00",
                    "discount_total_cents": 69,
                    "currency": "EUR",
                    "items": [
                        {"name": "RUEG.TEEW.GROB", "price_cents": 229, "quantity": 1},
                        {"name": "MIREE DATTEL-CUR", "price_cents": 111, "quantity": 1},
                        {
                            "name": "BANANE",
                            "price_cents": 112,
                            "quantity": 1,
                            "weight_kg": 0.562,
                            "unit_price_cents_per_kg": 199,
                        },
                        {"name": "KNUS.MUESLI HON", "price_cents": 299, "quantity": 1},
                        {"name": "KNUSPER KROK.", "price_cents": 379, "quantity": 1},
                        {"name": "PESTO ROSSO", "price_cents": 199, "quantity": 1},
                        {"name": "FEINE GUERKCHEN", "price_cents": 219, "quantity": 1},
                        {"name": "TORTILLAS KAESE", "price_cents": 298, "quantity": 2},
                        {"name": "DIP HOT CHEESE", "price_cents": 249, "quantity": 1},
                        {"name": "FUSION BBQ HONEY", "price_cents": 169, "quantity": 1},
                    ],
                    "discounts": [
                        {
                            "description": "1 x Frischerabatt",
                            "amount_cents": 69,
                            "item_index": 1,
                        }
                    ],
                    "ignored_lines": ["Geg. Mastercard EUR 21,95", "Datum: 18.04.2026", "Betrag EUR 21,95"],
                }
            ),
        )

        result = extractor.extract(
            ocr_text=_REWE_TEXT,
            fallback_store="OCR Upload",
            ocr_provider="glm_ocr_local",
        )

        self.assertEqual(result.source, "structured")
        self.assertEqual(result.canonical["total_gross_cents"], 2195)
        self.assertEqual(result.canonical["discount_total_cents"], 69)
        names = [item["name"] for item in result.canonical["items"]]
        self.assertNotIn("Datum", names)
        self.assertNotIn("Betrag EUR", names)
        self.assertNotIn("TSE-Start: 2026-04-18T17:00:08.000", names)
        self.assertEqual(len(names), 10)
        self.assertEqual(len(result.discounts), 1)
        self.assertEqual(result.discounts[0]["line_no"], 1)
        self.assertEqual(result.discounts[0]["amount_cents"], 69)
        self.assertEqual(result.canonical["items"][2]["qty"], "0.562")
        self.assertEqual(result.canonical["items"][2]["unit"], "kg")
        self.assertEqual(result.canonical["items"][2]["unit_price_cents"], 199)

    def test_structured_extraction_maps_pfand_discounts_back_to_deposit_items(self) -> None:
        extractor = OcrStructuredReceiptExtractor(
            config=_config(),
            runtime=_FakeRuntime(
                {
                    "items": [
                        {"name": "Paul.Cola 0,33l", "price_cents": 89},
                        {"name": "M.Mio Guarana 0,5l", "price_cents": 109},
                    ],
                    "discounts": [
                        {"description": "Pfand 0,25*B", "amount_cents": 25, "item_index": 1},
                        {"description": "Pfand 0,15*B", "amount_cents": 15, "item_index": 2},
                    ],
                    "discount_total_cents": 40,
                    "ignored_lines": ["Mastercard 2,38€", "Betrag EUR 2,38"],
                }
            ),
        )

        result = extractor.extract(
            ocr_text="""Paul.Cola 0,33l 0,89 B
Pfand 0,25*B
M.Mio Guarana 0,5l 1,09 B
Pfand 0,15*B
SUMME € 2,38
Mastercard 2,38€
""",
            fallback_store="Marktkauf",
            ocr_provider="glm_ocr_local",
        )

        self.assertEqual(result.source, "structured")
        self.assertEqual(result.canonical["total_gross_cents"], 238)
        self.assertEqual(result.canonical["discount_total_cents"], 0)
        self.assertEqual(len(result.discounts), 0)
        self.assertEqual(
            [item["name"] for item in result.canonical["items"]],
            ["Paul.Cola 0,33l", "M.Mio Guarana 0,5l", "Pfand", "Pfand"],
        )
        self.assertTrue(result.canonical["items"][2]["is_deposit"])
        self.assertEqual(result.canonical["items"][2]["line_total_cents"], 25)

    def test_structured_extraction_keeps_informational_discounts_without_breaking_total(self) -> None:
        extractor = OcrStructuredReceiptExtractor(
            config=_config(),
            runtime=_FakeRuntime(
                {
                    "store_name": "SAFEWAY",
                    "purchased_at": "2019-04-25T21:01:00+00:00",
                    "total_gross_cents": 9114,
                    "discount_total_cents": 419,
                    "items": [
                        {"name": "BLUE AGAVE ORGANIC", "line_total_cents": 699},
                        {"name": "CRM OF WHEAT", "line_total_cents": 499},
                        {"name": "SIG CEREAL CRSPY", "line_total_cents": 250},
                        {"name": "NUMI ORGNC TEA", "line_total_cents": 749},
                        {"name": "LACROIX CURFTE", "line_total_cents": 549},
                        {"name": "CRV SF Dk 8 PK TAX", "line_total_cents": 40, "is_deposit": True},
                        {"name": "SIG BROCCOLI CHP", "line_total_cents": 100},
                        {"name": "EB FRM ORGNC CHUNK", "line_total_cents": 1299},
                        {"name": "HORIZON ORGANIC", "line_total_cents": 499},
                        {"name": "O ORGNC BLUEBERRIE", "line_total_cents": 1399},
                        {"name": "WT BANANAS YELLOW", "weight_kg": 3.21, "unit": "lb", "line_total_cents": 254},
                        {"name": "O ORGNC CUBED TOFU", "line_total_cents": 199},
                        {"name": "O ORGANICS SALAD", "line_total_cents": 500},
                        {"name": "BELGIOIOSO FRMSN", "line_total_cents": 899},
                        {"name": "TW PITCHERS RADLER", "line_total_cents": 999},
                        {"name": "CRV BEER 6 PK TAX", "line_total_cents": 30, "is_deposit": True},
                        {"name": "TAX", "line_total_cents": 150},
                    ],
                    "discounts": [
                        {"label": "Card Savings", "amount_cents": 100, "item_index": 1},
                        {"label": "Card Savings", "amount_cents": 99, "item_index": 7},
                        {"label": "Card Savings", "amount_cents": 70, "item_index": 9},
                        {"label": "Card Savings", "amount_cents": 150, "item_index": 15},
                    ],
                }
            ),
        )

        result = extractor.extract(
            ocr_text="SAFEWAY\nBALANCE 91.14\n",
            fallback_store="SAFEWAY",
            ocr_provider="glm_ocr_local",
        )

        self.assertEqual(result.source, "structured")
        self.assertEqual(result.canonical["total_gross_cents"], 9114)
        self.assertEqual(result.canonical["discount_total_cents"], 419)
        self.assertEqual(len(result.discounts), 4)

    def test_structured_extraction_drops_duplicate_deposit_return_item(self) -> None:
        extractor = OcrStructuredReceiptExtractor(
            config=_config(),
            runtime=_FakeRuntime(
                {
                    "store_name": "PENNY-MARKT GmbH",
                    "purchased_at": "2014-10-18T19:03:00+00:00",
                    "total_gross_cents": 1056,
                    "items": [
                        {"name": "Saftorangen", "line_total_cents": 149},
                        {"name": "Banane Golden v.", "line_total_cents": 119},
                        {"name": "Apfel gruen kg", "weight_kg": 0.41, "line_total_cents": 82},
                        {"name": "Pflaume 750g", "line_total_cents": 99},
                        {"name": "Orto Mio Oliven", "line_total_cents": 69},
                        {"name": "HAUTKLAR 3IN1", "quantity": 2, "line_total_cents": 598},
                        {"name": "Today Nachfüllbe", "line_total_cents": 65},
                        {"name": "Spül-/HH- Tücher", "line_total_cents": 75},
                        {
                            "name": "LEERGUT EINWEG",
                            "quantity": 8,
                            "line_total_cents": 200,
                            "is_deposit": True,
                        },
                    ],
                    "discounts": [
                        {
                            "label": "LEERGUT EINWEG",
                            "amount_cents": 200,
                            "scope": "basket",
                            "item_index": 9,
                            "subkind": "deposit_return",
                        }
                    ],
                }
            ),
        )

        result = extractor.extract(
            ocr_text="PENNY\nLEERGUT EINWEG -2,00\nSUMME 10,56\n",
            fallback_store="PENNY",
            ocr_provider="glm_ocr_local",
        )

        self.assertEqual(result.source, "structured")
        self.assertEqual(result.canonical["total_gross_cents"], 1056)
        self.assertEqual(result.canonical["discount_total_cents"], 200)
        self.assertEqual(len(result.canonical["items"]), 8)
        self.assertEqual(len(result.discounts), 1)
        self.assertEqual(result.discounts[0]["scope"], "transaction")

    def test_structured_extraction_can_use_unit_price_for_multi_qty_receipts(self) -> None:
        extractor = OcrStructuredReceiptExtractor(
            config=_config(),
            runtime=_FakeRuntime(
                {
                    "store_name": "Kaiser's Tengelmann GmbH",
                    "purchased_at": "2015-08-31T19:22:02+00:00",
                    "total_gross_cents": 1595,
                    "discount_total_cents": 25,
                    "items": [
                        {"name": "Wurst", "qty": 1, "unit_price_cents": 292, "line_total_cents": 292},
                        {"name": "Kaese", "qty": 1, "unit_price_cents": 290, "line_total_cents": 290},
                        {"name": "A&P BIERSCHI", "qty": 2, "unit_price_cents": 179, "line_total_cents": 358},
                        {"name": "KI.SCHOKOL.", "qty": 2, "unit_price_cents": 99, "line_total_cents": 198},
                        {"name": "BROT 500G", "qty": 2, "unit_price_cents": 139, "line_total_cents": 278},
                        {"name": "TRUE FRUITS", "qty": 1, "unit_price_cents": 399, "line_total_cents": 399},
                        {
                            "name": "BANANEN",
                            "weight_kg": 1.273,
                            "unit": "kg",
                            "unit_price_cents": 139,
                            "line_total_cents": 177,
                        },
                        {"name": "ESSIG", "qty": 2, "unit_price_cents": 45, "line_total_cents": 90},
                    ],
                    "discounts": [
                        {
                            "label": "Leergutbon",
                            "amount_cents": 25,
                            "scope": "basket",
                            "item_index": 0,
                            "kind": "discount",
                            "subkind": "deposit refund",
                        }
                    ],
                }
            ),
        )

        result = extractor.extract(
            ocr_text="Kaiser's\nZwischensumme EUR 15,95\n",
            fallback_store="Kaiser's",
            ocr_provider="glm_ocr_local",
        )

        self.assertEqual(result.source, "structured")
        self.assertEqual(result.canonical["total_gross_cents"], 1595)
        self.assertEqual(result.canonical["discount_total_cents"], 25)
        self.assertEqual(result.canonical["items"][2]["line_total_cents"], 179)
        self.assertEqual(result.canonical["items"][3]["line_total_cents"], 99)
        self.assertEqual(result.canonical["items"][7]["line_total_cents"], 45)

    def test_structured_extraction_falls_back_when_totals_do_not_reconcile(self) -> None:
        extractor = OcrStructuredReceiptExtractor(
            config=_config(),
            runtime=_FakeRuntime(
                [
                    {
                        "store_name": "REWE Martin Bornemann oHG",
                        "purchased_at": "2026-04-18T00:00:00+00:00",
                        "total_gross_cents": 2195,
                        "discount_total_cents": 0,
                        "currency": "EUR",
                        "items": [
                            {"name": "BANANE", "qty": "1.000", "line_total_cents": 112},
                            {"name": "Datum", "qty": "1.000", "line_total_cents": 1804},
                        ],
                        "discounts": [],
                        "ignored_lines": [],
                    },
                    {
                        "store_name": "REWE Martin Bornemann oHG",
                        "purchased_at": "2026-04-18T00:00:00+00:00",
                        "total_gross_cents": 2195,
                        "discount_total_cents": 0,
                        "currency": "EUR",
                        "items": [
                            {"name": "BANANE", "qty": "1.000", "line_total_cents": 112},
                            {"name": "Datum", "qty": "1.000", "line_total_cents": 1804},
                        ],
                        "discounts": [],
                        "ignored_lines": [],
                    },
                ]
            ),
        )

        result = extractor.extract(
            ocr_text=_REWE_TEXT,
            fallback_store="OCR Upload",
            ocr_provider="glm_ocr_local",
        )

        self.assertEqual(result.source, "parser")
        self.assertEqual(result.metadata["reason"], "structured_validation_failed")

    def test_structured_extraction_uses_vision_candidate_when_text_candidate_fails(self) -> None:
        extractor = OcrStructuredReceiptExtractor(
            config=_config(),
            runtime=_FakeRuntime(
                {
                    "store_name": "rewe_webd97_1.pdf",
                    "purchased_at": "2020-01-13T00:00:00+00:00",
                    "total_gross_cents": 70,
                    "items": [
                        {"name": "ZITRONE", "line_total_cents": 89},
                    ],
                    "discounts": [],
                }
            ),
        )

        result = extractor.extract(
            ocr_text="REWE\nSUMME EUR 13,05\n",
            fallback_store="rewe_webd97_1.pdf",
            ocr_provider="openai_compatible",
            ocr_metadata={
                "structured_vision_candidate": {
                    "status": "ok",
                    "payload": {
                        "store_name": "REWE Markt GmbH",
                        "purchased_at": "2020-01-13T00:00:00+00:00",
                        "total_gross_cents": 1305,
                        "items": [
                            {"name": "ZITRONE", "line_total_cents": 89},
                            {"name": "APFEL GRANNY SMI", "line_total_cents": 197},
                            {"name": "KIWI GOLD", "qty": 4, "unit_price_cents": 79, "line_total_cents": 316},
                            {"name": "BLATTSPINAT BIO", "line_total_cents": 179},
                            {"name": "TOPFPFLANZE", "line_total_cents": 499},
                            {"name": "ORANGENSAFT", "line_total_cents": 85},
                            {"name": "TOPFREINIGER", "line_total_cents": 35},
                        ],
                        "discounts": [
                            {"label": "LEERGUT EINWEG", "amount_cents": 25, "scope": "transaction"},
                            {"label": "Mitarbeiterrabatt 5%", "amount_cents": 6, "scope": "transaction"},
                            {"label": "Mitarbeiterrabatt 5%", "amount_cents": 64, "scope": "transaction"},
                        ],
                    },
                }
            },
        )

        self.assertEqual(result.source, "structured")
        self.assertEqual(result.metadata["selected_source"], "vision")
        self.assertEqual(result.canonical["store_name"], "REWE Markt GmbH")
        self.assertEqual(result.canonical["total_gross_cents"], 1305)
        self.assertEqual(result.canonical["discount_total_cents"], 95)
        self.assertEqual(len(result.discounts), 3)

    def test_structured_extraction_prefers_vision_when_both_reconcile_but_text_looks_like_filename(self) -> None:
        extractor = OcrStructuredReceiptExtractor(
            config=_config(),
            runtime=_FakeRuntime(
                {
                    "store_name": "rewe_webd97_5.pdf",
                    "purchased_at": "2023-08-11T00:00:00+00:00",
                    "total_gross_cents": 3944,
                    "items": [
                        {"name": "SALAMI SPITZENQ.", "line_total_cents": 179},
                        {"name": "BUTTERSCHINKEN", "line_total_cents": 259},
                        {"name": "KAESEAUFSCHNITT", "line_total_cents": 199},
                        {"name": "MIREE KRAEUTER", "line_total_cents": 99},
                        {"name": "VITAL UND FIT", "line_total_cents": 189},
                        {"name": "SKYR NATUR", "line_total_cents": 149},
                        {"name": "BAG. SPECIALE", "qty": 2, "unit_price_cents": 229, "line_total_cents": 458},
                        {"name": "TIRAMISU", "line_total_cents": 199},
                        {"name": "FUSILLI", "line_total_cents": 79},
                        {"name": "PENNE RIGATE", "line_total_cents": 79},
                        {"name": "REMOULADE", "line_total_cents": 185},
                        {"name": "CRUNCHIPS PAPRIK", "line_total_cents": 199},
                        {"name": "CREMA G. BOH.", "line_total_cents": 1499},
                        {"name": "COMP.PROT.ZAHNCR", "line_total_cents": 599},
                    ],
                    "discounts": [
                        {"label": "5% REWE Scan u. Go", "amount_cents": 30},
                        {"label": "5% REWE Scan u. Go", "amount_cents": 189},
                        {"label": "Mitarbeiterrabatt 5%", "amount_cents": 29},
                        {"label": "Mitarbeiterrabatt 5%", "amount_cents": 179},
                    ],
                }
            ),
        )

        result = extractor.extract(
            ocr_text="REWE\nSUMME EUR 39,44\n",
            fallback_store="rewe_webd97_5.pdf",
            ocr_provider="openai_compatible",
            ocr_metadata={
                "structured_vision_candidate": {
                    "status": "ok",
                    "payload": {
                        "store_name": "REWE Jürgen Maziejewski OHG",
                        "purchased_at": "2023-08-11T00:00:00+00:00",
                        "total_gross_cents": 3944,
                        "items": [
                            {"name": "SALAMI SPITZENQ.", "line_total_cents": 179},
                            {"name": "BUTTERSCHINKEN", "line_total_cents": 259},
                            {"name": "KAESEAUFSCHNITT", "line_total_cents": 199},
                            {"name": "MIREE KRAEUTER", "line_total_cents": 99},
                            {"name": "VITAL UND FIT", "line_total_cents": 189},
                            {"name": "SKYR NATUR", "line_total_cents": 149},
                            {"name": "BAG. SPECIALE", "qty": 2, "unit_price_cents": 229, "line_total_cents": 458},
                            {"name": "TIRAMISU", "line_total_cents": 199},
                            {"name": "FUSILLI", "line_total_cents": 79},
                            {"name": "PENNE RIGATE", "line_total_cents": 79},
                            {"name": "REMOULADE", "line_total_cents": 185},
                            {"name": "CRUNCHIPS PAPRIK", "line_total_cents": 199},
                            {"name": "CREMA G. BOH.", "line_total_cents": 1499},
                            {"name": "COMP.PROT.ZAHNCR", "line_total_cents": 599},
                        ],
                        "discounts": [
                            {"label": "5% REWE Scan u. Go", "amount_cents": 30},
                            {"label": "5% REWE Scan u. Go", "amount_cents": 189},
                            {"label": "Mitarbeiterrabatt 5%", "amount_cents": 29},
                            {"label": "Mitarbeiterrabatt 5%", "amount_cents": 179},
                        ],
                    },
                }
            },
        )

        self.assertEqual(result.metadata["selected_source"], "vision")
        self.assertEqual(result.canonical["store_name"], "REWE Jürgen Maziejewski OHG")

    def test_structured_extraction_repairs_failed_text_candidate_before_parser_fallback(self) -> None:
        runtime = _FakeRuntime(
            [
                {
                    "store_name": "rewe_webd97_1.pdf",
                    "purchased_at": "2020-01-13T00:00:00+00:00",
                    "total_gross_cents": 70,
                    "items": [
                        {"name": "ZITRONE", "line_total_cents": 89},
                        {"name": "Punktestand entspricht", "line_total_cents": 988},
                    ],
                    "discounts": [],
                },
                {
                    "store_name": "rewe_webd97_1.pdf",
                    "purchased_at": "2006-05-25T00:00:00+00:00",
                    "total_gross_cents": 1305,
                    "items": [
                        {"name": "ZITRONE", "line_total_cents": 89},
                        {"name": "APFEL GRANNY SMI", "weight_kg": 0.792, "unit_price_cents_per_kg": 249, "line_total_cents": 197},
                        {"name": "KIWI GOLD", "quantity": 4, "unit_price_cents": 79, "line_total_cents": 316},
                        {"name": "BLATTSPINAT BIO", "line_total_cents": 179},
                        {"name": "TOPFPFLANZE", "line_total_cents": 499},
                        {"name": "ORANGENSAFT", "line_total_cents": 85},
                        {"name": "TOPFREINIGER", "line_total_cents": 35},
                    ],
                    "discounts": [
                        {"label": "LEERGUT EINWEG", "amount_cents": 25},
                        {"label": "Mitarbeiterrabatt 5%", "amount_cents": 6},
                        {"label": "Mitarbeiterrabatt 5%", "amount_cents": 64},
                    ],
                },
            ]
        )
        extractor = OcrStructuredReceiptExtractor(
            config=_config(),
            runtime=runtime,
        )

        result = extractor.extract(
            ocr_text="""REWE
ZITRONE 0,89 B
APFEL GRANNY SMI 1,97 B
  0,792 kg x   2,49 EUR/kg
KIWI GOLD 3,16 B
  4 Stk x    0,79
BLATTSPINAT BIO 1,79 B
TOPFPFLANZE 4,99 B
ORANGENSAFT 0,85 A
TOPFREINIGER 0,35 A
LEERGUT EINWEG -0,25 A *
 Mitarbeiterrabatt 5% -0,06 A
 Mitarbeiterrabatt 5% -0,64 B
SUMME EUR 13,05
13.01.2020 17:25 Bon-Nr.:933
REWE Markt GmbH
Punktestand entspricht: 9,88 EUR
""",
            fallback_store="rewe_webd97_1.pdf",
            ocr_provider="openai_compatible",
        )

        self.assertEqual(result.source, "structured")
        self.assertEqual(result.metadata["selected_source"], "repair")
        self.assertEqual(result.canonical["store_name"], "REWE Markt GmbH")
        self.assertEqual(result.canonical["purchased_at"][:10], "2020-01-13")
        self.assertEqual(result.canonical["discount_total_cents"], 95)
        self.assertEqual(len(result.canonical["items"]), 7)
        self.assertEqual(len(result.discounts), 3)
        self.assertEqual(len(runtime.requests), 2)


if __name__ == "__main__":
    unittest.main()
