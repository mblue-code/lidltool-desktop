from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lidltool.analytics.advanced import budget_utilization
from lidltool.analytics.scope import VisibilityContext
from lidltool.db.models import Goal, IngestionJob, Notification, RecurringBill, RecurringBillOccurrence, Source
from lidltool.goals.service import goals_summary


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _serialize_notification(notification: Notification) -> dict[str, Any]:
    return {
        "id": notification.id,
        "user_id": notification.user_id,
        "kind": notification.kind,
        "severity": notification.severity,
        "title": notification.title,
        "body": notification.body,
        "href": notification.href,
        "unread": notification.unread,
        "occurred_at": notification.occurred_at.isoformat(),
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "metadata_json": notification.metadata_json,
        "created_at": notification.created_at.isoformat(),
        "updated_at": notification.updated_at.isoformat(),
    }


def _upsert_notification(
    session: Session,
    *,
    user_id: str,
    kind: str,
    severity: str,
    title: str,
    body: str,
    href: str | None,
    fingerprint: str,
    occurred_at: datetime,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    existing = session.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.fingerprint == fingerprint,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            Notification(
                user_id=user_id,
                kind=kind,
                severity=severity,
                title=title,
                body=body,
                href=href,
                fingerprint=fingerprint,
                unread=True,
                occurred_at=occurred_at,
                metadata_json=metadata_json,
            )
        )
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
        return

    existing.kind = kind
    existing.severity = severity
    existing.title = title
    existing.body = body
    existing.href = href
    existing.occurred_at = occurred_at
    existing.metadata_json = metadata_json


def refresh_notifications(
    session: Session,
    *,
    user_id: str,
    visibility: VisibilityContext,
    today: date | None = None,
) -> None:
    effective_today = today or _utcnow().date()
    horizon = effective_today + timedelta(days=7)

    latest_jobs = (
        session.execute(
            select(IngestionJob)
            .join(Source, Source.id == IngestionJob.source_id)
            .where(Source.user_id.in_((None, user_id)))
            .order_by(IngestionJob.created_at.desc())
            .limit(8)
        )
        .scalars()
        .all()
    )
    seen_job_sources: set[str] = set()
    for job in latest_jobs:
        if job.source_id in seen_job_sources:
            continue
        seen_job_sources.add(job.source_id)
        if job.status not in {"succeeded", "failed"}:
            continue
        _upsert_notification(
            session,
            user_id=user_id,
            kind=f"sync_{job.status}",
            severity="critical" if job.status == "failed" else "info",
            title=f"{job.source_id} sync {job.status}",
            body=job.error or (job.summary or {}).get("message") or "Connector run updated.",
            href="/connectors",
            fingerprint=f"sync:{job.source_id}:{job.status}:{job.finished_at or job.updated_at}",
            occurred_at=job.finished_at or job.updated_at,
            metadata_json={"source_id": job.source_id, "status": job.status},
        )

    due_occurrences = (
        session.execute(
            select(RecurringBillOccurrence, RecurringBill)
            .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
            .where(
                RecurringBill.user_id == user_id,
                RecurringBillOccurrence.status.in_(("upcoming", "due", "overdue")),
                RecurringBillOccurrence.due_date <= horizon,
            )
            .order_by(RecurringBillOccurrence.due_date.asc())
            .limit(12)
        )
        .all()
    )
    for occurrence, bill in due_occurrences:
        severity = "critical" if occurrence.due_date < effective_today else "warning"
        title = f"{bill.name} is overdue" if occurrence.due_date < effective_today else f"{bill.name} due soon"
        body = (
            f"Expected {occurrence.expected_amount_cents or 0} cents on {occurrence.due_date.isoformat()}."
        )
        _upsert_notification(
            session,
            user_id=user_id,
            kind="bill_due" if occurrence.due_date >= effective_today else "bill_overdue",
            severity=severity,
            title=title,
            body=body,
            href="/bills",
            fingerprint=f"bill:{occurrence.id}:{occurrence.status}:{occurrence.due_date.isoformat()}",
            occurred_at=datetime.combine(occurrence.due_date, datetime.min.time(), tzinfo=UTC),
            metadata_json={"bill_id": bill.id, "occurrence_id": occurrence.id},
        )

    budget_rows = budget_utilization(
        session,
        year=effective_today.year,
        month=effective_today.month,
        visibility=visibility,
        user_id=user_id,
    )["rows"]
    for row in budget_rows:
        if not row["projected_over_budget"] and row["projected_utilization"] < 0.9:
            continue
        _upsert_notification(
            session,
            user_id=user_id,
            kind="budget_risk",
            severity="warning",
            title=f"Budget risk: {row['scope_value']}",
            body=(
                f"Projected utilization is {round(row['projected_utilization'] * 100)}% of the current budget."
            ),
            href="/budget",
            fingerprint=f"budget:{row['rule_id']}:{effective_today.year}-{effective_today.month}",
            occurred_at=_utcnow(),
            metadata_json={"rule_id": row["rule_id"]},
        )

    goal_rows = goals_summary(
        session,
        user_id=user_id,
        visibility=visibility,
        from_date=effective_today.replace(day=1),
        to_date=effective_today,
    )["items"]
    for goal in goal_rows:
        status = goal["progress"]["status"]
        if status not in {"at_risk", "over_target"}:
            continue
        _upsert_notification(
            session,
            user_id=user_id,
            kind="goal_risk",
            severity="warning",
            title=f"Goal risk: {goal['name']}",
            body=(
                f"Current progress is {round(goal['progress']['progress_ratio'] * 100)}% of target."
            ),
            href="/goals",
            fingerprint=f"goal:{goal['id']}:{status}",
            occurred_at=_utcnow(),
            metadata_json={"goal_id": goal["id"], "status": status},
        )

    stale_sources = (
        session.execute(
            select(Source).where(
                Source.user_id.in_((None, user_id)),
                Source.enabled.is_(True),
                Source.status.in_(("error", "needs_attention")),
            )
        )
        .scalars()
        .all()
    )
    for source in stale_sources:
        _upsert_notification(
            session,
            user_id=user_id,
            kind="connector_attention",
            severity="warning",
            title=f"{source.display_name} needs attention",
            body=f"Connector status is {source.status}. Review the connector workspace.",
            href="/merchants",
            fingerprint=f"connector:{source.id}:{source.status}",
            occurred_at=source.updated_at,
            metadata_json={"source_id": source.id},
        )


def list_notifications(
    session: Session,
    *,
    user_id: str,
    visibility: VisibilityContext,
    limit: int = 20,
) -> dict[str, Any]:
    refresh_notifications(session, user_id=user_id, visibility=visibility)
    rows = (
        session.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.unread.desc(), Notification.occurred_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    unread_count = sum(1 for row in rows if row.unread)
    return {
        "count": len(rows),
        "unread_count": unread_count,
        "items": [_serialize_notification(row) for row in rows],
    }


def update_notification(
    session: Session,
    *,
    user_id: str,
    notification_id: str,
    unread: bool,
) -> dict[str, Any]:
    row = session.get(Notification, notification_id)
    if row is None or row.user_id != user_id:
        raise ValueError("notification not found")
    row.unread = unread
    row.read_at = None if unread else _utcnow()
    row.updated_at = _utcnow()
    session.flush()
    return _serialize_notification(row)


def mark_all_notifications_read(
    session: Session,
    *,
    user_id: str,
) -> dict[str, Any]:
    now = _utcnow()
    rows = session.execute(
        select(Notification).where(Notification.user_id == user_id, Notification.unread.is_(True))
    ).scalars().all()
    for row in rows:
        row.unread = False
        row.read_at = now
        row.updated_at = now
    session.flush()
    return {"updated": len(rows)}
