from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.analytics.normalization import canonicalize_category_name
from lidltool.db.audit import record_audit_event
from lidltool.db.models import (
    Document,
    MerchantAlias,
    NormalizationRule,
    Transaction,
    TransactionItem,
)
from lidltool.ingest.corrections import CorrectionService


class OverrideService:
    def __init__(self, *, session: Session) -> None:
        self._session = session

    def apply(
        self,
        *,
        transaction_id: str,
        mode: str,
        actor_id: str | None,
        reason: str | None,
        transaction_corrections: dict[str, Any],
        item_corrections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        transaction = self._session.get(Transaction, transaction_id)
        if transaction is None:
            raise RuntimeError("transaction not found")

        if mode not in {"local", "global", "both"}:
            raise RuntimeError("mode must be one of: local, global, both")

        global_result = (
            self._apply_global(
                transaction=transaction,
                actor_id=actor_id,
                reason=reason,
                transaction_corrections=transaction_corrections,
                item_corrections=item_corrections,
            )
            if mode in {"global", "both"}
            else {"created": []}
        )

        local_result = (
            self._apply_local(
                transaction_id=transaction_id,
                actor_id=actor_id,
                reason=reason,
                transaction_corrections=transaction_corrections,
                item_corrections=item_corrections,
            )
            if mode in {"local", "both"}
            else {"transaction": None, "items": []}
        )

        return {
            "transaction_id": transaction_id,
            "mode": mode,
            "local": local_result,
            "global": global_result,
        }

    def _apply_local(
        self,
        *,
        transaction_id: str,
        actor_id: str | None,
        reason: str | None,
        transaction_corrections: dict[str, Any],
        item_corrections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not transaction_corrections and not item_corrections:
            return {"transaction": None, "items": []}
        document = self._session.execute(
            select(Document)
            .where(Document.transaction_id == transaction_id)
            .order_by(Document.created_at.desc(), Document.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        service = CorrectionService(session=self._session)
        transaction_result: dict[str, Any] | None = None
        item_results: list[dict[str, Any]] = []
        if document is None:
            if transaction_corrections:
                transaction_result = service.correct_transaction_direct(
                    transaction_id=transaction_id,
                    corrections=transaction_corrections,
                    actor_id=actor_id,
                    reason=reason,
                )
            for item_payload in item_corrections:
                item_id = str(item_payload.get("item_id", "")).strip()
                corrections = item_payload.get("corrections")
                if not item_id or not isinstance(corrections, dict):
                    continue
                item_results.append(
                    service.correct_item_direct(
                        transaction_id=transaction_id,
                        item_id=item_id,
                        corrections=corrections,
                        actor_id=actor_id,
                        reason=reason,
                    )
                )
        else:
            if transaction_corrections:
                transaction_result = service.correct_transaction(
                    document_id=document.id,
                    corrections=transaction_corrections,
                    actor_id=actor_id,
                    reason=reason,
                )
            for item_payload in item_corrections:
                item_id = str(item_payload.get("item_id", "")).strip()
                corrections = item_payload.get("corrections")
                if not item_id or not isinstance(corrections, dict):
                    continue
                item_results.append(
                    service.correct_item(
                        document_id=document.id,
                        item_id=item_id,
                        corrections=corrections,
                        actor_id=actor_id,
                        reason=reason,
                    )
                )
        return {
            "transaction": transaction_result,
            "items": item_results,
        }

    def _apply_global(
        self,
        *,
        transaction: Transaction,
        actor_id: str | None,
        reason: str | None,
        transaction_corrections: dict[str, Any],
        item_corrections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        created: list[dict[str, Any]] = []

        merchant_override = transaction_corrections.get("merchant_name")
        if isinstance(merchant_override, str):
            before_merchant = (transaction.merchant_name or "").strip()
            after_merchant = merchant_override.strip()
            if before_merchant and after_merchant and before_merchant != after_merchant:
                alias = MerchantAlias(
                    source=transaction.source_id,
                    alias=before_merchant,
                    canonical_name=after_merchant,
                )
                self._session.add(alias)
                self._session.flush()
                record_audit_event(
                    self._session,
                    action="review.global_merchant_override",
                    source=transaction.source_id,
                    actor_id=actor_id,
                    entity_type="transaction",
                    entity_id=transaction.id,
                    details={
                        "reason": reason,
                        "before": before_merchant,
                        "after": after_merchant,
                        "merchant_alias_id": alias.id,
                    },
                )
                created.append(
                    {
                        "type": "merchant_alias",
                        "id": alias.id,
                        "alias": alias.alias,
                        "canonical_name": alias.canonical_name,
                    }
                )

        for item_payload in item_corrections:
            item_id = str(item_payload.get("item_id", "")).strip()
            corrections = item_payload.get("corrections")
            if not item_id or not isinstance(corrections, dict):
                continue
            category_override = corrections.get("category")
            if not isinstance(category_override, str) or not category_override.strip():
                continue
            normalized_override = canonicalize_category_name(category_override) or category_override.strip()
            item = self._session.get(TransactionItem, item_id)
            if item is None or item.transaction_id != transaction.id:
                raise RuntimeError("item override target not found on transaction")
            if not item.name.strip():
                continue
            exact_item_name = item.name.strip()
            rule = NormalizationRule(
                rule_type="category_name_regex",
                source=transaction.source_id,
                pattern=f"^{re.escape(exact_item_name)}$",
                replacement=normalized_override,
                priority=10,
                enabled=True,
                metadata_json={
                    "origin": "ledger_override",
                    "transaction_id": transaction.id,
                    "transaction_item_id": item.id,
                },
            )
            self._session.add(rule)
            self._session.flush()
            correction_service = CorrectionService(session=self._session)
            matching_items = (
                self._session.execute(
                    select(TransactionItem)
                    .join(Transaction, TransactionItem.transaction_id == Transaction.id)
                    .where(
                        Transaction.source_id == transaction.source_id,
                        TransactionItem.name == exact_item_name,
                    )
                )
                .scalars()
                .all()
            )
            updated_items = 0
            for matching_item in matching_items:
                correction_result = correction_service.correct_item_direct(
                    transaction_id=matching_item.transaction_id,
                    item_id=matching_item.id,
                    corrections={"category": normalized_override},
                    actor_id=actor_id,
                    reason=reason or "global exact-name category override",
                )
                if correction_result.get("updated_fields"):
                    updated_items += 1
            record_audit_event(
                self._session,
                action="review.global_category_override",
                source=transaction.source_id,
                actor_id=actor_id,
                entity_type="transaction",
                entity_id=transaction.id,
                details={
                    "reason": reason,
                    "transaction_item_id": item.id,
                    "item_name": item.name,
                    "before": item.category,
                    "after": normalized_override,
                    "normalization_rule_id": rule.id,
                    "applied_item_count": updated_items,
                },
            )
            created.append(
                {
                    "type": "normalization_rule",
                    "id": rule.id,
                    "rule_type": rule.rule_type,
                    "pattern": rule.pattern,
                    "replacement": rule.replacement,
                    "applied_item_count": updated_items,
                }
            )

        return {"created": created}
