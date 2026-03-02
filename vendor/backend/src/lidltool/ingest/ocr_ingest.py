from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.analytics.normalization import load_normalization_bundle
from lidltool.auth.users import ensure_service_user
from lidltool.config import AppConfig
from lidltool.db.engine import session_scope
from lidltool.db.models import Document, Source, SourceAccount, Transaction, TransactionItem
from lidltool.ocr.confidence import confidence_metadata
from lidltool.ocr.parser import parse_receipt_text, to_canonical_payload
from lidltool.ocr.provider_router import OcrProviderRouter
from lidltool.storage.document_storage import DocumentStorage

OCR_SOURCE_ID = "ocr_upload"


class OcrIngestService:
    def __init__(self, *, session_factory: sessionmaker[Session], config: AppConfig) -> None:
        self._session_factory = session_factory
        self._config = config
        self._storage = DocumentStorage(config)
        self._router = OcrProviderRouter(config)

    def process_document(self, *, document_id: str) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            document = session.get(Document, document_id)
            if document is None:
                raise RuntimeError(f"document not found: {document_id}")
            payload = self._storage.read_bytes(storage_uri=document.storage_uri)
            file_name = document.file_name or f"{document.id}.bin"
            routed = self._router.extract(
                payload=payload,
                mime_type=document.mime_type,
                file_name=file_name,
            )
            parsed = parse_receipt_text(routed.result.text)
            metadata = confidence_metadata(
                parsed=parsed,
                ocr=routed.result,
                fallback_used=routed.fallback_used,
                attempted_providers=routed.attempted_providers,
            )
            canonical = to_canonical_payload(parsed)
            source, account = _ensure_ocr_source(session)
            tx = _upsert_ocr_transaction(
                session=session,
                source=source,
                source_account=account,
                canonical=canonical,
                raw_payload={
                    "ocr_text": routed.result.text,
                    "ocr_metadata": routed.result.metadata or {},
                    "confidence": metadata,
                },
                transaction_confidence=metadata["transaction_confidence"],
                item_confidence_scores=metadata["item_confidence_scores"],
            )
            document.transaction_id = tx.id
            document.source_id = source.id
            document.ocr_status = "completed"
            tx_confidence = float(tx.confidence) if tx.confidence is not None else None
            if (
                tx_confidence is None
                or tx_confidence < self._config.ocr_review_confidence_threshold
            ):
                document.review_status = "needs_review"
            else:
                document.review_status = "approved"
            document.ocr_provider = routed.result.provider
            document.ocr_latency_ms = routed.result.latency_ms
            document.ocr_confidence = _to_decimal(routed.result.confidence)
            document.ocr_fallback_used = routed.fallback_used
            document.ocr_text = routed.result.text
            document.ocr_processed_at = datetime.now(tz=UTC)
            merged_metadata = dict(document.metadata_json or {})
            merged_metadata.update(
                {
                    "ocr_attempted_providers": routed.attempted_providers,
                    "ocr_metadata": routed.result.metadata or {},
                    "confidence": metadata,
                }
            )
            document.metadata_json = merged_metadata
            session.flush()
            return {
                "document_id": document.id,
                "transaction_id": tx.id,
                "ocr_provider": routed.result.provider,
                "fallback_used": routed.fallback_used,
                "attempted_providers": routed.attempted_providers,
                "transaction_confidence": metadata["transaction_confidence"],
                "review_status": document.review_status,
            }


def _ensure_ocr_source(session: Session) -> tuple[Source, SourceAccount]:
    service_user = ensure_service_user(session)
    source = session.get(Source, OCR_SOURCE_ID)
    if source is None:
        source = Source(
            id=OCR_SOURCE_ID,
            user_id=service_user.user_id,
            kind="ocr",
            display_name="OCR Uploads",
            status="healthy",
            enabled=True,
        )
        session.add(source)
        session.flush()
    elif source.user_id is None:
        source.user_id = service_user.user_id
    account = session.execute(
        select(SourceAccount).where(SourceAccount.source_id == source.id).limit(1)
    ).scalar_one_or_none()
    if account is None:
        account = SourceAccount(source_id=source.id, account_ref="default", status="connected")
        session.add(account)
        session.flush()
    return source, account


def _upsert_ocr_transaction(
    *,
    session: Session,
    source: Source,
    source_account: SourceAccount,
    canonical: dict[str, object],
    raw_payload: dict[str, object],
    transaction_confidence: float,
    item_confidence_scores: list[float],
) -> Transaction:
    normalization_bundle = load_normalization_bundle(session, source=source.id)
    source_transaction_id = str(canonical.get("id") or "").strip()
    existing = session.execute(
        select(Transaction)
        .where(
            Transaction.source_id == source.id,
            Transaction.source_transaction_id == source_transaction_id,
        )
        .limit(1)
    ).scalar_one_or_none()

    if existing is not None:
        existing.raw_payload = raw_payload
        existing.confidence = _to_decimal(transaction_confidence)
        return existing

    total_gross_raw = canonical.get("total_gross_cents")
    total_gross_cents = (
        int(total_gross_raw)
        if isinstance(total_gross_raw, int | float | str) and str(total_gross_raw).strip() != ""
        else 0
    )

    tx = Transaction(
        source_id=source.id,
        user_id=source.user_id,
        source_account_id=source_account.id,
        source_transaction_id=source_transaction_id,
        purchased_at=datetime.fromisoformat(str(canonical["purchased_at"])),
        merchant_name=str(canonical.get("store_name") or normalization_bundle.source),
        total_gross_cents=total_gross_cents,
        currency=str(canonical.get("currency") or "EUR"),
        discount_total_cents=None,
        confidence=_to_decimal(transaction_confidence),
        fingerprint=str(canonical.get("fingerprint") or None),
        raw_payload=raw_payload,
    )
    session.add(tx)
    session.flush()

    raw_items = canonical.get("items")
    items = raw_items if isinstance(raw_items, list) else []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        score = item_confidence_scores[idx - 1] if idx - 1 < len(item_confidence_scores) else 0.7
        session.add(
            TransactionItem(
                transaction_id=tx.id,
                source_item_id=str(item.get("source_item_id") or f"{source_transaction_id}:{idx}"),
                line_no=int(item.get("line_no") or idx),
                name=str(item.get("name") or f"item_{idx}"),
                qty=Decimal(str(item.get("qty") or "1.0")),
                unit=str(item.get("unit")) if item.get("unit") is not None else None,
                unit_price_cents=(
                    int(item["unit_price_cents"])
                    if item.get("unit_price_cents") is not None
                    else None
                ),
                line_total_cents=int(item.get("line_total_cents") or 0),
                category=str(item.get("category")) if item.get("category") is not None else None,
                confidence=_to_decimal(score),
                raw_payload=item,
            )
        )
    return tx


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(f"{value:.3f}")
