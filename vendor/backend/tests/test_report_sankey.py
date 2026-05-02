from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lidltool.analytics.scope import VisibilityContext
from lidltool.db.models import Base, CashflowEntry, Source, Transaction, TransactionItem, User
from lidltool.reports.service import (
    OTHER_MERCHANT_ID,
    OTHER_OUTFLOW_CATEGORY_ID,
    SYNTHETIC_INFLOW_BUCKET_ID,
    build_report_sankey,
)


def _session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_build_report_sankey_combined_mode_allocates_period_inflows_proportionally() -> None:
    Session = _session_factory()
    user_id = "sankey-combined-user"
    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add_all(
            [
                Source(id="bank", user_id=user_id, kind="agent", display_name="Bank"),
                Source(id="wallet", user_id=user_id, kind="agent", display_name="Wallet"),
            ]
        )
        session.add_all(
            [
                Transaction(
                    id="salary-april",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="salary-april",
                    purchased_at=datetime(2026, 4, 1, 8, tzinfo=timezone.utc),
                    merchant_name="Employer",
                    total_gross_cents=4_000,
                    discount_total_cents=0,
                    direction="inflow",
                    finance_category_id="income:salary",
                ),
                Transaction(
                    id="groceries-april",
                    source_id="wallet",
                    user_id=user_id,
                    source_transaction_id="groceries-april",
                    purchased_at=datetime(2026, 4, 3, 18, tzinfo=timezone.utc),
                    merchant_name="Lidl",
                    total_gross_cents=3_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="groceries",
                ),
                Transaction(
                    id="utilities-april",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="utilities-april",
                    purchased_at=datetime(2026, 4, 5, 10, tzinfo=timezone.utc),
                    merchant_name="Vattenfall",
                    total_gross_cents=3_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="utilities",
                ),
            ]
        )
        session.add(
            CashflowEntry(
                id="manual-bonus",
                user_id=user_id,
                effective_date=date(2026, 4, 2),
                direction="inflow",
                category="manual_bonus",
                amount_cents=2_000,
                currency="EUR",
                source_type="manual",
            )
        )
        session.commit()

        result = build_report_sankey(
            session,
            user_id=user_id,
            visibility=VisibilityContext(user_id=user_id, is_service=False),
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            mode="combined",
            top_n=8,
        )

    links = {
        (link["source"], link["target"]): link["value_cents"]
        for link in result["links"]
    }
    nodes = {node["id"]: node for node in result["nodes"]}

    assert result["mode"] == "combined"
    assert result["breakdown"] == "merchant"
    assert result["model"]["kind"] == "period_proportional_inflow_to_outflow_category_merchant"
    assert result["summary"]["total_outflow_cents"] == 6_000
    assert result["summary"]["total_inflow_basis_cents"] == 6_000
    assert result["flags"]["synthetic_inflow_bucket"] is False
    assert links[("inflow:income:salary", "category:groceries")] == 2_000
    assert links[("inflow:manual_bonus", "category:groceries")] == 1_000
    assert links[("inflow:income:salary", "category:utilities")] == 2_000
    assert links[("inflow:manual_bonus", "category:utilities")] == 1_000
    assert links[("category:groceries", "merchant:Lidl")] == 3_000
    assert links[("category:utilities", "merchant:Vattenfall")] == 3_000
    assert nodes["inflow:income:salary"]["basis_amount_cents"] == 4_000
    assert nodes["inflow:manual_bonus"]["basis_amount_cents"] == 2_000


def test_build_report_sankey_uses_synthetic_inflow_bucket_when_source_filters_exclude_manual_basis() -> None:
    Session = _session_factory()
    user_id = "sankey-synthetic-user"
    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add(Source(id="wallet", user_id=user_id, kind="agent", display_name="Wallet"))
        session.add(
            Transaction(
                id="groceries-wallet",
                source_id="wallet",
                user_id=user_id,
                source_transaction_id="groceries-wallet",
                purchased_at=datetime(2026, 4, 3, 18, tzinfo=timezone.utc),
                merchant_name="Lidl",
                total_gross_cents=3_250,
                discount_total_cents=0,
                direction="outflow",
                finance_category_id="groceries",
            )
        )
        session.add(
            CashflowEntry(
                id="manual-salary",
                user_id=user_id,
                effective_date=date(2026, 4, 1),
                direction="inflow",
                category="salary_manual",
                amount_cents=5_000,
                currency="EUR",
                source_type="manual",
            )
        )
        session.commit()

        result = build_report_sankey(
            session,
            user_id=user_id,
            visibility=VisibilityContext(user_id=user_id, is_service=False),
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            source_ids=["wallet"],
            mode="combined",
            breakdown="merchant",
            top_n=8,
        )

    nodes = {node["id"]: node for node in result["nodes"]}
    links = {
        (link["source"], link["target"]): link["value_cents"]
        for link in result["links"]
    }

    assert result["flags"]["manual_inflows_excluded_by_source_filter"] is True
    assert result["flags"]["synthetic_inflow_bucket"] is True
    assert result["summary"]["total_inflow_basis_cents"] == 0
    assert SYNTHETIC_INFLOW_BUCKET_ID in nodes
    assert nodes[SYNTHETIC_INFLOW_BUCKET_ID]["label"] == "Unattributed period inflow"
    assert links[(SYNTHETIC_INFLOW_BUCKET_ID, "category:groceries")] == 3_250


def test_build_report_sankey_outflow_only_aggregates_extra_categories_and_merchants() -> None:
    Session = _session_factory()
    user_id = "sankey-outflow-user"
    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add(Source(id="bank", user_id=user_id, kind="agent", display_name="Bank"))
        session.add_all(
            [
                Transaction(
                    id="txn-1",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-1",
                    purchased_at=datetime(2026, 4, 1, 9, tzinfo=timezone.utc),
                    merchant_name="Merchant 1",
                    total_gross_cents=10_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="cat-1",
                ),
                Transaction(
                    id="txn-2",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-2",
                    purchased_at=datetime(2026, 4, 2, 9, tzinfo=timezone.utc),
                    merchant_name="Merchant 2",
                    total_gross_cents=9_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="cat-2",
                ),
                Transaction(
                    id="txn-3",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-3",
                    purchased_at=datetime(2026, 4, 3, 9, tzinfo=timezone.utc),
                    merchant_name="Merchant 3",
                    total_gross_cents=8_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="cat-3",
                ),
                Transaction(
                    id="txn-4",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-4",
                    purchased_at=datetime(2026, 4, 4, 9, tzinfo=timezone.utc),
                    merchant_name="Merchant 4",
                    total_gross_cents=7_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="cat-4",
                ),
                Transaction(
                    id="txn-5",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-5",
                    purchased_at=datetime(2026, 4, 5, 9, tzinfo=timezone.utc),
                    merchant_name="Merchant 5",
                    total_gross_cents=6_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="cat-5",
                ),
                Transaction(
                    id="txn-6",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-6",
                    purchased_at=datetime(2026, 4, 6, 9, tzinfo=timezone.utc),
                    merchant_name="Merchant 6",
                    total_gross_cents=5_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="cat-1",
                ),
                Transaction(
                    id="txn-7",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-7",
                    purchased_at=datetime(2026, 4, 7, 9, tzinfo=timezone.utc),
                    merchant_name="Merchant 7",
                    total_gross_cents=4_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="cat-2",
                ),
                Transaction(
                    id="txn-8",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-8",
                    purchased_at=datetime(2026, 4, 8, 9, tzinfo=timezone.utc),
                    merchant_name="Merchant 8",
                    total_gross_cents=3_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="cat-3",
                ),
                Transaction(
                    id="txn-9",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-9",
                    purchased_at=datetime(2026, 4, 9, 9, tzinfo=timezone.utc),
                    merchant_name="Merchant 9",
                    total_gross_cents=2_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="cat-5",
                ),
            ]
        )
        session.commit()

        result = build_report_sankey(
            session,
            user_id=user_id,
            visibility=VisibilityContext(user_id=user_id, is_service=False),
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            mode="outflow_only",
            top_n=4,
        )

    node_ids = {node["id"] for node in result["nodes"]}
    links = {
        (link["source"], link["target"]): link["value_cents"]
        for link in result["links"]
    }

    assert result["mode"] == "outflow_only"
    assert result["breakdown"] == "merchant"
    assert result["model"]["kind"] == "outflow_category_to_merchant"
    assert result["flags"]["aggregated_categories"] is True
    assert result["flags"]["aggregated_merchants"] is True
    assert OTHER_OUTFLOW_CATEGORY_ID in node_ids
    assert OTHER_MERCHANT_ID in node_ids
    assert links[(OTHER_OUTFLOW_CATEGORY_ID, "merchant:Merchant 4")] == 7_000
    assert links[("category:cat-5", OTHER_MERCHANT_ID)] == 2_000


def test_build_report_sankey_source_breakdown_uses_source_labels() -> None:
    Session = _session_factory()
    user_id = "sankey-source-user"
    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add_all(
            [
                Source(id="amazon_connector", user_id=user_id, kind="connector", display_name="Amazon Connector"),
                Source(id="agent_ingest", user_id=user_id, kind="agent", display_name="Agent Ingest Connector"),
                Source(id="bank", user_id=user_id, kind="agent", display_name="Bank"),
            ]
        )
        session.add_all(
            [
                Transaction(
                    id="salary-source",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="salary-source",
                    purchased_at=datetime(2026, 4, 1, 8, tzinfo=timezone.utc),
                    merchant_name="Employer",
                    total_gross_cents=10_000,
                    discount_total_cents=0,
                    direction="inflow",
                    finance_category_id="income:salary",
                ),
                Transaction(
                    id="txn-source-1",
                    source_id="amazon_connector",
                    user_id=user_id,
                    source_transaction_id="txn-source-1",
                    purchased_at=datetime(2026, 4, 1, 9, tzinfo=timezone.utc),
                    merchant_name="Amazon",
                    total_gross_cents=6_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="shopping:online_retail",
                ),
                Transaction(
                    id="txn-source-2",
                    source_id="agent_ingest",
                    user_id=user_id,
                    source_transaction_id="txn-source-2",
                    purchased_at=datetime(2026, 4, 2, 9, tzinfo=timezone.utc),
                    merchant_name="Manual Bill",
                    total_gross_cents=4_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="housing:utilities",
                ),
            ]
        )
        session.commit()

        result = build_report_sankey(
            session,
            user_id=user_id,
            visibility=VisibilityContext(user_id=user_id, is_service=False),
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            mode="combined",
            breakdown="source",
            top_n=8,
        )

    nodes = {node["id"]: node for node in result["nodes"]}
    links = {
        (link["source"], link["target"]): link["value_cents"]
        for link in result["links"]
    }

    assert result["breakdown"] == "source"
    assert result["model"]["kind"] == "period_proportional_inflow_to_outflow_category_source"
    assert nodes["source:amazon_connector"]["label"] == "Amazon Connector"
    assert nodes["source:agent_ingest"]["label"] == "Agent Ingest Connector"
    assert links[("category:shopping", "source:amazon_connector")] == 6_000
    assert links[("category:housing", "source:agent_ingest")] == 4_000


def test_build_report_sankey_subcategory_breakdown_adds_leaf_layer_before_merchants() -> None:
    Session = _session_factory()
    user_id = "sankey-subcategory-user"
    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add(Source(id="bank", user_id=user_id, kind="agent", display_name="Bank"))
        session.add_all(
            [
                Transaction(
                    id="salary-sub",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="salary-sub",
                    purchased_at=datetime(2026, 4, 1, 8, tzinfo=timezone.utc),
                    merchant_name="Employer",
                    total_gross_cents=8_000,
                    discount_total_cents=0,
                    direction="inflow",
                    finance_category_id="income:salary",
                ),
                Transaction(
                    id="txn-sub-1",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-sub-1",
                    purchased_at=datetime(2026, 4, 3, 8, tzinfo=timezone.utc),
                    merchant_name="Alnatura",
                    total_gross_cents=3_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="groceries",
                ),
                Transaction(
                    id="txn-sub-2",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-sub-2",
                    purchased_at=datetime(2026, 4, 4, 8, tzinfo=timezone.utc),
                    merchant_name="Edeka",
                    total_gross_cents=5_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="groceries",
                ),
            ]
        )
        session.add_all(
            [
                TransactionItem(
                    id="txn-sub-1-item-1",
                    transaction_id="txn-sub-1",
                    line_no=1,
                    name="Rinderhack",
                    qty=Decimal("1"),
                    unit="pack",
                    unit_price_cents=1_800,
                    line_total_cents=1_800,
                    category="groceries:meat",
                    category_id="groceries:meat",
                ),
                TransactionItem(
                    id="txn-sub-1-item-2",
                    transaction_id="txn-sub-1",
                    line_no=2,
                    name="Saft",
                    qty=Decimal("1"),
                    unit="bottle",
                    unit_price_cents=1_200,
                    line_total_cents=1_200,
                    category="groceries:beverages",
                    category_id="groceries:beverages",
                ),
                TransactionItem(
                    id="txn-sub-2-item-1",
                    transaction_id="txn-sub-2",
                    line_no=1,
                    name="Lachs",
                    qty=Decimal("1"),
                    unit="pack",
                    unit_price_cents=2_000,
                    line_total_cents=2_000,
                    category="groceries:fish",
                    category_id="groceries:fish",
                ),
                TransactionItem(
                    id="txn-sub-2-item-2",
                    transaction_id="txn-sub-2",
                    line_no=2,
                    name="Mineralwasser",
                    qty=Decimal("1"),
                    unit="crate",
                    unit_price_cents=3_000,
                    line_total_cents=3_000,
                    category="groceries:beverages",
                    category_id="groceries:beverages",
                ),
            ]
        )
        session.commit()

        result = build_report_sankey(
            session,
            user_id=user_id,
            visibility=VisibilityContext(user_id=user_id, is_service=False),
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            mode="combined",
            breakdown="subcategory",
            top_n=8,
        )

    nodes = {node["id"]: node for node in result["nodes"]}
    links = {
        (link["source"], link["target"]): link["value_cents"]
        for link in result["links"]
    }

    assert result["breakdown"] == "subcategory"
    assert result["model"]["kind"] == "period_proportional_inflow_to_outflow_category_subcategory_merchant"
    assert nodes["subcategory:groceries:meat"]["kind"] == "subcategory"
    assert nodes["subcategory:groceries:beverages"]["kind"] == "subcategory"
    assert nodes["subcategory:groceries:fish"]["kind"] == "subcategory"
    assert links[("category:groceries", "subcategory:groceries:meat")] == 1_800
    assert links[("category:groceries", "subcategory:groceries:beverages")] == 4_200
    assert links[("category:groceries", "subcategory:groceries:fish")] == 2_000
    assert links[("subcategory:groceries:meat", "merchant:Alnatura")] == 1_800
    assert links[("subcategory:groceries:beverages", "merchant:Alnatura")] == 1_200
    assert links[("subcategory:groceries:beverages", "merchant:Edeka")] == 3_000
    assert links[("subcategory:groceries:fish", "merchant:Edeka")] == 2_000


def test_build_report_sankey_subcategory_source_breakdown_adds_leaf_layer_before_sources() -> None:
    Session = _session_factory()
    user_id = "sankey-subcategory-source-user"
    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add_all(
            [
                Source(id="lidl_plus_de", user_id=user_id, kind="connector", display_name="Lidl Plus DE"),
                Source(id="manual_ingest", user_id=user_id, kind="agent", display_name="Manual Ingest"),
            ]
        )
        session.add_all(
            [
                Transaction(
                    id="salary-sub-source",
                    source_id="manual_ingest",
                    user_id=user_id,
                    source_transaction_id="salary-sub-source",
                    purchased_at=datetime(2026, 4, 1, 8, tzinfo=timezone.utc),
                    merchant_name="Employer",
                    total_gross_cents=8_000,
                    discount_total_cents=0,
                    direction="inflow",
                    finance_category_id="income:salary",
                ),
                Transaction(
                    id="txn-sub-source-1",
                    source_id="lidl_plus_de",
                    user_id=user_id,
                    source_transaction_id="txn-sub-source-1",
                    purchased_at=datetime(2026, 4, 3, 8, tzinfo=timezone.utc),
                    merchant_name="Lidl",
                    total_gross_cents=3_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="groceries",
                ),
                Transaction(
                    id="txn-sub-source-2",
                    source_id="manual_ingest",
                    user_id=user_id,
                    source_transaction_id="txn-sub-source-2",
                    purchased_at=datetime(2026, 4, 4, 8, tzinfo=timezone.utc),
                    merchant_name="Lidl",
                    total_gross_cents=5_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="groceries",
                ),
            ]
        )
        session.add_all(
            [
                TransactionItem(
                    id="txn-sub-source-1-item-1",
                    transaction_id="txn-sub-source-1",
                    line_no=1,
                    name="Rinderhack",
                    qty=Decimal("1"),
                    unit="pack",
                    unit_price_cents=1_800,
                    line_total_cents=1_800,
                    category="groceries:meat",
                    category_id="groceries:meat",
                ),
                TransactionItem(
                    id="txn-sub-source-1-item-2",
                    transaction_id="txn-sub-source-1",
                    line_no=2,
                    name="Saft",
                    qty=Decimal("1"),
                    unit="bottle",
                    unit_price_cents=1_200,
                    line_total_cents=1_200,
                    category="groceries:beverages",
                    category_id="groceries:beverages",
                ),
                TransactionItem(
                    id="txn-sub-source-2-item-1",
                    transaction_id="txn-sub-source-2",
                    line_no=1,
                    name="Lachs",
                    qty=Decimal("1"),
                    unit="pack",
                    unit_price_cents=2_000,
                    line_total_cents=2_000,
                    category="groceries:fish",
                    category_id="groceries:fish",
                ),
                TransactionItem(
                    id="txn-sub-source-2-item-2",
                    transaction_id="txn-sub-source-2",
                    line_no=2,
                    name="Mineralwasser",
                    qty=Decimal("1"),
                    unit="crate",
                    unit_price_cents=3_000,
                    line_total_cents=3_000,
                    category="groceries:beverages",
                    category_id="groceries:beverages",
                ),
            ]
        )
        session.commit()

        result = build_report_sankey(
            session,
            user_id=user_id,
            visibility=VisibilityContext(user_id=user_id, is_service=False),
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            mode="combined",
            breakdown="subcategory_source",
            top_n=8,
        )

    nodes = {node["id"]: node for node in result["nodes"]}
    links = {
        (link["source"], link["target"]): link["value_cents"]
        for link in result["links"]
    }

    assert result["breakdown"] == "subcategory_source"
    assert result["model"]["kind"] == "period_proportional_inflow_to_outflow_category_subcategory_source"
    assert nodes["subcategory:groceries:meat"]["kind"] == "subcategory"
    assert nodes["source:lidl_plus_de"]["kind"] == "source"
    assert nodes["source:manual_ingest"]["kind"] == "source"
    assert links[("category:groceries", "subcategory:groceries:meat")] == 1_800
    assert links[("category:groceries", "subcategory:groceries:beverages")] == 4_200
    assert links[("category:groceries", "subcategory:groceries:fish")] == 2_000
    assert links[("subcategory:groceries:meat", "source:lidl_plus_de")] == 1_800
    assert links[("subcategory:groceries:beverages", "source:lidl_plus_de")] == 1_200
    assert links[("subcategory:groceries:beverages", "source:manual_ingest")] == 3_000
    assert links[("subcategory:groceries:fish", "source:manual_ingest")] == 2_000


def test_build_report_sankey_subcategory_only_breakdown_stops_at_real_grocery_item_categories() -> None:
    Session = _session_factory()
    user_id = "sankey-subcategory-only-user"
    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add(Source(id="bank", user_id=user_id, kind="agent", display_name="Bank"))
        session.add_all(
            [
                Transaction(
                    id="salary-sub-only",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="salary-sub-only",
                    purchased_at=datetime(2026, 4, 1, 8, tzinfo=timezone.utc),
                    merchant_name="Employer",
                    total_gross_cents=6_000,
                    discount_total_cents=0,
                    direction="inflow",
                    finance_category_id="income:salary",
                ),
                Transaction(
                    id="txn-sub-only",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="txn-sub-only",
                    purchased_at=datetime(2026, 4, 3, 8, tzinfo=timezone.utc),
                    merchant_name="Lidl",
                    total_gross_cents=3_600,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="groceries",
                ),
            ]
        )
        session.add_all(
            [
                TransactionItem(
                    id="txn-sub-only-item-1",
                    transaction_id="txn-sub-only",
                    line_no=1,
                    name="Hähnchen",
                    qty=Decimal("1"),
                    unit="pack",
                    unit_price_cents=1_100,
                    line_total_cents=1_100,
                    category="groceries:meat",
                    category_id="groceries:meat",
                ),
                TransactionItem(
                    id="txn-sub-only-item-2",
                    transaction_id="txn-sub-only",
                    line_no=2,
                    name="Wasser",
                    qty=Decimal("1"),
                    unit="crate",
                    unit_price_cents=900,
                    line_total_cents=900,
                    category="groceries:beverages",
                    category_id="groceries:beverages",
                ),
                TransactionItem(
                    id="txn-sub-only-item-3",
                    transaction_id="txn-sub-only",
                    line_no=3,
                    name="Paprika",
                    qty=Decimal("1"),
                    unit="pack",
                    unit_price_cents=1_600,
                    line_total_cents=1_600,
                    category="groceries:produce",
                    category_id="groceries:produce",
                ),
            ]
        )
        session.commit()

        result = build_report_sankey(
            session,
            user_id=user_id,
            visibility=VisibilityContext(user_id=user_id, is_service=False),
            from_date=date(2026, 4, 1),
            to_date=date(2026, 4, 30),
            mode="combined",
            breakdown="subcategory_only",
            top_n=8,
        )

    node_ids = {node["id"] for node in result["nodes"]}
    link_kinds = {link["kind"] for link in result["links"]}
    links = {
        (link["source"], link["target"]): link["value_cents"]
        for link in result["links"]
    }

    assert result["breakdown"] == "subcategory_only"
    assert result["model"]["kind"] == "period_proportional_inflow_to_outflow_category_subcategory"
    assert "merchant:Lidl" not in node_ids
    assert link_kinds == {"period_proportional_attribution", "category_to_subcategory"}
    assert links[("category:groceries", "subcategory:groceries:meat")] == 1_100
    assert links[("category:groceries", "subcategory:groceries:beverages")] == 900
    assert links[("category:groceries", "subcategory:groceries:produce")] == 1_600
