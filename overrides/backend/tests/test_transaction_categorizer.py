from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lidltool.analytics.finance_taxonomy import ensure_finance_taxonomy
from lidltool.analytics.transaction_categorizer import (
    apply_transaction_category,
    categorize_transaction,
    learn_finance_category_rule,
)
from lidltool.db.models import Base, FinanceCategoryRule, Source, Transaction


def test_credit_keyword_maps_to_credit_repayment() -> None:
    result = categorize_transaction(
        merchant_name="Kredit Rate",
        source_id="manual",
        source_kind="bank",
        total_gross_cents=35000,
    )

    assert result.direction == "outflow"
    assert result.category_id == "credit:repayment"
    assert "debt" in result.tags


def test_getsafe_maps_to_insurance() -> None:
    result = categorize_transaction(
        merchant_name="Getsafe Digital GmbH",
        source_id="bank",
        source_kind="bank",
        total_gross_cents=799,
    )

    assert result.direction == "outflow"
    assert result.category_id == "insurance:liability"


def test_common_other_merchants_map_to_specific_categories() -> None:
    examples = {
        "Catapult Magazine": "subscriptions:news",
        "Swift": "subscriptions:fitness",
        "Amazon Marketplace": "shopping:online_retail",
        "Substack": "education:publications",
        "DM": "personal_care:drugstore",
        "dm-drogerie markt": "personal_care:drugstore",
        "Rossmann": "personal_care:drugstore",
        "Bahnhof Kiosk": "shopping:convenience",
    }

    for merchant_name, category_id in examples.items():
        result = categorize_transaction(
            merchant_name=merchant_name,
            source_id="bank",
            source_kind="bank",
            total_gross_cents=999,
        )

        assert result.direction == "outflow"
        assert result.category_id == category_id


def test_investment_transfer_is_transfer_not_portfolio_performance() -> None:
    result = categorize_transaction(
        merchant_name="Trade Republic Sparplan",
        source_id="bank",
        source_kind="bank",
        total_gross_cents=10000,
    )

    assert result.direction == "transfer"
    assert result.category_id == "investment:broker_transfer"
    assert "investment" in result.tags


def test_learned_merchant_rule_reuses_getsafe_insurance_without_model() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        ensure_finance_taxonomy(session)
        session.add(Source(id="bank", kind="bank", display_name="Bank"))
        first = Transaction(
            source_id="bank",
            source_transaction_id="getsafe-2026-01",
            purchased_at=datetime(2026, 1, 1, tzinfo=UTC),
            merchant_name="Getsafe Digital GmbH",
            total_gross_cents=799,
            direction="outflow",
            finance_category_id="insurance:liability",
            finance_category_method="model",
        )
        session.add(first)
        session.flush()

        rule = learn_finance_category_rule(session, transaction=first, source="model", confidence=0.95)
        assert rule is not None

        second = Transaction(
            source_id="bank",
            source_transaction_id="getsafe-2026-02",
            purchased_at=datetime(2026, 2, 1, tzinfo=UTC),
            merchant_name="GETSAFE DIGITAL GMBH",
            total_gross_cents=799,
        )
        session.add(second)
        session.flush()

        result = apply_transaction_category(second, session=session)

        assert result.category_id == "insurance:liability"
        assert result.method == "learned_rule"
        assert second.finance_category_id == "insurance:liability"
        assert second.finance_category_method == "learned_rule"
        saved_rule = session.execute(select(FinanceCategoryRule)).scalar_one()
        assert saved_rule.hit_count == 1


def test_short_learned_merchant_rule_requires_exact_match() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        ensure_finance_taxonomy(session)
        session.add(Source(id="bank", kind="bank", display_name="Bank"))
        dm = Transaction(
            source_id="bank",
            source_transaction_id="dm-2026-01",
            purchased_at=datetime(2026, 1, 1, tzinfo=UTC),
            merchant_name="DM",
            total_gross_cents=1299,
            direction="outflow",
            finance_category_id="personal_care:drugstore",
            finance_category_method="manual",
        )
        session.add(dm)
        session.flush()
        rule = learn_finance_category_rule(session, transaction=dm, source="manual", confidence=1)
        assert rule is not None

        random = Transaction(
            source_id="bank",
            source_transaction_id="random-2026-01",
            purchased_at=datetime(2026, 1, 2, tzinfo=UTC),
            merchant_name="Random Store",
            total_gross_cents=1999,
        )
        session.add(random)
        session.flush()

        result = apply_transaction_category(random, session=session)

        assert result.category_id == "other"
        assert result.method == "fallback"


def test_specific_deterministic_rule_refines_old_model_learned_rule() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        ensure_finance_taxonomy(session)
        session.add(Source(id="bank", kind="bank", display_name="Bank"))
        session.add(
            FinanceCategoryRule(
                rule_type="merchant",
                pattern="Substack",
                normalized_pattern="substack",
                category_id="subscriptions:news",
                direction="outflow",
                source="model",
                confidence=0.8,
                enabled=True,
            )
        )
        transaction = Transaction(
            source_id="bank",
            source_transaction_id="substack-2026-01",
            purchased_at=datetime(2026, 1, 1, tzinfo=UTC),
            merchant_name="Substack",
            total_gross_cents=500,
        )
        session.add(transaction)
        session.flush()

        result = apply_transaction_category(transaction, session=session)

        assert result.category_id == "education:publications"
        assert result.method == "rule"
