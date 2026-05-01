from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.analytics.normalization import canonicalize_category_name
from lidltool.db.audit import record_audit_event
from lidltool.db.models import Category, Document, TrainingHint, Transaction, TransactionItem

_EDITABLE_TRANSACTION_FIELDS = {
    "merchant_name",
    "total_gross_cents",
    "currency",
    "discount_total_cents",
    "purchased_at",
    "direction",
    "finance_category_id",
}
_EDITABLE_ITEM_FIELDS = {
    "name",
    "qty",
    "unit",
    "unit_price_cents",
    "line_total_cents",
    "category",
}


class CorrectionService:
    def __init__(self, *, session: Session) -> None:
        self._session = session

    def approve_document(
        self,
        *,
        document_id: str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        document, _ = self._load_document_transaction(document_id=document_id)
        before = document.review_status
        document.review_status = "approved"
        record_audit_event(
            self._session,
            action="review.approved",
            source=document.source_id,
            actor_id=actor_id,
            entity_type="document",
            entity_id=document.id,
            details={"before": before, "after": document.review_status, "reason": reason},
        )
        return {"document_id": document.id, "review_status": document.review_status}

    def reject_document(
        self,
        *,
        document_id: str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        document, _ = self._load_document_transaction(document_id=document_id)
        before = document.review_status
        document.review_status = "rejected"
        record_audit_event(
            self._session,
            action="review.rejected",
            source=document.source_id,
            actor_id=actor_id,
            entity_type="document",
            entity_id=document.id,
            details={"before": before, "after": document.review_status, "reason": reason},
        )
        return {"document_id": document.id, "review_status": document.review_status}

    def correct_transaction(
        self,
        *,
        document_id: str,
        corrections: dict[str, Any],
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        document, tx = self._load_document_transaction(document_id=document_id)
        before_after = self._apply_transaction_updates(tx=tx, corrections=corrections)
        if not before_after:
            return {"transaction_id": tx.id, "updated_fields": []}
        self._record_correction_audit(
            action="review.transaction_corrected",
            document=document,
            entity_type="transaction",
            entity_id=tx.id,
            before_after=before_after,
            actor_id=actor_id,
            reason=reason,
        )
        for field_name, values in before_after.items():
            self._add_training_hint(
                document=document,
                transaction=tx,
                transaction_item=None,
                hint_type="transaction_correction",
                field_path=f"transaction.{field_name}",
                original_value=values["before"],
                corrected_value=values["after"],
                reason=reason,
        )
        return {"transaction_id": tx.id, "updated_fields": sorted(before_after.keys())}

    def correct_transaction_direct(
        self,
        *,
        transaction_id: str,
        actor_id: str | None = None,
        corrections: dict[str, Any],
        reason: str | None = None,
    ) -> dict[str, Any]:
        tx = self._session.get(Transaction, transaction_id)
        if tx is None:
            raise RuntimeError("transaction not found")
        before_after = self._apply_transaction_updates(tx=tx, corrections=corrections)
        if not before_after:
            return {"transaction_id": tx.id, "updated_fields": []}
        self._record_direct_correction_audit(
            action="review.transaction_corrected",
            source_id=tx.source_id,
            entity_type="transaction",
            entity_id=tx.id,
            before_after=before_after,
            actor_id=actor_id,
            reason=reason,
        )
        return {"transaction_id": tx.id, "updated_fields": sorted(before_after.keys())}

    def correct_item(
        self,
        *,
        document_id: str,
        item_id: str,
        corrections: dict[str, Any],
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        document, tx = self._load_document_transaction(document_id=document_id)
        item = self._session.get(TransactionItem, item_id)
        if item is None or item.transaction_id != tx.id:
            raise RuntimeError("transaction item not found for document")
        before_after = self._apply_item_updates(item=item, corrections=corrections)
        if not before_after:
            return {"transaction_item_id": item.id, "updated_fields": []}
        self._record_correction_audit(
            action="review.item_corrected",
            document=document,
            entity_type="transaction_item",
            entity_id=item.id,
            before_after=before_after,
            actor_id=actor_id,
            reason=reason,
        )
        for field_name, values in before_after.items():
            self._add_training_hint(
                document=document,
                transaction=tx,
                transaction_item=item,
                hint_type="item_correction",
                field_path=f"items.{item.id}.{field_name}",
                original_value=values["before"],
                corrected_value=values["after"],
                reason=reason,
        )
        return {"transaction_item_id": item.id, "updated_fields": sorted(before_after.keys())}

    def correct_item_direct(
        self,
        *,
        transaction_id: str,
        item_id: str,
        actor_id: str | None = None,
        corrections: dict[str, Any],
        reason: str | None = None,
    ) -> dict[str, Any]:
        tx = self._session.get(Transaction, transaction_id)
        if tx is None:
            raise RuntimeError("transaction not found")
        item = self._session.get(TransactionItem, item_id)
        if item is None or item.transaction_id != tx.id:
            raise RuntimeError("transaction item not found for transaction")
        before_after = self._apply_item_updates(item=item, corrections=corrections)
        if not before_after:
            return {"transaction_item_id": item.id, "updated_fields": []}
        self._record_direct_correction_audit(
            action="review.item_corrected",
            source_id=tx.source_id,
            entity_type="transaction_item",
            entity_id=item.id,
            before_after=before_after,
            actor_id=actor_id,
            reason=reason,
        )
        return {"transaction_item_id": item.id, "updated_fields": sorted(before_after.keys())}

    def _load_document_transaction(self, *, document_id: str) -> tuple[Document, Transaction]:
        document = self._session.get(Document, document_id)
        if document is None or document.transaction_id is None:
            raise RuntimeError("document not found")
        tx = self._session.get(Transaction, document.transaction_id)
        if tx is None:
            raise RuntimeError("transaction not found for document")
        return document, tx

    def _apply_transaction_updates(
        self,
        *,
        tx: Transaction,
        corrections: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        before_after: dict[str, dict[str, Any]] = {}
        for field_name, value in corrections.items():
            if field_name not in _EDITABLE_TRANSACTION_FIELDS:
                raise RuntimeError(f"unsupported transaction field: {field_name}")
            current_value = getattr(tx, field_name)
            normalized = _normalize_value(field_name, value)
            if current_value == normalized:
                continue
            before_after[field_name] = {"before": current_value, "after": normalized}
            setattr(tx, field_name, normalized)
            if field_name == "finance_category_id":
                tx.finance_category_method = "manual"
                tx.finance_category_confidence = Decimal("1.000")
                tx.finance_category_source_value = "manual"
                tx.finance_category_version = "manual"
        return before_after

    def _apply_item_updates(
        self,
        *,
        item: TransactionItem,
        corrections: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        before_after: dict[str, dict[str, Any]] = {}
        for field_name, value in corrections.items():
            if field_name not in _EDITABLE_ITEM_FIELDS:
                raise RuntimeError(f"unsupported item field: {field_name}")
            current_value = getattr(item, field_name)
            normalized = _normalize_value(field_name, value)
            if current_value == normalized:
                continue
            before_after[field_name] = {"before": current_value, "after": normalized}
            setattr(item, field_name, normalized)
            if field_name == "category":
                canonical_category = canonicalize_category_name(str(normalized)) if normalized else None
                item.category = canonical_category or (str(normalized) if normalized is not None else None)
                item.category_id = _resolve_category_id(self._session, item.category)
                item.category_method = "manual"
                item.category_confidence = Decimal("1.000")
                item.category_version = "manual"
        return before_after

    def _record_correction_audit(
        self,
        *,
        action: str,
        document: Document,
        entity_type: str,
        entity_id: str,
        before_after: dict[str, dict[str, Any]],
        actor_id: str | None,
        reason: str | None,
    ) -> None:
        record_audit_event(
            self._session,
            action=action,
            source=document.source_id,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            details={
                "changes": {
                    key: {
                        "before": _to_jsonable(values["before"]),
                        "after": _to_jsonable(values["after"]),
                    }
                    for key, values in before_after.items()
                },
                "reason": reason,
            },
        )

    def _record_direct_correction_audit(
        self,
        *,
        action: str,
        source_id: str,
        entity_type: str,
        entity_id: str,
        before_after: dict[str, dict[str, Any]],
        actor_id: str | None,
        reason: str | None,
    ) -> None:
        record_audit_event(
            self._session,
            action=action,
            source=source_id,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            details={
                "changes": {
                    key: {
                        "before": _to_jsonable(values["before"]),
                        "after": _to_jsonable(values["after"]),
                    }
                    for key, values in before_after.items()
                },
                "reason": reason,
                "document_linked": False,
            },
        )

    def _add_training_hint(
        self,
        *,
        document: Document,
        transaction: Transaction,
        transaction_item: TransactionItem | None,
        hint_type: str,
        field_path: str,
        original_value: Any,
        corrected_value: Any,
        reason: str | None,
    ) -> None:
        self._session.add(
            TrainingHint(
                document_id=document.id,
                transaction_id=transaction.id,
                transaction_item_id=transaction_item.id if transaction_item is not None else None,
                hint_type=hint_type,
                field_path=field_path,
                original_value=_serialize_hint_value(original_value),
                corrected_value=_serialize_hint_value(corrected_value),
                context_json={
                    "source_id": document.source_id,
                    "reason": reason,
                },
            )
        )


def _normalize_value(field_name: str, value: Any) -> Any:
    if field_name in {
        "total_gross_cents",
        "discount_total_cents",
        "unit_price_cents",
        "line_total_cents",
    }:
        if value is None and field_name in {"discount_total_cents", "unit_price_cents"}:
            return None
        return int(value)
    if field_name == "qty":
        return Decimal(str(value))
    if field_name == "purchased_at":
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
    if value is None:
        return None
    if field_name == "direction":
        normalized = str(value).strip()
        if normalized not in {"inflow", "outflow", "transfer", "neutral"}:
            raise RuntimeError("unsupported transaction direction")
        return normalized
    if field_name == "finance_category_id":
        return str(value).strip() or None
    if field_name == "category":
        return canonicalize_category_name(str(value)) or str(value)
    return str(value)


def _resolve_category_id(session: Session, category_name: str | None) -> str | None:
    if not category_name:
        return None
    return session.execute(
        select(Category.category_id).where(Category.name == category_name).limit(1)
    ).scalar_one_or_none()


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_hint_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
