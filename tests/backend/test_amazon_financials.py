from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from lidltool.amazon.order_money import normalize_order_financials
from lidltool.amazon.recalc import recalculate_amazon_transaction_financials
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import Source, Transaction, TransactionItem
from sqlalchemy import func, select


def _order(*, gross: float, final: float | None, refunds: list[tuple[str, float]] | None = None) -> dict:
    subtotals = [
        {"label": "Summe:", "amount": gross, "category": "order_total"},
    ]
    if final is not None:
        subtotals.append({"label": "Gesamtsumme:", "amount": final, "category": "order_total"})
    for label, amount in refunds or []:
        subtotals.append({"label": label, "amount": amount, "category": "refund_info"})
    order = {
        "totalAmount": final if final is not None else gross,
        "subtotals": subtotals,
    }
    if final is not None:
        order["originalOrder"] = {"totalAmount": final}
    return order


def test_amazon_financials_partial_refund_uses_final_charged_total() -> None:
    financials = normalize_order_financials(
        _order(gross=1639.52, final=1621.57, refunds=[("Summe der Erstattung", 62.00)]),
        gross_total_cents=163952,
    )

    assert financials.gross_total_cents == 163952
    assert financials.final_order_total_cents == 162157
    assert financials.refund_total_cents == 6200
    assert financials.net_spending_total_cents == 155957
    assert "partial_refund" in financials.flags


def test_amazon_financials_fully_refunded_clamps_to_zero() -> None:
    financials = normalize_order_financials(
        _order(gross=313.36, final=313.36, refunds=[("Summe der Erstattung", 313.36)]),
        gross_total_cents=31336,
    )

    assert financials.net_spending_total_cents == 0
    assert "fully_refunded" in financials.flags


def test_amazon_financials_gift_card_reflected_in_final_is_not_subtracted_twice() -> None:
    financials = normalize_order_financials(
        {
            "totalAmount": 0.0,
            "subtotals": [
                {"label": "Summe:", "amount": 7.74, "category": "order_total"},
                {"label": "Geschenkgutschein(e):", "amount": -7.74, "category": "coupon"},
                {"label": "Gesamtsumme:", "amount": 0.0, "category": "order_total"},
            ],
            "paymentAdjustments": [
                {"label": "Geschenkgutschein(e):", "amount_cents": 774, "subkind": "gift_card_balance"}
            ],
            "originalOrder": {"totalAmount": 0.0},
        },
        gross_total_cents=774,
    )

    assert financials.final_order_total_cents == 0
    assert financials.payment_adjustment_total_cents == 774
    assert financials.refund_total_cents == 0
    assert financials.net_spending_total_cents == 0


def test_amazon_financials_missing_final_total_falls_back_to_gross() -> None:
    financials = normalize_order_financials(
        {"subtotals": [{"label": "Zwischensumme:", "amount": 12.34, "category": "subtotal"}]},
        gross_total_cents=1234,
    )

    assert financials.final_order_total_cents == 1234
    assert financials.net_spending_total_cents == 1234
    assert "missing_final_order_total" in financials.warnings


def test_amazon_financials_refund_greater_than_final_clamps_to_zero() -> None:
    financials = normalize_order_financials(
        _order(gross=50.0, final=40.0, refunds=[("Refund total", 60.0)]),
        gross_total_cents=5000,
    )

    assert financials.refund_total_cents == 6000
    assert financials.net_spending_total_cents == 0
    assert "refund_exceeds_final_total" in financials.flags


def test_amazon_financials_recognizes_german_and_english_refund_labels() -> None:
    financials = normalize_order_financials(
        _order(
            gross=100.0,
            final=100.0,
            refunds=[("Gesamterstattungsbetrag", 12.0), ("Refund total", 8.0)],
        ),
        gross_total_cents=10000,
    )

    assert financials.refund_total_cents == 2000
    assert financials.net_spending_total_cents == 8000


def test_amazon_recalc_updates_existing_transaction_in_place_and_preserves_items(tmp_path: Path) -> None:
    db_path = (tmp_path / "lidltool.sqlite").resolve()
    db_url = f"sqlite:///{db_path}"
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    sessions = session_factory(engine)

    with session_scope(sessions) as session:
        session.add(
            Source(
                id="amazon_de",
                kind="connector",
                display_name="Amazon",
                status="healthy",
                enabled=True,
                reporting_role="spending_only",
            )
        )
        transaction = Transaction(
            id="tx-amazon",
            source_id="amazon_de",
            source_transaction_id="amazon-306-4659501-3303528",
            purchased_at=datetime(2020, 10, 29, tzinfo=UTC),
            merchant_name="Amazon",
            total_gross_cents=163952,
            discount_total_cents=0,
            currency="EUR",
            raw_payload={
                "source_record_ref": "306-4659501-3303528",
                "source_record_detail": {
                    "totalGross": 1639.52,
                    "subtotals": [
                        {"label": "Summe:", "amount": 1639.52, "category": "order_total"},
                        {"label": "Gutschein eingelöst:", "amount": -17.95, "category": "coupon"},
                        {"label": "Gesamtsumme:", "amount": 1621.57, "category": "order_total"},
                        {"label": "Summe der Erstattung", "amount": 62.0, "category": "refund_info"},
                    ],
                    "paymentAdjustments": [
                        {"type": "payment_adjustment", "subkind": "store_credit", "amount_cents": 1795, "label": "Gutschein eingelöst:"}
                    ],
                    "originalOrder": {"totalAmount": 1621.57},
                },
                "connector_normalized": {"id": "amazon-306-4659501-3303528", "total_gross_cents": 163952},
            },
        )
        transaction.items.append(
            TransactionItem(
                line_no=1,
                name="Camera",
                qty=Decimal("1"),
                line_total_cents=163952,
                category="electronics",
            )
        )
        session.add(transaction)

    with session_scope(sessions) as session:
        result = recalculate_amazon_transaction_financials(session)
        assert result.scanned == 1
        assert result.updated == 1

    with session_scope(sessions) as session:
        rows = session.query(Transaction).filter_by(source_id="amazon_de").all()
        assert len(rows) == 1
        transaction = rows[0]
        assert transaction.total_gross_cents == 155957
        assert transaction.items[0].line_total_cents == 163952
        assert transaction.raw_payload["source_record_detail"]["amazonFinancials"]["refund_total_cents"] == 6200
        summary_total = session.execute(
            select(func.coalesce(func.sum(Transaction.total_gross_cents), 0)).where(
                Transaction.source_id == "amazon_de"
            )
        ).scalar_one()
        assert summary_total == 155957
