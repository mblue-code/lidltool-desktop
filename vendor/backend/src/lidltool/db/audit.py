from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from lidltool.db.models import AuditEvent


def record_audit_event(
    session: Session,
    *,
    action: str,
    source: str | None = None,
    actor_type: str = "user",
    actor_id: str | None = None,
    entity_type: str | None = "source",
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        source=source,
        details=details,
    )
    session.add(event)
    return event


def list_transaction_history(
    session: Session,
    *,
    transaction_id: str,
    document_ids: list[str] | None = None,
    item_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    filters = [
        and_(AuditEvent.entity_type == "transaction", AuditEvent.entity_id == transaction_id)
    ]
    for document_id in document_ids or []:
        filters.append(
            and_(AuditEvent.entity_type == "document", AuditEvent.entity_id == document_id)
        )
    for item_id in item_ids or []:
        filters.append(
            and_(AuditEvent.entity_type == "transaction_item", AuditEvent.entity_id == item_id)
        )

    rows = (
        session.execute(
            select(AuditEvent)
            .where(or_(*filters))
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "action": row.action,
            "actor_type": row.actor_type,
            "actor_id": row.actor_id,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "source": row.source,
            "details": row.details,
        }
        for row in rows
    ]


def summarize_actions(
    session: Session,
    *,
    actions: list[str] | None = None,
    actor_type: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    query = select(AuditEvent)
    if actions:
        query = query.where(AuditEvent.action.in_(actions))
    if actor_type:
        query = query.where(AuditEvent.actor_type == actor_type)
    if source:
        query = query.where(AuditEvent.source == source)
    rows = session.execute(query).scalars().all()
    by_action = Counter(row.action for row in rows)
    by_actor_type = Counter(row.actor_type for row in rows)
    return {
        "total": len(rows),
        "by_action": dict(by_action),
        "by_actor_type": dict(by_actor_type),
    }
