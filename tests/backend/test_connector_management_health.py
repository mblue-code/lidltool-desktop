from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.orm import sessionmaker

DESKTOP_ROOT = Path(__file__).resolve().parents[2]
VENDOR_BACKEND_SRC = DESKTOP_ROOT / "vendor" / "backend" / "src"

if str(VENDOR_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_BACKEND_SRC))

from lidltool.connectors.management import _health_by_source  # noqa: E402
from lidltool.db.engine import create_engine_for_url, migrate_db  # noqa: E402
from lidltool.db.models import ConnectorPayloadQuarantine, Source, SourceAccount, Transaction  # noqa: E402


class ConnectorManagementHealthTests(unittest.TestCase):
    def test_health_ignores_resolved_rows_and_reclassifies_lidl_source_gaps(self) -> None:
        with TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "health.sqlite"
            db_url = f"sqlite:///{db_path}"
            migrate_db(db_url)
            engine = create_engine_for_url(db_url)
            session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)

            with session_factory() as session:
                session.add(Source(
                    id="lidl_plus_de",
                    user_id=None,
                    kind="connector",
                    display_name="Lidl Plus",
                    status="healthy",
                    enabled=True,
                ))
                session.add(SourceAccount(source_id="lidl_plus_de", account_ref="default", status="connected"))
                session.add(Transaction(
                    source_id="lidl_plus_de",
                    user_id=None,
                    shared_group_id=None,
                    source_account_id=None,
                    source_transaction_id="resolved-record",
                    purchased_at=datetime(2026, 4, 28, tzinfo=UTC),
                    merchant_name="Lidl",
                    total_gross_cents=199,
                    currency="EUR",
                    discount_total_cents=0,
                    confidence=None,
                    fingerprint="resolved-fingerprint",
                    raw_payload={},
                ))
                session.flush()
                session.add_all([
                    ConnectorPayloadQuarantine(
                        source_id="lidl_plus_de",
                        source_account_id=None,
                        ingestion_job_id=None,
                        plugin_id=None,
                        manifest_version=None,
                        connector_api_version=None,
                        runtime_kind=None,
                        action_name="canonical_write_gate",
                        outcome="quarantine",
                        review_status="pending",
                        source_record_ref="historical-missing-html",
                        payload_snapshot={
                            "source_record_detail": {
                                "receiptHtmlAvailable": False,
                                "items": [],
                            }
                        },
                        validation_errors=[
                            {
                                "code": "source_receipt_items_unavailable",
                                "severity": "quarantine",
                                "message": "historical receipt unavailable",
                                "path": "$.normalized_record.items",
                            }
                        ],
                        runtime_diagnostics=None,
                    ),
                    ConnectorPayloadQuarantine(
                        source_id="lidl_plus_de",
                        source_account_id=None,
                        ingestion_job_id=None,
                        plugin_id=None,
                        manifest_version=None,
                        connector_api_version=None,
                        runtime_kind=None,
                        action_name="canonical_write_gate",
                        outcome="quarantine",
                        review_status="pending",
                        source_record_ref="resolved-record",
                        payload_snapshot={"source_record_detail": {"items": []}},
                        validation_errors=[
                            {
                                "code": "empty_items",
                                "severity": "quarantine",
                                "message": "normalized receipt record must contain at least one item",
                                "path": "$.normalized_record.items",
                            }
                        ],
                        runtime_diagnostics=None,
                    ),
                    ConnectorPayloadQuarantine(
                        source_id="lidl_plus_de",
                        source_account_id=None,
                        ingestion_job_id=None,
                        plugin_id=None,
                        manifest_version=None,
                        connector_api_version=None,
                        runtime_kind=None,
                        action_name="canonical_write_gate",
                        outcome="reject",
                        review_status="pending",
                        source_record_ref="actual-review-needed",
                        payload_snapshot={"source_record_detail": {"items": []}},
                        validation_errors=[
                            {
                                "code": "normalized_record_shape_invalid",
                                "severity": "reject",
                                "message": "schema invalid",
                                "path": "$.normalized_record",
                            }
                        ],
                        runtime_diagnostics=None,
                    ),
                ])
                session.commit()

                health = _health_by_source(session)["lidl_plus_de"]

            self.assertEqual(health["source_unavailable_records"], 1)
            self.assertEqual(health["pending_quarantine_reviews"], 1)
            self.assertEqual(health["status"], "needs_attention")
            self.assertIn("unavailable from the retailer", health["summary"])
            self.assertIn("still need review", health["summary"])


if __name__ == "__main__":
    unittest.main()
