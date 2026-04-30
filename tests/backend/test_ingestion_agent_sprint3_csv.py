from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from lidltool.auth.users import create_local_user
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import IngestionProposal, StatementRow, Transaction
from lidltool.ingest.manual_ingest import ManualIngestService, ManualTransactionInput
from lidltool.ingestion_agent import IngestionAgentService


def _build_sessions(tmp_path: Path):
    db_path = (tmp_path / "lidltool.sqlite").resolve()
    db_url = f"sqlite:///{db_path}"
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    return engine, session_factory(engine)


def _create_user(sessions) -> str:
    with session_scope(sessions) as session:
        user = create_local_user(
            session,
            username="csv-admin",
            password="test-password",
            display_name="CSV Admin",
            is_admin=True,
        )
        return user.user_id


def _seed_amazon(sessions, *, user_id: str) -> None:
    ManualIngestService(session_factory=sessions).ingest_transaction(
        payload=ManualTransactionInput(
            purchased_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
            merchant_name="Amazon Marketplace",
            total_gross_cents=2599,
            source_id="amazon_de",
            source_kind="connector",
            source_display_name="Amazon DE",
            source_account_ref="amazon",
            source_transaction_id="amazon-order-csv",
            user_id=user_id,
            currency="EUR",
            raw_payload={"fixture": "csv"},
            ingest_channel="test",
        ),
        actor_type="system",
        actor_id=None,
        audit_action="transaction.test_seeded",
    )


def _seed_lidl(sessions, *, user_id: str) -> None:
    ManualIngestService(session_factory=sessions).ingest_transaction(
        payload=ManualTransactionInput(
            purchased_at=datetime(2026, 4, 27, 12, 0, tzinfo=UTC),
            merchant_name="Lidl Isenbüttel",
            total_gross_cents=1615,
            source_id="lidl_plus_de",
            source_kind="connector",
            source_display_name="Lidl Plus DE",
            source_account_ref="lidl",
            source_transaction_id="lidl-receipt-match",
            user_id=user_id,
            currency="EUR",
            raw_payload={"fixture": "lidl"},
            ingest_channel="test",
        ),
        actor_type="system",
        actor_id=None,
        audit_action="transaction.test_seeded",
    )


def test_csv_rows_are_staged_as_raw_cells_without_parser_semantics(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    _seed_amazon(sessions, user_id=user_id)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="csv")
    csv_text = (
        "Date,Payee,Description,Amount,Currency\n"
        "2026-04-30,Amazon Marketplace,Order,-25.99,EUR\n"
        "2026-04-30,Ice Cream Store,Cash,-5.50,EUR\n"
    )
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=csv_text.encode("utf-8"),
        file_name="bank.csv",
        mime_type="text/csv",
    )

    parsed = service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)
    assert parsed["count"] == 3
    assert parsed["items"][0]["raw_json"]["parser_mode"] == "raw_table_row"
    assert parsed["items"][1]["raw_json"]["cells"] == ["2026-04-30", "Amazon Marketplace", "Order", "-25.99", "EUR"]
    assert parsed["items"][1]["amount_cents"] is None
    assert parsed["items"][1]["payee"] is None
    classified = service.classify_rows(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    assert classified["count"] == 3

    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(StatementRow.id))) == 3
        assert session.scalar(select(func.count(Transaction.id))) == 1
        proposals = [
            {"type": proposal.type, "payload_json": proposal.payload_json}
            for proposal in session.execute(select(IngestionProposal).order_by(IngestionProposal.created_at.asc())).scalars()
        ]
    assert [proposal["type"] for proposal in proposals] == ["ignore", "already_covered", "create_transaction"]
    assert proposals[0]["payload_json"]["reason"].startswith("Bank-Metadaten")
    assert proposals[1]["payload_json"]["transaction_id"]
    assert proposals[2]["payload_json"]["merchant_name"] == "Ice Cream Store"
    assert proposals[2]["payload_json"]["total_gross_cents"] == 550
    assert proposals[2]["payload_json"]["confidence"] < 0.7
    engine.dispose()


def test_create_transaction_proposal_auto_marks_existing_match_before_review(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    _seed_amazon(sessions, user_id=user_id)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="csv")

    proposal = service.create_proposal(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
        payload={
            "type": "create_transaction",
            "purchased_at": "2026-04-30T12:00:00+00:00",
            "merchant_name": "Amazon Marketplace",
            "total_gross_cents": 2599,
            "currency": "EUR",
            "source_id": "agent_ingest",
            "source_display_name": "Agent Ingestion",
            "source_account_ref": "bank_statement",
            "source_transaction_id": None,
            "idempotency_key": "test-amazon-match",
            "confidence": 0.9,
            "items": [],
            "discounts": [],
            "raw_payload": {"input_kind": "statement_row"},
        },
    )

    assert proposal["type"] == "already_covered"
    assert proposal["payload_json"]["transaction_id"]
    assert proposal["payload_json"]["match_score"] >= 0.9
    engine.dispose()


def test_lidl_bank_row_auto_marks_existing_connector_match_from_raw_evidence(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    _seed_lidl(sessions, user_id=user_id)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="csv")

    proposal = service.create_proposal(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
        payload={
            "type": "create_transaction",
            "purchased_at": "2026-04-29T00:00:00+00:00",
            "merchant_name": "S. Payment Solutions GmbH",
            "total_gross_cents": 1615,
            "direction": "outflow",
            "ledger_scope": "household",
            "dashboard_include": True,
            "currency": "EUR",
            "source_id": "agent_ingest",
            "source_display_name": "Agent Ingestion",
            "source_account_ref": "bank_statement",
            "source_transaction_id": None,
            "idempotency_key": "test-lidl-raw-evidence-match",
            "confidence": 0.58,
            "items": [],
            "discounts": [],
            "raw_payload": {
                "input_kind": "statement_row",
                "evidence": "Lidl sagt Danke DE501883007399117261 Lidl Pay",
            },
        },
    )

    assert proposal["type"] == "already_covered"
    assert proposal["payload_json"]["match_score"] >= 0.9
    engine.dispose()


def test_pasted_german_table_parses_amount_conventions(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None)
    pasted = "Buchungstag;Empfänger;Verwendungszweck;Betrag;Währung\n30.04.2026;Bäckerei;Frühstück;-4,20;EUR\n"

    parsed = service.parse_pasted_table(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        text=pasted,
    )

    assert parsed["count"] == 2
    assert parsed["items"][1]["raw_json"]["cells"] == ["30.04.2026", "Bäckerei", "Frühstück", "-4,20", "EUR"]
    assert parsed["items"][1]["amount_cents"] is None
    assert parsed["items"][1]["payee"] is None
    engine.dispose()


def test_german_bank_export_with_preamble_finds_statement_header(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="csv")
    csv_text = (
        '"Girokonto";"DE00123456781234567890"\n'
        '"Zeitraum:";"01.01.2024 - 30.04.2026"\n'
        '"Kontostand vom 30.04.2026:";"5.417,44 €"\n'
        '""\n'
        '"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";"Zahlungsempfänger*in";'
        '"Verwendungszweck";"Umsatztyp";"IBAN";"Betrag (€)";"Gläubiger-ID";"Mandatsreferenz";"Kundenreferenz"\n'
        '"30.04.26";"30.04.26";"Gebucht";"";"Eisladen";"Karte";"Kartenzahlung";"";"-25,00";"";"";""\n'
    )
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=csv_text.encode("utf-8-sig"),
        file_name="bank-export.csv",
        mime_type="text/csv",
    )

    parsed = service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)

    assert parsed["count"] == 5
    data_row = parsed["items"][-1]
    assert data_row["raw_json"]["cells"][4] == "Eisladen"
    assert data_row["raw_json"]["cells"][8] == "-25,00"
    assert data_row["amount_cents"] is None
    assert data_row["payee"] is None
    assert data_row["occurred_at"] is None
    engine.dispose()


def test_german_bank_export_keeps_sender_recipient_for_model_interpretation(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="csv")
    csv_text = (
        '"Buchungsdatum";"Zahlungspflichtige*r";"Zahlungsempfänger*in";"Verwendungszweck";"Betrag (€)"\n'
        '"30.04.26";"Max Mustermann";"Eisladen";"Kartenzahlung";"-25,00"\n'
        '"30.04.26";"Arbeitgeber GmbH";"Max Mustermann";"Gehalt";"2500,00"\n'
    )
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=csv_text.encode("utf-8-sig"),
        file_name="bank-export.csv",
        mime_type="text/csv",
    )

    parsed = service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)

    assert parsed["count"] == 3
    outgoing = parsed["items"][1]
    incoming = parsed["items"][2]
    assert outgoing["raw_json"]["cells"] == ["30.04.26", "Max Mustermann", "Eisladen", "Kartenzahlung", "-25,00"]
    assert incoming["raw_json"]["cells"] == ["30.04.26", "Arbeitgeber GmbH", "Max Mustermann", "Gehalt", "2500,00"]
    assert outgoing["payee"] is None
    assert incoming["payee"] is None
    engine.dispose()


def test_raw_bank_fallback_shows_inflow_context_in_review_proposal(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="csv")
    csv_text = (
        '"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";"Zahlungsempfänger*in";'
        '"Verwendungszweck";"Umsatztyp";"IBAN";"Betrag (€)"\n'
        '"28.04.26";"28.04.26";"Gebucht";"RUHRMEDIC GMBH";"BLUECHER MAXIMILIAN";'
        '"LOHN / GEHALT 04/26";"Eingang";"DE51533500000000116033";"2.608,14"\n'
    )
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=csv_text.encode("utf-8-sig"),
        file_name="salary.csv",
        mime_type="text/csv",
    )
    service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)

    classified = service.classify_rows(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )

    assert classified["count"] == 2
    review = classified["items"][1]
    assert review["type"] == "create_cashflow_entry"
    assert review["payload_json"]["direction"] == "inflow"
    assert review["payload_json"]["description"] == "RUHRMEDIC GMBH"
    assert review["payload_json"]["amount_cents"] == 260814
    assert review["payload_json"]["confidence"] < 0.7
    assert review["model_metadata_json"]["strategy"] == "generic_header_fallback_after_model"
    engine.dispose()


def test_raw_bank_fallback_uses_amount_column_not_payment_reference(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="csv")
    csv_text = (
        '"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";"Zahlungsempfänger*in";'
        '"Verwendungszweck";"Umsatztyp";"IBAN";"Betrag (€)";"Gläubiger-ID";"Mandatsreferenz";"Kundenreferenz"\n'
        '"14.04.26";"14.04.26";"Gebucht";"MAXIMILIAN BLUCHER Ahornring 54";'
        '"PayPal Europe S.a.r.l. et Cie S.C.A 22-24 Boulevard Royal, 2449 Luxembourg";'
        '"1049576623499/. Klinikum Braunschweig , Ihr Einkauf bei Klinikum Braunschweig";'
        '"Ausgang";"LU89751000135104200E";"-2,5";"LU96ZZZ0000000000000000058";"4J8J224Y4YESU";"1049576623499"\n'
    )
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=csv_text.encode("utf-8-sig"),
        file_name="paypal.csv",
        mime_type="text/csv",
    )
    service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)

    classified = service.classify_rows(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )

    proposal = classified["items"][1]
    assert proposal["type"] == "create_transaction"
    assert proposal["payload_json"]["direction"] == "outflow"
    assert proposal["payload_json"]["merchant_name"] == "Klinikum Braunschweig"
    assert proposal["payload_json"]["total_gross_cents"] == 250
    assert proposal["payload_json"]["confidence"] < 0.7
    engine.dispose()


def test_raw_bank_fallback_without_header_does_not_create_transaction(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="csv")
    csv_text = '"14.04.26";"MAXIMILIAN BLUCHER";"1049576623499/. Klinikum";"Ausgang";"-2,5";"1049576623499"\n'
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=csv_text.encode("utf-8-sig"),
        file_name="headerless.csv",
        mime_type="text/csv",
    )
    service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)

    classified = service.classify_rows(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )

    proposal = classified["items"][0]
    assert proposal["type"] == "needs_review"
    assert proposal["payload_json"]["amount_cents"] is None
    assert proposal["model_metadata_json"]["strategy"] == "generic_header_fallback_after_model"
    engine.dispose()
