from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lidltool.config import AppConfig
from lidltool.connectors.connector_catalog import connector_catalog_payload
from lidltool.connectors.operator_status import (
    market_context_payload,
    operator_state_payload,
    state_legend_payload,
    support_summary_payload,
)
from lidltool.connectors.registry import ConnectorRegistry, get_connector_registry
from lidltool.db.models import ConnectorPayloadQuarantine, IngestionJob, Source, SourceAccount


def plugin_management_payload(
    session: Session,
    *,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
    include_sensitive_details: bool = True,
) -> dict[str, Any]:
    resolved_registry = registry or get_connector_registry(config)
    discovery_catalog = connector_catalog_payload(
        product="self_hosted",
        config=config,
        registry=resolved_registry,
    )
    catalog_entries = [
        entry for entry in discovery_catalog["entries"] if entry.get("entry_type") != "bundle"
    ]
    catalog_by_key = {
        _plugin_key(plugin_id=entry.get("plugin_id"), source_id=entry.get("source_id")): entry
        for entry in catalog_entries
    }

    health_by_source = _health_by_source(session)
    entries: list[dict[str, Any]] = []
    seen_keys: set[tuple[str | None, str | None]] = set()

    for registry_entry in resolved_registry.list_entries(plugin_family=None):
        key = _plugin_key(plugin_id=registry_entry.plugin_id, source_id=registry_entry.source_id)
        seen_keys.add(key)
        catalog_entry = catalog_by_key.get(key)
        health = health_by_source.get(registry_entry.source_id or "", _empty_health())
        support = support_summary_payload(registry_entry.trust_class)
        entries.append(
            {
                "plugin_id": registry_entry.plugin_id,
                "source_id": registry_entry.source_id,
                "display_name": (
                    registry_entry.manifest.display_name
                    if registry_entry.manifest is not None
                    else registry_entry.source_id or registry_entry.plugin_id or "unknown plugin"
                ),
                "plugin_family": registry_entry.plugin_family,
                "plugin_version": registry_entry.plugin_version,
                "plugin_origin": registry_entry.plugin_origin,
                "runtime_kind": registry_entry.runtime_kind,
                "status": registry_entry.status,
                "enabled": registry_entry.enabled,
                "valid": registry_entry.valid,
                "operator_state": operator_state_payload(
                    status=registry_entry.status,
                    enabled=registry_entry.enabled,
                    discovered=registry_entry.discovered,
                    plugin_origin=registry_entry.plugin_origin,
                    catalog_listed=catalog_entry is not None,
                    has_quarantine_activity=health["quarantine_events_30d"] > 0,
                    block_reason=registry_entry.block_reason,
                    status_detail=registry_entry.status_detail,
                ),
                "support": support,
                "health": health,
                "catalog": _catalog_context(catalog_entry),
                "market_context": market_context_payload(catalog_entry),
                "origin": (
                    {
                        "search_path": (
                            str(registry_entry.search_path)
                            if registry_entry.search_path is not None
                            else None
                        ),
                        "origin_path": (
                            str(registry_entry.origin_path)
                            if registry_entry.origin_path is not None
                            else None
                        ),
                        "origin_directory": (
                            str(registry_entry.origin_directory)
                            if registry_entry.origin_directory is not None
                            else None
                        ),
                    }
                    if include_sensitive_details
                    else None
                ),
                "diagnostics": list(registry_entry.diagnostics) if include_sensitive_details else [],
            }
        )

    for catalog_entry in catalog_entries:
        key = _plugin_key(plugin_id=catalog_entry.get("plugin_id"), source_id=catalog_entry.get("source_id"))
        if key in seen_keys:
            continue
        support = support_summary_payload(
            str(catalog_entry.get("trust_class")) if catalog_entry.get("trust_class") else None
        )
        entries.append(
            {
                "plugin_id": catalog_entry.get("plugin_id"),
                "source_id": catalog_entry.get("source_id"),
                "display_name": catalog_entry.get("display_name"),
                "plugin_family": "receipt",
                "plugin_version": catalog_entry.get("current_version"),
                "plugin_origin": "catalog",
                "runtime_kind": None,
                "status": None,
                "enabled": False,
                "valid": True,
                "operator_state": operator_state_payload(
                    status=None,
                    enabled=False,
                    discovered=False,
                    plugin_origin=None,
                    catalog_listed=True,
                ),
                "support": support,
                "health": _empty_health(),
                "catalog": _catalog_context(catalog_entry),
                "market_context": market_context_payload(catalog_entry),
                "origin": {
                    "search_path": None,
                    "origin_path": None,
                    "origin_directory": None,
                },
                "diagnostics": [],
            }
        )

    entries.sort(key=lambda item: (str(item.get("display_name") or ""), str(item.get("plugin_id") or "")))
    state_counts: dict[str, int] = defaultdict(int)
    health_counts: dict[str, int] = defaultdict(int)
    for item in entries:
        state_counts[str(item["operator_state"]["primary_state"])] += 1
        health_counts[str(item["health"]["status"])] += 1

    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "search_paths": (
            [str(path) for path in config.connector_plugin_search_paths]
            if config is not None and include_sensitive_details
            else []
        ),
        "rescan_supported": True,
        "summary": {
            "total_plugins": len(entries),
            "by_primary_state": dict(sorted(state_counts.items())),
            "by_health_status": dict(sorted(health_counts.items())),
            "quarantine_present": sum(
                1 for item in entries if bool(item["health"]["quarantine_events_30d"])
            ),
            "auth_issues_present": sum(
                1 for item in entries if bool(item["health"]["auth_issue_present"])
            ),
        },
        "state_legend": state_legend_payload(),
        "entries": entries,
    }


def _plugin_key(*, plugin_id: Any, source_id: Any) -> tuple[str | None, str | None]:
    normalized_plugin = str(plugin_id) if isinstance(plugin_id, str) and plugin_id else None
    normalized_source = str(source_id) if isinstance(source_id, str) and source_id else None
    return normalized_plugin, normalized_source


def _catalog_context(catalog_entry: dict[str, Any] | None) -> dict[str, Any]:
    if catalog_entry is None:
        return {
            "listed": False,
            "entry_id": None,
            "current_version": None,
            "summary": "Not listed in the curated catalog.",
        }
    return {
        "listed": True,
        "entry_id": catalog_entry.get("entry_id"),
        "current_version": catalog_entry.get("current_version"),
        "summary": catalog_entry.get("summary"),
    }


def _health_by_source(session: Session) -> dict[str, dict[str, Any]]:
    cutoff = datetime.now(tz=UTC) - timedelta(days=30)

    quarantine_rows = session.execute(
        select(
            ConnectorPayloadQuarantine.source_id,
            func.count(ConnectorPayloadQuarantine.id),
            func.max(ConnectorPayloadQuarantine.created_at),
        )
        .where(ConnectorPayloadQuarantine.created_at >= cutoff)
        .group_by(ConnectorPayloadQuarantine.source_id)
    ).all()
    pending_review_by_source = {
        str(source_id): int(count)
        for source_id, count in session.execute(
            select(
                ConnectorPayloadQuarantine.source_id,
                func.count(ConnectorPayloadQuarantine.id),
            )
            .where(ConnectorPayloadQuarantine.review_status == "pending")
            .group_by(ConnectorPayloadQuarantine.source_id)
        ).all()
    }

    failed_rows = session.execute(
        select(
            IngestionJob.source_id,
            func.count(IngestionJob.id),
            func.max(IngestionJob.finished_at),
        )
        .where(IngestionJob.created_at >= cutoff)
        .where(IngestionJob.status.in_(("failed", "canceled")))
        .group_by(IngestionJob.source_id)
    ).all()

    latest_jobs = session.execute(
        select(IngestionJob).order_by(IngestionJob.source_id.asc(), IngestionJob.created_at.desc())
    ).scalars()
    latest_job_by_source: dict[str, IngestionJob] = {}
    for job in latest_jobs:
        if job.source_id not in latest_job_by_source:
            latest_job_by_source[job.source_id] = job

    source_rows = {
        source.id: source
        for source in session.execute(select(Source)).scalars().all()
    }
    account_rows = session.execute(select(SourceAccount)).scalars().all()
    auth_issue_by_source: dict[str, bool] = defaultdict(bool)
    for account in account_rows:
        if account.status.lower() != "connected":
            auth_issue_by_source[account.source_id] = True

    payload: dict[str, dict[str, Any]] = defaultdict(_empty_health)
    for source_id, count, latest_created_at in quarantine_rows:
        item = payload[str(source_id)]
        item["quarantine_events_30d"] = int(count)
        item["latest_quarantine_at"] = (
            latest_created_at.isoformat() if latest_created_at is not None else None
        )
        item["pending_quarantine_reviews"] = pending_review_by_source.get(str(source_id), 0)
    for source_id, count, latest_failed_at in failed_rows:
        item = payload[str(source_id)]
        item["recent_failures_30d"] = int(count)
        item["latest_failure_at"] = latest_failed_at.isoformat() if latest_failed_at else None

    for source_id, source in source_rows.items():
        item = payload[str(source_id)]
        latest_job = latest_job_by_source.get(source_id)
        latest_warning_count = 0
        latest_warning_messages: list[str] = []
        if latest_job is not None and isinstance(latest_job.summary, dict):
            warnings = latest_job.summary.get("warnings")
            if isinstance(warnings, list):
                latest_warning_messages = [str(item) for item in warnings if str(item)]
                latest_warning_count = len(latest_warning_messages)
            elif isinstance(latest_job.summary.get("result"), dict):
                result_warnings = latest_job.summary["result"].get("warnings")
                if isinstance(result_warnings, list):
                    latest_warning_messages = [str(item) for item in result_warnings if str(item)]
                    latest_warning_count = len(latest_warning_messages)
        auth_issue_present = auth_issue_by_source[source_id] or source.status.lower() in {
            "expired_auth",
            "auth_required",
        }
        item["latest_warning_count"] = latest_warning_count
        item["latest_warning_messages"] = latest_warning_messages[:5]
        item["auth_issue_present"] = auth_issue_present
        item["status"] = _health_status(item)
        item["summary"] = _health_summary(item)

    return payload


def _empty_health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "summary": "No recent plugin health issues were recorded.",
        "quarantine_events_30d": 0,
        "pending_quarantine_reviews": 0,
        "latest_quarantine_at": None,
        "recent_failures_30d": 0,
        "latest_failure_at": None,
        "latest_warning_count": 0,
        "latest_warning_messages": [],
        "auth_issue_present": False,
    }


def _health_status(item: dict[str, Any]) -> str:
    if item["pending_quarantine_reviews"] or item["recent_failures_30d"] or item["auth_issue_present"]:
        return "needs_attention"
    if item["quarantine_events_30d"] or item["latest_warning_count"]:
        return "warning"
    return "healthy"


def _health_summary(item: dict[str, Any]) -> str:
    parts: list[str] = []
    if item["pending_quarantine_reviews"]:
        parts.append(f"{item['pending_quarantine_reviews']} quarantine item(s) still need review")
    elif item["quarantine_events_30d"]:
        parts.append(f"{item['quarantine_events_30d']} recent quarantine event(s)")
    if item["recent_failures_30d"]:
        parts.append(f"{item['recent_failures_30d']} failed or canceled sync run(s) in the last 30 days")
    if item["latest_warning_count"]:
        parts.append(f"{item['latest_warning_count']} warning(s) on the latest sync result")
    if item["auth_issue_present"]:
        parts.append("authentication needs attention")
    if not parts:
        return "No recent plugin health issues were recorded."
    return ". ".join(parts).capitalize() + "."
