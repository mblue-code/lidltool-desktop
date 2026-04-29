from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

DESKTOP_ROOT = Path(__file__).resolve().parents[2]
VENDOR_BACKEND_SRC = DESKTOP_ROOT / "vendor" / "backend" / "src"

if str(VENDOR_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_BACKEND_SRC))

from lidltool.config import AppConfig  # noqa: E402
from lidltool.db.engine import create_engine_for_url, migrate_db  # noqa: E402
from lidltool.ingest.sync import SyncService  # noqa: E402


class _FakeConnector:
    def authenticate(self) -> dict[str, bool]:
        return {"authenticated": True}

    def refresh_auth(self) -> dict[str, bool]:
        return {"refreshed": True}

    def healthcheck(self) -> dict[str, bool]:
        return {"healthy": True}

    def discover_new_records(self) -> list[str]:
        return ["bad-record", "good-record"]

    def fetch_record_detail(self, record_ref: str) -> dict[str, str]:
        return {"id": record_ref}

    def normalize(self, record_detail: dict[str, str]) -> dict[str, object]:
        if record_detail["id"] == "bad-record":
            raise RuntimeError("normalize_record failed: items must not be empty")
        return {
            "id": "good-record",
            "purchased_at": "2026-04-28T17:00:00+00:00",
            "store_id": "store-1",
            "store_name": "Lidl Test Store",
            "store_address": "Teststrasse 1",
            "total_gross_cents": 199,
            "currency": "EUR",
            "discount_total_cents": 0,
            "fingerprint": "good-record-fingerprint",
            "items": [
                {
                    "line_no": 1,
                    "name": "Item",
                    "qty": "1",
                    "unit": "pcs",
                    "unit_price_cents": 199,
                    "line_total_cents": 199,
                    "is_deposit": False,
                    "discounts": [],
                }
            ],
            "raw_json": {"id": "good-record"},
        }

    def extract_discounts(self, record_detail: dict[str, str]) -> list[dict[str, object]]:
        return []


class _AlwaysNormalizeConnector(_FakeConnector):
    def normalize(self, record_detail: dict[str, str]) -> dict[str, object]:
        record_id = record_detail["id"]
        return {
            "id": record_id,
            "purchased_at": "2026-04-28T17:00:00+00:00",
            "store_id": "store-1",
            "store_name": "Lidl Test Store",
            "store_address": "Teststrasse 1",
            "total_gross_cents": 199,
            "currency": "EUR",
            "discount_total_cents": 0,
            "fingerprint": f"{record_id}-fingerprint",
            "items": [
                {
                    "line_no": 1,
                    "name": "Item",
                    "qty": "1",
                    "unit": "pcs",
                    "unit_price_cents": 199,
                    "line_total_cents": 199,
                    "is_deposit": False,
                    "discounts": [],
                }
            ],
            "raw_json": {"id": record_id},
        }


class _EmptyItemsConnector(_FakeConnector):
    def normalize(self, record_detail: dict[str, str]) -> dict[str, object]:
        record_id = record_detail["id"]
        items: list[dict[str, object]]
        if record_id == "bad-record":
            items = []
        else:
            items = [
                {
                    "line_no": 1,
                    "name": "Item",
                    "qty": "1",
                    "unit": "pcs",
                    "unit_price_cents": 199,
                    "line_total_cents": 199,
                    "is_deposit": False,
                    "discounts": [],
                }
            ]
        return {
            "id": record_id,
            "purchased_at": "2026-04-28T17:00:00+00:00",
            "store_id": "store-1",
            "store_name": "Lidl Test Store",
            "store_address": "Teststrasse 1",
            "total_gross_cents": 199,
            "currency": "EUR",
            "discount_total_cents": 0,
            "fingerprint": f"{record_id}-fingerprint",
            "items": items,
            "raw_json": {"id": record_id},
        }


def _desktop_config(tmp_root: Path) -> AppConfig:
    config = AppConfig(
        db_path=tmp_root / "lidltool.sqlite",
        config_dir=tmp_root / "config",
        document_storage_path=tmp_root / "documents",
        credential_encryption_key="desktop-sync-resilience-secret-key-1234567890",
        desktop_mode=True,
        connector_live_sync_enabled=False,
        source="lidl_plus_de",
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.document_storage_path.mkdir(parents=True, exist_ok=True)
    return config


def _fake_normalized_receipt(record_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=record_id,
        purchased_at=datetime(2026, 4, 28, 17, 0, tzinfo=UTC),
        store_id="store-1",
        store_name="Lidl Test Store",
        store_address="Teststrasse 1",
        total_gross=199,
        currency="EUR",
        discount_total=0,
        fingerprint=f"{record_id}-fingerprint",
        raw_json={"id": record_id},
        items=[
            SimpleNamespace(
                line_no=1,
                name="Item",
                qty=Decimal("1"),
                unit="pcs",
                unit_price=199,
                line_total=199,
                vat_rate=None,
                category=None,
                discounts=[],
            )
        ],
    )


class LidlSyncResilienceTests(unittest.TestCase):
    def test_sync_quarantines_empty_item_payloads_and_continues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = _desktop_config(root)
            db_url = f"sqlite:///{config.db_path}"
            migrate_db(db_url)
            engine = create_engine_for_url(db_url)
            session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
            service = SyncService(
                client=None,
                connector=_EmptyItemsConnector(),
                session_factory=session_factory,
                config=config,
            )

            with patch(
                "lidltool.ingest.sync.normalize_receipt",
                side_effect=lambda detail, category_rules=None: _fake_normalized_receipt(detail["id"]),
            ), patch(
                "lidltool.ingest.sync._upsert_canonical_transaction",
                return_value=None,
            ), patch(
                "lidltool.ingest.sync.auto_match_unmatched_items",
                return_value=0,
            ), patch(
                "lidltool.ingest.sync.rebuild_item_observations",
                return_value=0,
            ):
                result = service.sync(full=True)

            self.assertTrue(result.ok)
            self.assertEqual(result.new_receipts, 1)
            self.assertEqual(result.receipts_seen, 2)
            self.assertEqual(result.validation["outcomes"]["quarantine"], 1)
            self.assertEqual(result.validation["issue_codes"]["empty_items"], 1)

            with session_factory() as session:
                receipt_count = session.execute(
                    text("select count(*) from receipts")
                ).scalar_one()
                quarantine_count = session.execute(
                    text("select count(*) from connector_payload_quarantine where source_id = 'lidl_plus_de'")
                ).scalar_one()

            self.assertEqual(receipt_count, 1)
            self.assertEqual(quarantine_count, 1)

    def test_sync_quarantines_unexpected_record_processing_failures_and_continues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = _desktop_config(root)
            db_url = f"sqlite:///{config.db_path}"
            migrate_db(db_url)
            engine = create_engine_for_url(db_url)
            session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
            service = SyncService(
                client=None,
                connector=_AlwaysNormalizeConnector(),
                session_factory=session_factory,
                config=config,
            )

            def _validate_or_fail(**kwargs):
                record_ref = kwargs["source_record_ref"]
                if record_ref == "bad-record":
                    raise RuntimeError("normalize_record failed: runtime connector returned empty items")
                from lidltool.ingest.validation import validate_normalized_connector_payload

                return validate_normalized_connector_payload(**kwargs)

            with patch(
                "lidltool.ingest.sync.normalize_receipt",
                side_effect=lambda detail, category_rules=None: _fake_normalized_receipt(detail["id"]),
            ), patch(
                "lidltool.ingest.sync.validate_normalized_connector_payload",
                side_effect=_validate_or_fail,
            ), patch(
                "lidltool.ingest.sync._upsert_canonical_transaction",
                return_value=None,
            ), patch(
                "lidltool.ingest.sync.auto_match_unmatched_items",
                return_value=0,
            ), patch(
                "lidltool.ingest.sync.rebuild_item_observations",
                return_value=0,
            ):
                result = service.sync(full=True)

            self.assertTrue(result.ok)
            self.assertEqual(result.new_receipts, 1)
            self.assertEqual(result.receipts_seen, 2)
            self.assertEqual(result.validation["outcomes"]["quarantine"], 1)
            self.assertEqual(result.validation["issue_codes"]["process_record_failed"], 1)

            with session_factory() as session:
                receipt_count = session.execute(
                    text("select count(*) from receipts")
                ).scalar_one()
                quarantine_count = session.execute(
                    text("select count(*) from connector_payload_quarantine where source_id = 'lidl_plus_de'")
                ).scalar_one()

            self.assertEqual(receipt_count, 1)
            self.assertEqual(quarantine_count, 1)

    def test_sync_quarantines_receipt_normalization_failures_and_continues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = _desktop_config(root)
            db_url = f"sqlite:///{config.db_path}"
            migrate_db(db_url)
            engine = create_engine_for_url(db_url)
            session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
            service = SyncService(
                client=None,
                connector=_FakeConnector(),
                session_factory=session_factory,
                config=config,
            )

            def _normalize_or_fail(detail: dict[str, str], category_rules=None) -> SimpleNamespace:
                if detail["id"] == "bad-record":
                    raise ValueError("normalized receipt record must contain at least one item")
                return _fake_normalized_receipt(detail["id"])

            with patch(
                "lidltool.ingest.sync.normalize_receipt",
                side_effect=_normalize_or_fail,
            ), patch(
                "lidltool.ingest.sync._upsert_canonical_transaction",
                return_value=None,
            ), patch(
                "lidltool.ingest.sync.auto_match_unmatched_items",
                return_value=0,
            ), patch(
                "lidltool.ingest.sync.rebuild_item_observations",
                return_value=0,
            ):
                result = service.sync(full=True)

            self.assertTrue(result.ok)
            self.assertEqual(result.new_receipts, 1)
            self.assertEqual(result.receipts_seen, 2)
            self.assertEqual(result.validation["outcomes"]["quarantine"], 1)
            self.assertEqual(result.validation["issue_codes"]["normalize_receipt_failed"], 1)

            with session_factory() as session:
                receipt_count = session.execute(
                    text("select count(*) from receipts")
                ).scalar_one()
                quarantine_count = session.execute(
                    text("select count(*) from connector_payload_quarantine where source_id = 'lidl_plus_de'")
                ).scalar_one()

            self.assertEqual(receipt_count, 1)
            self.assertEqual(quarantine_count, 1)

    def test_sync_quarantines_normalize_failures_and_continues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = _desktop_config(root)
            db_url = f"sqlite:///{config.db_path}"
            migrate_db(db_url)
            engine = create_engine_for_url(db_url)
            session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
            service = SyncService(
                client=None,
                connector=_FakeConnector(),
                session_factory=session_factory,
                config=config,
            )

            with patch(
                "lidltool.ingest.sync.normalize_receipt",
                side_effect=lambda detail, category_rules=None: _fake_normalized_receipt(detail["id"]),
            ), patch(
                "lidltool.ingest.sync._upsert_canonical_transaction",
                return_value=None,
            ), patch(
                "lidltool.ingest.sync.auto_match_unmatched_items",
                return_value=0,
            ), patch(
                "lidltool.ingest.sync.rebuild_item_observations",
                return_value=0,
            ):
                result = service.sync(full=True)

            self.assertTrue(result.ok)
            self.assertEqual(result.new_receipts, 1)
            self.assertEqual(result.receipts_seen, 2)
            self.assertEqual(result.validation["outcomes"]["quarantine"], 1)
            self.assertEqual(result.validation["issue_codes"]["normalize_record_failed"], 1)

            with session_factory() as session:
                receipt_count = session.execute(
                    text("select count(*) from receipts")
                ).scalar_one()
                quarantine_count = session.execute(
                    text("select count(*) from connector_payload_quarantine where source_id = 'lidl_plus_de'")
                ).scalar_one()

            self.assertEqual(receipt_count, 1)
            self.assertEqual(quarantine_count, 1)


if __name__ == "__main__":
    unittest.main()
