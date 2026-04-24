from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.analytics.item_categorizer import (
    CategorizationRequest,
    categorize_transaction_items,
    resolve_item_categorizer_runtime_client,
)
from lidltool.analytics.normalization import load_normalization_bundle
from lidltool.analytics.product_matcher import resolve_product_for_item
from lidltool.config import AppConfig
from lidltool.db.engine import session_scope
from lidltool.db.models import Document, Source, SourceAccount, Transaction, TransactionItem
from lidltool.ingest.ocr_source import OCR_SOURCE_ID, ensure_ocr_source
from lidltool.ocr.confidence import confidence_metadata
from lidltool.ocr.parser import normalize_receipt_text, parse_receipt_text, to_canonical_payload
from lidltool.ocr.provider_router import OcrProviderRouter
from lidltool.storage.document_storage import DocumentStorage


class OcrIngestService:
    def __init__(self, *, session_factory: sessionmaker[Session], config: AppConfig) -> None:
        self._session_factory = session_factory
        self._config = config
        self._storage = DocumentStorage(config)
        self._router = OcrProviderRouter(config)
        self._item_categorizer_model_client = resolve_item_categorizer_runtime_client(config)

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
            normalized_ocr_text = normalize_receipt_text(routed.result.text)
            parsed = parse_receipt_text(normalized_ocr_text)
            metadata = confidence_metadata(
                parsed=parsed,
                ocr=routed.result,
                fallback_used=routed.fallback_used,
                attempted_providers=routed.attempted_providers,
            )
            canonical = to_canonical_payload(parsed)
            uploader_user_id = None
            if isinstance(document.metadata_json, dict):
                raw_uploader_user_id = document.metadata_json.get("uploader_user_id")
                if isinstance(raw_uploader_user_id, str) and raw_uploader_user_id.strip():
                    uploader_user_id = raw_uploader_user_id.strip()
            source, account = _resolve_document_source(
                session=session,
                document=document,
                owner_user_id=uploader_user_id,
            )
            tx = _upsert_ocr_transaction(
                session=session,
                source=source,
                source_account=account,
                document=document,
                config=self._config,
                canonical=canonical,
                raw_payload={
                    "ocr_text": normalized_ocr_text,
                    "ocr_metadata": routed.result.metadata or {},
                    "confidence": metadata,
                },
                transaction_confidence=metadata["transaction_confidence"],
                item_confidence_scores=metadata["item_confidence_scores"],
                model_client=self._item_categorizer_model_client,
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
            document.ocr_text = normalized_ocr_text
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


def _resolve_document_source(
    *,
    session: Session,
    document: Document,
    owner_user_id: str | None,
) -> tuple[Source, SourceAccount]:
    if document.source_id and document.source_id != OCR_SOURCE_ID:
        source = session.get(Source, document.source_id)
        if source is None:
            raise RuntimeError(f"document source is not registered: {document.source_id}")
        account = session.execute(
            select(SourceAccount).where(SourceAccount.source_id == source.id).limit(1)
        ).scalar_one_or_none()
        if account is None:
            account = SourceAccount(source_id=source.id, account_ref="default", status="connected")
            session.add(account)
            session.flush()
        return source, account
    source, account = ensure_ocr_source(session, owner_user_id=owner_user_id)
    document.source_id = source.id
    return source, account


def _upsert_ocr_transaction(
    *,
    session: Session,
    source: Source,
    source_account: SourceAccount,
    document: Document,
    config: AppConfig,
    canonical: dict[str, object],
    raw_payload: dict[str, object],
    transaction_confidence: float,
    item_confidence_scores: list[float],
    model_client: object | None,
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
        shared_group_id=document.shared_group_id or source.shared_group_id,
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
    item_rows: list[TransactionItem] = []
    categorization_requests: list[CategorizationRequest] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        score = item_confidence_scores[idx - 1] if idx - 1 < len(item_confidence_scores) else 0.7
        item_row = TransactionItem(
            transaction_id=tx.id,
            shared_group_id=tx.shared_group_id,
            source_item_id=str(item.get("source_item_id") or f"{source_transaction_id}:{idx}"),
            line_no=int(item.get("line_no") or idx),
            name=str(item.get("name") or f"item_{idx}"),
            qty=Decimal(str(item.get("qty") or "1.0")),
            unit=str(item.get("unit")) if item.get("unit") is not None else None,
            unit_price_cents=(
                int(item["unit_price_cents"]) if item.get("unit_price_cents") is not None else None
            ),
            line_total_cents=int(item.get("line_total_cents") or 0),
            category=str(item.get("category")) if item.get("category") is not None else None,
            confidence=_to_decimal(score),
            raw_payload=item,
        )
        match = resolve_product_for_item(session, item=item_row, source=source)
        if match is not None:
            item_row.product_id = match.product_id
        item_rows.append(item_row)
        categorization_requests.append(
            CategorizationRequest(
                item_name=item_row.name,
                current_category=item_row.category,
                product_id=item_row.product_id,
                raw_payload=item,
                item_confidence=score,
                merchant_name=tx.merchant_name,
                source_item_id=item_row.source_item_id,
                unit=item_row.unit,
                unit_price_cents=item_row.unit_price_cents,
                line_total_cents=item_row.line_total_cents,
            )
        )

    categorization_results = categorize_transaction_items(
        session=session,
        source=source,
        requests=categorization_requests,
        normalization_bundle=normalization_bundle,
        use_model=model_client is not None,
        model_client=model_client,
        model_batch_size=int(getattr(config, "item_categorizer_max_batch_size", 8) or 8),
        model_confidence_threshold=float(
            getattr(
                config,
                "item_categorizer_confidence_threshold",
                getattr(config, "item_categorizer_low_confidence_threshold", 0.65),
            )
            or 0.65
        ),
    )
    for item_row, categorization_result in zip(item_rows, categorization_results, strict=True):
        item_row.category = categorization_result.category_name
        item_row.category_id = categorization_result.category_id
        item_row.category_method = categorization_result.method
        item_row.category_confidence = _to_decimal(categorization_result.confidence)
        item_row.category_source_value = categorization_result.source_value
        item_row.category_version = categorization_result.version
        session.add(item_row)
    return tx


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(f"{value:.3f}")
