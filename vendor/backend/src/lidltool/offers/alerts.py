from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.db.models import AlertEvent, OfferMatch


def emit_alert_event_for_match(session: Session, *, match: OfferMatch) -> tuple[AlertEvent, bool]:
    dedupe_key = f"offer-match:{match.match_key}"
    existing = session.execute(
        select(AlertEvent).where(AlertEvent.dedupe_key == dedupe_key).limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    reason = dict(match.reason_json or {})
    title = reason.get("title")
    if not isinstance(title, str) or not title.strip():
        title = "Matched offer"
    body = reason.get("summary")
    if not isinstance(body, str) or not body.strip():
        body = None

    event = AlertEvent(
        user_id=match.user_id,
        offer_match_id=match.id,
        event_type="offer_match",
        status="pending",
        dedupe_key=dedupe_key,
        title=title,
        body=body,
        payload_json=reason,
    )
    session.add(event)
    match.status = "alerted"
    session.flush()
    return event, True
