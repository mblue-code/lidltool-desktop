from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.db.engine import session_scope
from lidltool.db.models import EndpointMetric


@dataclass(slots=True)
class EndpointSLOSummary:
    generated_at: str
    window_hours: int
    thresholds: dict[str, Any]
    endpoints: list[dict[str, Any]]
    families: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "window_hours": self.window_hours,
            "thresholds": self.thresholds,
            "endpoints": self.endpoints,
            "families": self.families,
        }


def _percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(min(int(round((len(ordered) - 1) * q)), len(ordered) - 1), 0)
    return ordered[idx]


def _endpoint_family(route: str) -> str:
    if route.startswith("/api/v1/dashboard"):
        return "analytics"
    if route.startswith("/api/v1/documents"):
        return "sync"
    return "other"


def _summarize_group(route: str, rows: list[EndpointMetric]) -> dict[str, Any]:
    durations = [int(row.duration_ms) for row in rows]
    total = len(rows)
    success_count = len([row for row in rows if int(row.status_code) < 500])
    error_count = total - success_count
    success_rate = (success_count / total) if total else 1.0
    return {
        "route": route,
        "count": total,
        "success_rate": round(success_rate, 4),
        "error_rate": round((error_count / total) if total else 0.0, 4),
        "p50_duration_ms": _percentile(durations, 0.50),
        "p95_duration_ms": _percentile(durations, 0.95),
        "p99_duration_ms": _percentile(durations, 0.99),
    }


def record_endpoint_metric(
    sessions: sessionmaker[Session],
    *,
    route: str,
    method: str,
    status_code: int,
    duration_ms: int,
    source: str | None = None,
) -> None:
    with session_scope(sessions) as session:
        session.add(
            EndpointMetric(
                route=route,
                method=method.upper(),
                status_code=int(status_code),
                duration_ms=max(int(duration_ms), 0),
                source=source,
                created_at=datetime.now(tz=UTC),
            )
        )


def compute_endpoint_slo_summary(
    session: Session,
    *,
    window_hours: int = 24,
    sync_p95_target_ms: int = 2500,
    analytics_p95_target_ms: int = 2000,
    min_success_rate: float = 0.97,
) -> EndpointSLOSummary:
    window = max(int(window_hours), 1)
    since = datetime.now(tz=UTC) - timedelta(hours=window)
    rows = (
        session.execute(
            select(EndpointMetric)
            .where(EndpointMetric.created_at >= since)
            .order_by(EndpointMetric.created_at.desc())
        )
        .scalars()
        .all()
    )

    by_route: dict[str, list[EndpointMetric]] = {}
    for row in rows:
        by_route.setdefault(row.route, []).append(row)

    endpoint_rows = [
        _summarize_group(route, route_rows) for route, route_rows in sorted(by_route.items())
    ]

    family_groups: dict[str, list[dict[str, Any]]] = {}
    for summary_row in endpoint_rows:
        family_groups.setdefault(_endpoint_family(str(summary_row["route"])), []).append(
            summary_row
        )

    families: dict[str, dict[str, Any]] = {}
    for family, points in family_groups.items():
        p95_values = [
            int(item["p95_duration_ms"]) for item in points if item["p95_duration_ms"] is not None
        ]
        p95 = _percentile(p95_values, 0.95)
        success_values = [float(item["success_rate"]) for item in points]
        avg_success = (sum(success_values) / len(success_values)) if success_values else 1.0
        target = analytics_p95_target_ms if family == "analytics" else sync_p95_target_ms
        families[family] = {
            "routes": len(points),
            "p95_duration_ms": p95,
            "avg_success_rate": round(avg_success, 4),
            "p95_target_ms": target,
            "slo_pass": (p95 is None or p95 <= target) and avg_success >= min_success_rate,
        }

    return EndpointSLOSummary(
        generated_at=datetime.now(tz=UTC).isoformat(),
        window_hours=window,
        thresholds={
            "sync_p95_target_ms": sync_p95_target_ms,
            "analytics_p95_target_ms": analytics_p95_target_ms,
            "min_success_rate": min_success_rate,
        },
        endpoints=endpoint_rows,
        families=families,
    )
