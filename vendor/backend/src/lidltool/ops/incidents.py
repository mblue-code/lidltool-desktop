from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.db.engine import session_scope
from lidltool.db.models import IncidentEvent


def record_incident_event(
    sessions: sessionmaker[Session],
    *,
    incident_key: str,
    event_type: str,
    severity: str = "sev3",
    source: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    with session_scope(sessions) as session:
        session.add(
            IncidentEvent(
                incident_key=incident_key,
                event_type=event_type,
                severity=severity,
                source=source,
                details=details,
                created_at=datetime.now(tz=UTC),
            )
        )


def simulate_incident(
    sessions: sessionmaker[Session],
    *,
    incident_key: str,
    severity: str,
    scenario: str,
    recovery_delay_seconds: int = 1,
    source: str | None = None,
) -> dict[str, Any]:
    started_at = datetime.now(tz=UTC)
    mitigated_at = started_at + timedelta(seconds=max(recovery_delay_seconds // 2, 1))
    resolved_at = started_at + timedelta(seconds=max(recovery_delay_seconds, 1))

    with session_scope(sessions) as session:
        session.add(
            IncidentEvent(
                incident_key=incident_key,
                event_type="started",
                severity=severity,
                source=source,
                details={"scenario": scenario},
                created_at=started_at,
            )
        )
        session.add(
            IncidentEvent(
                incident_key=incident_key,
                event_type="mitigated",
                severity=severity,
                source=source,
                details={"scenario": scenario},
                created_at=mitigated_at,
            )
        )
        session.add(
            IncidentEvent(
                incident_key=incident_key,
                event_type="resolved",
                severity=severity,
                source=source,
                details={"scenario": scenario},
                created_at=resolved_at,
            )
        )
    return {
        "incident_key": incident_key,
        "severity": severity,
        "scenario": scenario,
        "started_at": started_at.isoformat(),
        "resolved_at": resolved_at.isoformat(),
        "mttr_seconds": int((resolved_at - started_at).total_seconds()),
    }


def compute_mttr_summary(session: Session, *, window_days: int = 14) -> dict[str, Any]:
    since = datetime.now(tz=UTC) - timedelta(days=max(window_days, 1))
    rows = (
        session.execute(
            select(IncidentEvent)
            .where(IncidentEvent.created_at >= since)
            .order_by(IncidentEvent.incident_key.asc(), IncidentEvent.created_at.asc())
        )
        .scalars()
        .all()
    )
    by_incident: dict[str, list[IncidentEvent]] = {}
    for row in rows:
        by_incident.setdefault(row.incident_key, []).append(row)

    incident_summaries: list[dict[str, Any]] = []
    mttrs: list[int] = []
    for key, events in by_incident.items():
        started = next((event for event in events if event.event_type == "started"), None)
        resolved = next((event for event in events if event.event_type == "resolved"), None)
        if started is None or resolved is None:
            continue
        mttr_seconds = max(int((resolved.created_at - started.created_at).total_seconds()), 0)
        mttrs.append(mttr_seconds)
        incident_summaries.append(
            {
                "incident_key": key,
                "severity": started.severity,
                "source": started.source,
                "started_at": started.created_at.isoformat(),
                "resolved_at": resolved.created_at.isoformat(),
                "mttr_seconds": mttr_seconds,
            }
        )

    avg_mttr_seconds = (sum(mttrs) / len(mttrs)) if mttrs else 0.0
    by_severity: dict[str, int] = {}
    for incident in incident_summaries:
        sev = str(incident["severity"])
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "window_days": window_days,
        "incidents_total": len(incident_summaries),
        "avg_mttr_seconds": round(avg_mttr_seconds, 2),
        "max_mttr_seconds": max(mttrs) if mttrs else 0,
        "by_severity": by_severity,
        "incidents": incident_summaries,
    }


def write_mttr_report(
    session: Session,
    *,
    out_path: str,
    window_days: int = 14,
) -> dict[str, Any]:
    result = compute_mttr_summary(session, window_days=window_days)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    return result
