from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.connectors.runtime.host import RuntimeHostedReceiptConnector
from lidltool.db.audit import record_audit_event
from lidltool.db.models import ConnectorPayloadQuarantine, SourceAccount
from lidltool.ingest.json_payloads import make_json_safe
from lidltool.ingest.validation_results import ValidationOutcome, ValidationReport


def quarantine_connector_payload(
    session: Session,
    *,
    source_id: str,
    source_account: SourceAccount | None,
    ingestion_job_id: str | None,
    connector: object | None,
    action_name: str,
    outcome: ValidationOutcome,
    source_record_ref: str,
    source_record_detail: Mapping[str, Any],
    connector_normalized: Mapping[str, Any],
    extracted_discounts: Sequence[Mapping[str, Any]],
    report: ValidationReport,
) -> ConnectorPayloadQuarantine:
    runtime_identity = _runtime_identity(connector)
    runtime_diagnostics = _runtime_diagnostics(connector)
    row = ConnectorPayloadQuarantine(
        source_id=source_id,
        source_account_id=source_account.id if source_account is not None else None,
        ingestion_job_id=ingestion_job_id,
        plugin_id=_as_optional_str(runtime_identity.get("plugin_id")),
        manifest_version=_as_optional_str(runtime_identity.get("manifest_version")),
        connector_api_version=_as_optional_str(runtime_identity.get("connector_api_version")),
        runtime_kind=_as_optional_str(runtime_identity.get("runtime_kind")),
        action_name=action_name,
        outcome=outcome.value,
        review_status="pending",
        source_record_ref=source_record_ref or None,
        payload_snapshot=make_json_safe(
            {
            "source_record_ref": source_record_ref,
            "source_record_detail": dict(source_record_detail),
            "connector_normalized": dict(connector_normalized),
            "extracted_discounts": [dict(row) for row in extracted_discounts],
            }
        ),
        validation_errors=[issue.to_payload() for issue in report.issues],
        runtime_diagnostics=make_json_safe(runtime_diagnostics),
    )
    session.add(row)
    session.flush()
    record_audit_event(
        session,
        action=f"connector.ingest.validation_{outcome.value}",
        source=source_id,
        actor_type="system",
        entity_type="connector_payload_quarantine",
        entity_id=row.id,
        details={
            "source_record_ref": source_record_ref,
            "plugin_id": row.plugin_id,
            "action_name": action_name,
            "ingestion_job_id": ingestion_job_id,
            "issue_codes": [issue.code for issue in report.issues],
        },
    )
    return row


def get_quarantined_payload(
    session: Session,
    *,
    quarantine_id: str,
) -> ConnectorPayloadQuarantine | None:
    return session.get(ConnectorPayloadQuarantine, quarantine_id)


def list_quarantined_payloads(
    session: Session,
    *,
    source_id: str | None = None,
    review_status: str | None = None,
) -> list[ConnectorPayloadQuarantine]:
    stmt = select(ConnectorPayloadQuarantine).order_by(
        ConnectorPayloadQuarantine.created_at.desc(),
        ConnectorPayloadQuarantine.id.desc(),
    )
    if source_id is not None:
        stmt = stmt.where(ConnectorPayloadQuarantine.source_id == source_id)
    if review_status is not None:
        stmt = stmt.where(ConnectorPayloadQuarantine.review_status == review_status)
    return list(session.execute(stmt).scalars().all())


def _runtime_identity(connector: object | None) -> dict[str, Any]:
    if isinstance(connector, RuntimeHostedReceiptConnector):
        return connector.runtime_identity()
    return {}


def _runtime_diagnostics(connector: object | None) -> dict[str, Any] | None:
    if not isinstance(connector, RuntimeHostedReceiptConnector):
        return None
    diagnostics = connector.latest_runtime_diagnostics()
    if not diagnostics:
        return None
    latest = diagnostics[-1].model_dump(mode="python")
    return {
        "latest": latest,
        "request_ids": [item.request_id for item in diagnostics[-5:]],
    }


def _as_optional_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None
