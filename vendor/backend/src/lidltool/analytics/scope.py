from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from lidltool.db.models import ItemObservation, Source, Transaction, TransactionItem

ScopeName = Literal["personal", "family"]


@dataclass(frozen=True, slots=True)
class VisibilityContext:
    user_id: str
    is_service: bool
    scope: ScopeName = "personal"


def parse_scope(raw_scope: str | None) -> ScopeName:
    if raw_scope is None:
        return "personal"
    normalized = raw_scope.strip().lower()
    if normalized not in {"personal", "family"}:
        raise ValueError("scope must be one of: personal, family")
    return normalized  # type: ignore[return-value]


def personal_source_filter(context: VisibilityContext) -> ColumnElement[bool]:
    if context.is_service:
        return or_(Source.user_id == context.user_id, Source.user_id.is_(None))
    return Source.user_id == context.user_id


def family_transaction_filter() -> ColumnElement[bool]:
    return and_(
        Transaction.family_share_mode != "none",
        or_(
            and_(
                Source.family_share_mode == "all",
                Transaction.family_share_mode == "inherit",
            ),
            Transaction.family_share_mode.in_(["receipt", "items"]),
        ),
    )


def family_item_filter() -> ColumnElement[bool]:
    return and_(
        Transaction.family_share_mode != "none",
        or_(
            and_(
                Source.family_share_mode == "all",
                Transaction.family_share_mode == "inherit",
            ),
            Transaction.family_share_mode == "receipt",
            and_(
                Transaction.family_share_mode == "items",
                TransactionItem.family_shared.is_(True),
            ),
        ),
    )


def personal_transaction_filter(context: VisibilityContext) -> ColumnElement[bool]:
    if context.is_service:
        return or_(Transaction.user_id == context.user_id, Transaction.user_id.is_(None))
    return Transaction.user_id == context.user_id


def transaction_visibility_filter(context: VisibilityContext) -> ColumnElement[bool]:
    if context.scope == "family":
        return family_transaction_filter()
    return personal_transaction_filter(context)


def visible_transaction_ids_subquery(context: VisibilityContext) -> Select[tuple[str]]:
    return (
        select(Transaction.id)
        .select_from(Transaction)
        .join(Source, Source.id == Transaction.source_id)
        .where(transaction_visibility_filter(context))
    )


def observation_visibility_filter(context: VisibilityContext) -> ColumnElement[bool]:
    if context.scope != "family":
        return ItemObservation.transaction_id.in_(visible_transaction_ids_subquery(context))

    receipt_level_tx = (
        select(Transaction.id)
        .select_from(Transaction)
        .join(Source, Source.id == Transaction.source_id)
        .where(
            Transaction.family_share_mode != "none",
            or_(
                and_(
                    Source.family_share_mode == "all",
                    Transaction.family_share_mode == "inherit",
                ),
                Transaction.family_share_mode == "receipt",
            ),
        )
    )
    items_level_tx = select(Transaction.id).where(Transaction.family_share_mode == "items")
    items_match = (
        select(TransactionItem.id)
        .where(
            TransactionItem.transaction_id == ItemObservation.transaction_id,
            TransactionItem.family_shared.is_(True),
            func.lower(TransactionItem.name) == func.lower(ItemObservation.raw_item_name),
        )
        .exists()
    )
    return or_(
        ItemObservation.transaction_id.in_(receipt_level_tx),
        and_(ItemObservation.transaction_id.in_(items_level_tx), items_match),
    )
