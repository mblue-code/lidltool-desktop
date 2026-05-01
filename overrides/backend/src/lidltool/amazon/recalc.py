from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.amazon.order_money import (
    amazon_financials_payload,
    normalize_order_financials,
    to_int_cents,
)
from lidltool.db.models import ConnectorConfigState, Transaction

AMAZON_FINANCIAL_RECALC_VERSION = "net-spend-v1"
_RECALC_VERSION_KEY = "_amazon_financial_recalc_version"


@dataclass(frozen=True, slots=True)
class AmazonRecalcResult:
    scanned: int
    updated: int
    unchanged: int
    skipped: int
    warnings: tuple[str, ...] = ()


def recalculate_amazon_transaction_financials(
    session: Session,
    *,
    source_id: str | None = None,
    user_id: str | None = None,
    shared_group_id: str | None = None,
) -> AmazonRecalcResult:
    scanned = 0
    updated = 0
    unchanged = 0
    skipped = 0
    warnings: list[str] = []

    stmt = select(Transaction)
    if source_id:
        stmt = stmt.where(Transaction.source_id == source_id)
    else:
        stmt = stmt.where(Transaction.source_id.like("amazon_%"))
    if user_id is not None:
        stmt = stmt.where(Transaction.user_id == user_id)
    if shared_group_id is not None:
        stmt = stmt.where(Transaction.shared_group_id == shared_group_id)
    transactions = (
        session.execute(stmt.order_by(Transaction.purchased_at.asc(), Transaction.source_transaction_id.asc()))
        .scalars()
        .all()
    )
    for transaction in transactions:
        scanned += 1
        payload = transaction.raw_payload if isinstance(transaction.raw_payload, dict) else {}
        order_payload = _extract_order_payload(payload)
        if order_payload is None:
            skipped += 1
            warnings.append(f"{transaction.source_transaction_id}: missing Amazon raw payload")
            continue

        current_raw_total = _current_gross_total_cents(payload, transaction)
        financials = normalize_order_financials(order_payload, gross_total_cents=current_raw_total)
        if financials.warnings:
            skipped += 1
            warnings.append(
                f"{transaction.source_transaction_id}: {','.join(financials.warnings)}"
            )
            continue

        next_payload = _with_financial_payload(payload, financials_payload=amazon_financials_payload(financials))
        next_total = financials.net_spending_total_cents
        if transaction.total_gross_cents == next_total and transaction.raw_payload == next_payload:
            unchanged += 1
            continue

        transaction.total_gross_cents = next_total
        transaction.raw_payload = next_payload
        updated += 1

    return AmazonRecalcResult(
        scanned=scanned,
        updated=updated,
        unchanged=unchanged,
        skipped=skipped,
        warnings=tuple(warnings),
    )


def amazon_financial_recalc_marker_current(
    session: Session,
    *,
    source_id: str,
    version: str = AMAZON_FINANCIAL_RECALC_VERSION,
) -> bool:
    row = session.get(ConnectorConfigState, source_id)
    public_config = row.public_config_json if row is not None else None
    if not isinstance(public_config, dict):
        return False
    return public_config.get(_RECALC_VERSION_KEY) == version


def mark_amazon_financial_recalc_current(
    session: Session,
    *,
    source_id: str,
    version: str = AMAZON_FINANCIAL_RECALC_VERSION,
) -> None:
    row = session.get(ConnectorConfigState, source_id)
    if row is None:
        row = ConnectorConfigState(source_id=source_id)
        session.add(row)
        session.flush()
    public_config = dict(row.public_config_json or {})
    public_config[_RECALC_VERSION_KEY] = version
    row.public_config_json = public_config


def run_scoped_amazon_financial_recalc_if_needed(
    session: Session,
    *,
    source_id: str,
    user_id: str | None,
    shared_group_id: str | None = None,
    version: str = AMAZON_FINANCIAL_RECALC_VERSION,
) -> dict[str, Any]:
    if amazon_financial_recalc_marker_current(session, source_id=source_id, version=version):
        return {
            "version": version,
            "skipped_reason": "marker_current",
            "scanned": 0,
            "updated": 0,
            "unchanged": 0,
            "skipped": 0,
            "warning_count": 0,
        }
    result = recalculate_amazon_transaction_financials(
        session,
        source_id=source_id,
        user_id=user_id,
        shared_group_id=shared_group_id,
    )
    mark_amazon_financial_recalc_current(session, source_id=source_id, version=version)
    return {
        "version": version,
        "scanned": result.scanned,
        "updated": result.updated,
        "unchanged": result.unchanged,
        "skipped": result.skipped,
        "warning_count": len(result.warnings),
    }


def _extract_order_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    source_record_detail = payload.get("source_record_detail")
    connector_normalized = payload.get("connector_normalized")
    for candidate in (source_record_detail, connector_normalized):
        if not isinstance(candidate, dict):
            continue
        original_order = candidate.get("originalOrder")
        if isinstance(original_order, dict):
            merged = dict(candidate)
            merged["originalOrder"] = original_order
            return merged
        if candidate.get("subtotals") is not None:
            return candidate
    return None


def _current_gross_total_cents(payload: dict[str, Any], transaction: Transaction) -> int:
    source_record_detail = payload.get("source_record_detail")
    if isinstance(source_record_detail, dict):
        financials = source_record_detail.get("amazonFinancials")
        if isinstance(financials, dict) and financials.get("gross_total_cents") is not None:
            return max(0, to_int_cents(financials.get("gross_total_cents")))
        if source_record_detail.get("totalGross") is not None:
            return max(0, to_int_cents(source_record_detail.get("totalGross")))
    connector_normalized = payload.get("connector_normalized")
    if isinstance(connector_normalized, dict):
        raw_json = connector_normalized.get("raw_json")
        if isinstance(raw_json, dict):
            financials = raw_json.get("amazonFinancials")
            if isinstance(financials, dict) and financials.get("gross_total_cents") is not None:
                return max(0, to_int_cents(financials.get("gross_total_cents")))
        if connector_normalized.get("total_gross_cents") is not None:
            return max(0, to_int_cents(connector_normalized.get("total_gross_cents")))
    return max(0, int(transaction.total_gross_cents or 0))


def _with_financial_payload(
    payload: dict[str, Any],
    *,
    financials_payload: dict[str, Any],
) -> dict[str, Any]:
    next_payload = dict(payload)
    source_record_detail = next_payload.get("source_record_detail")
    if isinstance(source_record_detail, dict):
        next_source_record_detail = dict(source_record_detail)
        next_source_record_detail["amazonFinancials"] = financials_payload
        next_source_record_detail["totalGross"] = financials_payload["net_spending_total_cents"] / 100.0
        next_payload["source_record_detail"] = next_source_record_detail

    connector_normalized = next_payload.get("connector_normalized")
    if isinstance(connector_normalized, dict):
        next_connector_normalized = dict(connector_normalized)
        next_connector_normalized["total_gross_cents"] = financials_payload["net_spending_total_cents"]
        raw_json = next_connector_normalized.get("raw_json")
        if isinstance(raw_json, dict):
            next_raw_json = dict(raw_json)
            next_raw_json["amazonFinancials"] = financials_payload
            next_raw_json["totalGross"] = financials_payload["net_spending_total_cents"] / 100.0
            next_connector_normalized["raw_json"] = next_raw_json
        next_payload["connector_normalized"] = next_connector_normalized

    return next_payload
