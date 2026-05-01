from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from lidltool.amazon.order_money import normalize_order_financials
from lidltool.amazon.recalc import (
    AMAZON_FINANCIAL_RECALC_VERSION,
    recalculate_amazon_transaction_financials,
)
from lidltool.config import AppConfig
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import ConnectorConfigState, Source, Transaction, TransactionItem, User
from lidltool.ingest.sync import SyncService
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


def _legacy_amazon_raw_payload(*, gross: float = 1639.52, final: float = 1621.57, refund: float = 62.0) -> dict:
    return {
        "source_record_ref": "306-4659501-3303528",
        "source_record_detail": {
            "totalGross": gross,
            "subtotals": [
                {"label": "Summe:", "amount": gross, "category": "order_total"},
                {"label": "Gutschein eingelöst:", "amount": round(gross - final, 2), "category": "coupon"},
                {"label": "Gesamtsumme:", "amount": final, "category": "order_total"},
                {"label": "Summe der Erstattung", "amount": refund, "category": "refund_info"},
            ],
            "paymentAdjustments": [
                {"type": "payment_adjustment", "subkind": "store_credit", "amount_cents": int(round((gross - final) * 100)), "label": "Gutschein eingelöst:"}
            ],
            "originalOrder": {"totalAmount": final},
        },
        "connector_normalized": {"id": "amazon-306-4659501-3303528", "total_gross_cents": int(round(gross * 100))},
    }


def _build_sessions(tmp_path: Path):
    db_path = (tmp_path / "lidltool.sqlite").resolve()
    db_url = f"sqlite:///{db_path}"
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    return engine, session_factory(engine)


def _add_source(session, source_id: str, *, user_id: str = "user-a") -> Source:
    _add_user(session, user_id)
    source = Source(
        id=source_id,
        user_id=user_id,
        kind="connector",
        display_name="Amazon",
        status="healthy",
        enabled=True,
        reporting_role="spending_only",
    )
    session.add(source)
    return source


def _add_user(session, user_id: str) -> User:
    for pending in session.new:
        if isinstance(pending, User) and pending.user_id == user_id:
            return pending
    existing = session.get(User, user_id)
    if existing is not None:
        return existing
    user = User(
        user_id=user_id,
        username=user_id,
        password_hash="test",
        is_admin=False,
    )
    session.add(user)
    return user


def _add_amazon_transaction(
    session,
    *,
    source_id: str = "amazon_de",
    user_id: str = "user-a",
    transaction_id: str = "tx-amazon",
    source_transaction_id: str = "amazon-306-4659501-3303528",
    total_gross_cents: int = 163952,
    raw_payload: dict | None = None,
) -> Transaction:
    _add_user(session, user_id)
    transaction = Transaction(
        id=transaction_id,
        source_id=source_id,
        user_id=user_id,
        source_transaction_id=source_transaction_id,
        purchased_at=datetime(2020, 10, 29, tzinfo=UTC),
        merchant_name="Amazon",
        total_gross_cents=total_gross_cents,
        discount_total_cents=0,
        currency="EUR",
        raw_payload=raw_payload if raw_payload is not None else _legacy_amazon_raw_payload(),
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
    return transaction


class _NoRecordAmazonConnector:
    def authenticate(self) -> dict:
        return {"authenticated": True}

    def refresh_auth(self) -> dict:
        return {"refreshed": True}

    def healthcheck(self) -> dict:
        return {"healthy": True}

    def discover_new_records(self) -> list[str]:
        return []

    def fetch_record_detail(self, record_ref: str) -> dict:
        raise AssertionError("no records should be fetched")

    def normalize(self, record_detail: dict) -> dict:
        raise AssertionError("no records should be normalized")

    def extract_discounts(self, record_detail: dict) -> list[dict]:
        raise AssertionError("no discounts should be extracted")


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
    engine, sessions = _build_sessions(tmp_path)

    with session_scope(sessions) as session:
        _add_source(session, "amazon_de")
        _add_amazon_transaction(session)

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


def test_amazon_recalc_scopes_by_source(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    with session_scope(sessions) as session:
        _add_source(session, "amazon_de")
        _add_source(session, "amazon_fr")
        _add_amazon_transaction(session, source_id="amazon_de", transaction_id="tx-de")
        _add_amazon_transaction(
            session,
            source_id="amazon_fr",
            transaction_id="tx-fr",
            source_transaction_id="amazon-fr-1",
        )

    with session_scope(sessions) as session:
        result = recalculate_amazon_transaction_financials(session, source_id="amazon_de")
        assert result.updated == 1

    with session_scope(sessions) as session:
        assert session.get(Transaction, "tx-de").total_gross_cents == 155957
        assert session.get(Transaction, "tx-fr").total_gross_cents == 163952


def test_amazon_recalc_scopes_by_user(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    with session_scope(sessions) as session:
        _add_source(session, "amazon_de", user_id="user-a")
        _add_amazon_transaction(session, transaction_id="tx-a", user_id="user-a")
        _add_amazon_transaction(
            session,
            transaction_id="tx-b",
            user_id="user-b",
            source_transaction_id="amazon-user-b",
        )

    with session_scope(sessions) as session:
        result = recalculate_amazon_transaction_financials(
            session,
            source_id="amazon_de",
            user_id="user-a",
        )
        assert result.updated == 1

    with session_scope(sessions) as session:
        assert session.get(Transaction, "tx-a").total_gross_cents == 155957
        assert session.get(Transaction, "tx-b").total_gross_cents == 163952


def test_amazon_recalc_skips_missing_raw_payload_with_warning(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    with session_scope(sessions) as session:
        _add_source(session, "amazon_de")
        _add_amazon_transaction(session, raw_payload={}, total_gross_cents=12345)

    with session_scope(sessions) as session:
        result = recalculate_amazon_transaction_financials(session, source_id="amazon_de")
        assert result.skipped == 1
        assert result.updated == 0
        assert "missing Amazon raw payload" in result.warnings[0]
        assert session.get(Transaction, "tx-amazon").total_gross_cents == 12345


def test_amazon_sync_lifecycle_runs_scoped_recalc_and_sets_marker(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    with session_scope(sessions) as session:
        _add_source(session, "amazon_de", user_id="user-a")
        _add_amazon_transaction(session, user_id="user-a")

    service = SyncService(
        client=None,
        session_factory=sessions,
        config=AppConfig(source="amazon_de", db_path=tmp_path / "lidltool.sqlite"),
        connector=_NoRecordAmazonConnector(),
        owner_user_id="user-a",
    )
    first = service.sync(full=True)
    second = service.sync(full=True)

    with session_scope(sessions) as session:
        rows = session.query(Transaction).filter_by(source_id="amazon_de").all()
        assert len(rows) == 1
        assert rows[0].total_gross_cents == 155957
        assert rows[0].items[0].line_total_cents == 163952
        marker = session.get(ConnectorConfigState, "amazon_de")
        assert marker is not None
        assert marker.public_config_json["_amazon_financial_recalc_version"] == AMAZON_FINANCIAL_RECALC_VERSION

    assert first.metadata["amazon_financial_recalc"]["updated"] == 1
    assert first.metadata["amazon_financial_recalc"]["scanned"] == 1
    assert second.metadata["amazon_financial_recalc"]["updated"] == 0
    assert second.metadata["amazon_financial_recalc"]["skipped_reason"] == "marker_current"
