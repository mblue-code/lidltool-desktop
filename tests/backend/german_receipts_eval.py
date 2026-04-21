from __future__ import annotations

import json
import os
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _desktop_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_python() -> Path:
    desktop_root = _desktop_root()
    if os.name == "nt":
        return desktop_root / "build" / "backend-venv" / "Scripts" / "python.exe"
    return desktop_root / "build" / "backend-venv" / "bin" / "python"


def _ensure_build_backend_src_on_path() -> Path:
    desktop_root = _desktop_root()
    packaged_src = desktop_root / "build" / "backend-src" / "src"
    if not packaged_src.exists():
        raise RuntimeError(
            f"Packaged backend source directory was not found at {packaged_src}. Run 'npm run build' first."
        )
    sys.path.insert(0, str(packaged_src))
    return packaged_src


PACKAGED_SRC = _ensure_build_backend_src_on_path()

from sqlalchemy import select

from lidltool.config import build_config
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import DiscountEvent, Document, Transaction, TransactionItem
from lidltool.ingest.ocr_ingest import OcrIngestService
from lidltool.storage.document_storage import DocumentStorage


@dataclass(slots=True)
class ReceiptMetrics:
    receipt_id: str
    merchant_ok: bool
    date_ok: bool
    total_ok: bool
    item_matches: int
    item_expected: int
    item_predicted: int
    discount_matches: int
    discount_expected: int
    discount_predicted: int
    exact_match: bool
    structured_strategy: str | None
    predicted: dict[str, Any]


def _normalize_text(value: str | None) -> str:
    raw = unicodedata.normalize("NFKD", value or "")
    ascii_only = "".join(ch for ch in raw if not unicodedata.combining(ch))
    lowered = ascii_only.lower()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in lowered)
    return " ".join(cleaned.split())


def _date_only(value: str | None) -> str:
    if not value:
        return ""
    return value[:10]


def _item_key(item: dict[str, Any]) -> tuple[str, int, bool]:
    return (
        _normalize_text(str(item.get("name") or "")),
        int(item.get("line_total_cents") or 0),
        bool(item.get("is_deposit")),
    )


def _discount_key(discount: dict[str, Any]) -> tuple[str, int]:
    return (
        _normalize_text(str(discount.get("label") or "")),
        int(discount.get("amount_cents") or 0),
    )


def _counter_matches(expected: Counter[tuple[Any, ...]], predicted: Counter[tuple[Any, ...]]) -> int:
    return sum(min(count, predicted.get(key, 0)) for key, count in expected.items())


def _load_ground_truth() -> dict[str, Any]:
    root = _desktop_root() / "tests" / "fixtures" / "german_receipts_eval"
    return json.loads((root / "ground_truth.json").read_text(encoding="utf-8"))


def _configure_env(config_dir: Path, documents_dir: Path) -> None:
    os.environ["LIDLTOOL_CONFIG_DIR"] = str(config_dir)
    os.environ["LIDLTOOL_DOCUMENT_STORAGE_PATH"] = str(documents_dir)
    os.environ.setdefault(
        "LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY",
        "desktop-german-eval-secret-key-1234567890abcdef",
    )
    if not os.environ.get("LIDLTOOL_AI_API_KEY") and os.environ.get("OPENAI_API_KEY"):
        os.environ["LIDLTOOL_AI_API_KEY"] = os.environ["OPENAI_API_KEY"]
    os.environ.setdefault("LIDLTOOL_AI_BASE_URL", "https://api.openai.com/v1")
    os.environ.setdefault("LIDLTOOL_AI_MODEL", "gpt-4.1-mini")
    if not os.environ.get("LIDLTOOL_OCR_OPENAI_API_KEY") and os.environ.get("LIDLTOOL_AI_API_KEY"):
        os.environ["LIDLTOOL_OCR_OPENAI_API_KEY"] = os.environ["LIDLTOOL_AI_API_KEY"]
    if not os.environ.get("LIDLTOOL_OCR_OPENAI_BASE_URL") and os.environ.get("LIDLTOOL_AI_BASE_URL"):
        os.environ["LIDLTOOL_OCR_OPENAI_BASE_URL"] = os.environ["LIDLTOOL_AI_BASE_URL"]
    if not os.environ.get("LIDLTOOL_OCR_OPENAI_MODEL") and os.environ.get("LIDLTOOL_AI_MODEL"):
        os.environ["LIDLTOOL_OCR_OPENAI_MODEL"] = os.environ["LIDLTOOL_AI_MODEL"]
    os.environ.setdefault("LIDLTOOL_DESKTOP_MODE", "true")
    os.environ.setdefault("LIDLTOOL_CONNECTOR_HOST_KIND", "electron")
    os.environ.setdefault("LIDLTOOL_OCR_DEFAULT_PROVIDER", "openai_compatible")
    os.environ.setdefault("LIDLTOOL_OCR_FALLBACK_ENABLED", "false")
    os.environ.setdefault("LIDLTOOL_ITEM_CATEGORIZER_ENABLED", "false")


def _run_receipt_eval(
    *,
    service: OcrIngestService,
    storage: DocumentStorage,
    sessions: Any,
    fixture_root: Path,
    truth: dict[str, Any],
) -> ReceiptMetrics:
    image_path = fixture_root / str(truth["file"])
    payload = image_path.read_bytes()
    storage_uri, sha256 = storage.store(
        file_name=image_path.name,
        mime_type="image/jpeg",
        payload=payload,
    )
    with session_scope(sessions) as session:
        document = Document(
            storage_uri=storage_uri,
            mime_type="image/jpeg",
            sha256=sha256,
            file_name=image_path.name,
            ocr_status="queued",
            metadata_json={"eval_receipt_id": truth["id"]},
        )
        session.add(document)
        session.flush()
        document_id = document.id

    service.process_document(document_id=document_id)

    with session_scope(sessions) as session:
        document = session.get(Document, document_id)
        if document is None or document.transaction_id is None:
            raise RuntimeError(f"OCR did not produce a transaction for {truth['id']}")
        transaction = session.get(Transaction, document.transaction_id)
        if transaction is None:
            raise RuntimeError(f"Transaction row missing for {truth['id']}")
        item_rows = session.execute(
            select(TransactionItem)
            .where(TransactionItem.transaction_id == transaction.id)
            .order_by(TransactionItem.line_no)
        ).scalars().all()
        discount_rows = session.execute(
            select(DiscountEvent).where(DiscountEvent.transaction_id == transaction.id)
        ).scalars().all()
        raw_payload = transaction.raw_payload or {}
        structured_meta = (
            raw_payload.get("structured_extraction") if isinstance(raw_payload, dict) else None
        )
        predicted = {
            "merchant": transaction.merchant_name,
            "purchased_at": _date_only(
                transaction.purchased_at.isoformat() if transaction.purchased_at else ""
            ),
            "total_gross_cents": transaction.total_gross_cents,
            "items": [
                {
                    "name": row.name,
                    "qty": str(row.qty),
                    "unit": row.unit,
                    "line_total_cents": row.line_total_cents,
                    "is_deposit": row.is_deposit,
                }
                for row in item_rows
            ],
            "discounts": [
                {
                    "label": row.source_label,
                    "amount_cents": row.amount_cents,
                }
                for row in discount_rows
            ],
        }

    expected_items = Counter(_item_key(item) for item in truth.get("items", []))
    predicted_items = Counter(_item_key(item) for item in predicted["items"])
    expected_discounts = Counter(_discount_key(item) for item in truth.get("discounts", []))
    predicted_discounts = Counter(_discount_key(item) for item in predicted["discounts"])

    item_matches = _counter_matches(expected_items, predicted_items)
    discount_matches = _counter_matches(expected_discounts, predicted_discounts)
    merchant_ok = _normalize_text(predicted["merchant"]) == _normalize_text(str(truth["merchant"]))
    date_ok = predicted["purchased_at"] == _date_only(str(truth["purchased_at"]))
    total_ok = int(predicted["total_gross_cents"] or 0) == int(truth["total_gross_cents"])
    exact_match = (
        merchant_ok
        and date_ok
        and total_ok
        and item_matches == sum(expected_items.values()) == sum(predicted_items.values())
        and discount_matches == sum(expected_discounts.values()) == sum(predicted_discounts.values())
    )

    return ReceiptMetrics(
        receipt_id=str(truth["id"]),
        merchant_ok=merchant_ok,
        date_ok=date_ok,
        total_ok=total_ok,
        item_matches=item_matches,
        item_expected=sum(expected_items.values()),
        item_predicted=sum(predicted_items.values()),
        discount_matches=discount_matches,
        discount_expected=sum(expected_discounts.values()),
        discount_predicted=sum(predicted_discounts.values()),
        exact_match=exact_match,
        structured_strategy=(
            structured_meta.get("strategy") if isinstance(structured_meta, dict) else None
        ),
        predicted=predicted,
    )


def main() -> None:
    desktop_root = _desktop_root()
    build_python = _build_python()
    if Path(sys.executable).resolve() != build_python.resolve():
        raise RuntimeError(
            f"German receipts eval must run under the build backend runtime. Expected {build_python}, got {sys.executable}."
        )

    ground_truth = _load_ground_truth()
    fixture_root = desktop_root / "tests" / "fixtures" / "german_receipts_eval"

    with tempfile.TemporaryDirectory(prefix="desktop-german-eval-") as tmpdir:
        root = Path(tmpdir)
        db_path = root / "german-eval.sqlite"
        config_dir = root / "config"
        documents_dir = root / "documents"
        config_dir.mkdir(parents=True, exist_ok=True)
        documents_dir.mkdir(parents=True, exist_ok=True)
        _configure_env(config_dir=config_dir, documents_dir=documents_dir)

        config = build_config(db_override=db_path)
        engine = create_engine_for_url(config.db_url or f"sqlite:///{db_path}")
        migrate_db(config.db_url or f"sqlite:///{db_path}")
        sessions = session_factory(engine)
        storage = DocumentStorage(config)
        service = OcrIngestService(session_factory=sessions, config=config)

        receipt_results = [
            _run_receipt_eval(
                service=service,
                storage=storage,
                sessions=sessions,
                fixture_root=fixture_root,
                truth=receipt,
            )
            for receipt in ground_truth["receipts"]
        ]

        total_fields = len(receipt_results) * 3
        correct_fields = sum(
            int(metric.merchant_ok) + int(metric.date_ok) + int(metric.total_ok)
            for metric in receipt_results
        )
        expected_item_lines = sum(metric.item_expected for metric in receipt_results)
        matched_item_lines = sum(metric.item_matches for metric in receipt_results)
        predicted_item_lines = sum(metric.item_predicted for metric in receipt_results)
        expected_discount_lines = sum(metric.discount_expected for metric in receipt_results)
        matched_discount_lines = sum(metric.discount_matches for metric in receipt_results)
        predicted_discount_lines = sum(metric.discount_predicted for metric in receipt_results)
        denom = total_fields + expected_item_lines + expected_discount_lines
        numer = correct_fields + matched_item_lines + matched_discount_lines
        summary = {
            "dataset_id": ground_truth["dataset_id"],
            "receipt_count": len(receipt_results),
            "field_accuracy_pct": round((correct_fields / total_fields) * 100, 2),
            "item_recall_pct": round((matched_item_lines / expected_item_lines) * 100, 2),
            "item_precision_pct": round((matched_item_lines / max(predicted_item_lines, 1)) * 100, 2),
            "discount_recall_pct": round(
                (matched_discount_lines / max(expected_discount_lines, 1)) * 100, 2
            ),
            "discount_precision_pct": round(
                (matched_discount_lines / max(predicted_discount_lines, 1)) * 100, 2
            ),
            "overall_accuracy_pct": round((numer / denom) * 100, 2),
            "exact_receipt_match_pct": round(
                (sum(int(metric.exact_match) for metric in receipt_results) / len(receipt_results)) * 100,
                2,
            ),
            "structured_receipt_count": sum(
                int(metric.structured_strategy == "structured_extraction") for metric in receipt_results
            ),
            "parser_fallback_count": sum(
                int(metric.structured_strategy == "parser_fallback") for metric in receipt_results
            ),
            "receipts": [
                {
                    "receipt_id": metric.receipt_id,
                    "merchant_ok": metric.merchant_ok,
                    "date_ok": metric.date_ok,
                    "total_ok": metric.total_ok,
                    "item_matches": metric.item_matches,
                    "item_expected": metric.item_expected,
                    "item_predicted": metric.item_predicted,
                    "discount_matches": metric.discount_matches,
                    "discount_expected": metric.discount_expected,
                    "discount_predicted": metric.discount_predicted,
                    "exact_match": metric.exact_match,
                    "structured_strategy": metric.structured_strategy,
                    "predicted": metric.predicted,
                }
                for metric in receipt_results
            ],
        }

        out_dir = desktop_root / ".tmp" / "german_receipts_eval"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "latest_results.json"
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\nResults written to: {out_path}")


if __name__ == "__main__":
    main()
