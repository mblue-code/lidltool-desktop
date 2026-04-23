from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from lidltool.db.models import ItemObservation, Source, Transaction, TransactionItem

ScopeName = Literal["personal", "group"]
WorkspaceKind = Literal["personal", "shared_group"]


@dataclass(frozen=True, slots=True)
class ParsedScope:
    scope: ScopeName
    workspace_kind: WorkspaceKind
    shared_group_id: str | None = None


@dataclass(frozen=True, slots=True)
class VisibilityContext:
    user_id: str
    is_service: bool
    scope: ScopeName = "personal"
    workspace_kind: WorkspaceKind = "personal"
    shared_group_id: str | None = None


def parse_scope(raw_scope: str | None) -> ParsedScope:
    if raw_scope is None:
        return ParsedScope(scope="personal", workspace_kind="personal")
    candidate = raw_scope.strip()
    normalized = candidate.lower()
    if normalized == "personal":
        return ParsedScope(scope="personal", workspace_kind="personal")
    if normalized.startswith("group:") or normalized.startswith("shared_group:"):
        _, group_id = candidate.split(":", 1)
        group_id = group_id.strip()
        if not group_id:
            raise ValueError("scope group selector must include a group id")
        return ParsedScope(scope="group", workspace_kind="shared_group", shared_group_id=group_id)
    raise ValueError("scope must be one of: personal, group:<group_id>")


def personal_source_filter(context: VisibilityContext) -> ColumnElement[bool]:
    if context.workspace_kind == "shared_group" and context.shared_group_id:
        return Source.shared_group_id == context.shared_group_id
    clauses: list[ColumnElement[bool]] = [Source.shared_group_id.is_(None)]
    if context.is_service:
        clauses.append(or_(Source.user_id == context.user_id, Source.user_id.is_(None)))
    else:
        clauses.append(Source.user_id == context.user_id)
    return and_(*clauses)


def personal_transaction_filter(context: VisibilityContext) -> ColumnElement[bool]:
    clauses: list[ColumnElement[bool]] = [
        Transaction.shared_group_id.is_(None),
        Source.shared_group_id.is_(None),
    ]
    if context.is_service:
        clauses.append(or_(Transaction.user_id == context.user_id, Transaction.user_id.is_(None)))
    else:
        clauses.append(Transaction.user_id == context.user_id)
    return and_(*clauses)


def shared_group_transaction_filter(context: VisibilityContext) -> ColumnElement[bool]:
    if context.shared_group_id is None:
        raise ValueError("shared group visibility requires a concrete shared_group_id")
    explicit_filter = or_(
        Transaction.shared_group_id == context.shared_group_id,
        Source.shared_group_id == context.shared_group_id,
        Transaction.id.in_(
            select(TransactionItem.transaction_id).where(
                TransactionItem.shared_group_id == context.shared_group_id
            )
        ),
    )
    return explicit_filter


def transaction_visibility_filter(context: VisibilityContext) -> ColumnElement[bool]:
    if context.scope == "group":
        return shared_group_transaction_filter(context)
    return personal_transaction_filter(context)


def visible_transaction_ids_subquery(context: VisibilityContext) -> Select[tuple[str]]:
    return (
        select(Transaction.id)
        .select_from(Transaction)
        .join(Source, Source.id == Transaction.source_id)
        .where(transaction_visibility_filter(context))
    )


def observation_visibility_filter(context: VisibilityContext) -> ColumnElement[bool]:
    if context.scope != "group":
        return ItemObservation.transaction_id.in_(visible_transaction_ids_subquery(context))

    if context.shared_group_id is not None:
        full_workspace_tx = (
            select(Transaction.id)
            .select_from(Transaction)
            .join(Source, Source.id == Transaction.source_id)
            .where(
                or_(
                    Transaction.shared_group_id == context.shared_group_id,
                    Source.shared_group_id == context.shared_group_id,
                )
            )
        )
        item_allocated_tx = (
            select(Transaction.id)
            .select_from(Transaction)
            .where(
                Transaction.id.in_(
                    select(TransactionItem.transaction_id).where(
                        TransactionItem.shared_group_id == context.shared_group_id
                    )
                )
            )
        )
        item_allocated_match = (
            select(TransactionItem.id)
            .where(
                TransactionItem.transaction_id == ItemObservation.transaction_id,
                TransactionItem.shared_group_id == context.shared_group_id,
                func.lower(TransactionItem.name) == func.lower(ItemObservation.raw_item_name),
            )
            .exists()
        )
        explicit_filter = or_(
            ItemObservation.transaction_id.in_(full_workspace_tx),
            and_(ItemObservation.transaction_id.in_(item_allocated_tx), item_allocated_match),
        )
        return explicit_filter

    raise ValueError("shared group visibility requires a concrete shared_group_id")
