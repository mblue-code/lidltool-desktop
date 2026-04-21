from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from lidltool.ai.schemas import validate_ai_mediation_response
from lidltool.connectors.sdk.receipt import (
    NormalizedDiscountRow,
    NormalizedReceiptItem,
    NormalizedReceiptRecord,
)
from lidltool.ingest.validation_results import (
    ValidationReport,
    ValidationSeverity,
)

_MIN_PLAUSIBLE_PURCHASED_AT = datetime(2000, 1, 1, tzinfo=UTC)
_MAX_FUTURE_SKEW = timedelta(days=2)
_MAX_REASONABLE_TOTAL_CENTS = 10_000_000
_WARN_TOTAL_MISMATCH_CENTS = 2
_QUARANTINE_TOTAL_MISMATCH_CENTS = 100
_WARN_DISCOUNT_MISMATCH_CENTS = 2
_QUARANTINE_DISCOUNT_MISMATCH_CENTS = 500
_MAX_REASONABLE_QTY = Decimal("1000")


def validate_normalized_connector_payload(
    *,
    source_record_ref: str,
    source_record_detail: Mapping[str, Any],
    connector_normalized: Mapping[str, Any],
    extracted_discounts: Sequence[Mapping[str, Any] | NormalizedDiscountRow],
    now: datetime | None = None,
) -> ValidationReport:
    report = ValidationReport()
    inspected_at = _as_utc(now or datetime.now(tz=UTC))
    report.inspected_at = inspected_at

    normalized_record = _validate_normalized_record_shape(
        report=report,
        connector_normalized=connector_normalized,
    )
    discount_rows = _validate_discount_shapes(
        report=report,
        extracted_discounts=extracted_discounts,
    )
    if normalized_record is None:
        return report

    _validate_provenance(
        report=report,
        source_record_ref=source_record_ref,
        source_record_detail=source_record_detail,
        normalized_record=normalized_record,
    )
    _validate_transaction_payload(
        report=report,
        normalized_record=normalized_record,
        inspected_at=inspected_at,
    )
    item_index = _validate_items(report=report, normalized_record=normalized_record)
    _validate_discounts(report=report, discount_rows=discount_rows, item_index=item_index)
    _validate_cross_field_consistency(
        report=report,
        normalized_record=normalized_record,
        discount_rows=discount_rows,
    )
    _validate_ai_assistance(
        report=report,
        source_record_detail=source_record_detail,
        normalized_record=normalized_record,
    )
    return report


def _validate_normalized_record_shape(
    *,
    report: ValidationReport,
    connector_normalized: Mapping[str, Any],
) -> NormalizedReceiptRecord | None:
    payload = dict(connector_normalized)
    if payload.get("discount_total_cents") is None:
        payload["discount_total_cents"] = 0
    try:
        return NormalizedReceiptRecord.model_validate(payload)
    except ValidationError as exc:
        report.add_issue(
            code="normalized_record_shape_invalid",
            severity=ValidationSeverity.REJECT,
            message="connector normalized receipt payload failed schema validation",
            path="$.normalized_record",
            details={"errors": exc.errors(include_url=False)},
        )
        return None


def _validate_discount_shapes(
    *,
    report: ValidationReport,
    extracted_discounts: Sequence[Mapping[str, Any] | NormalizedDiscountRow],
) -> list[NormalizedDiscountRow]:
    rows: list[NormalizedDiscountRow] = []
    for index, raw_row in enumerate(extracted_discounts):
        try:
            row = (
                raw_row
                if isinstance(raw_row, NormalizedDiscountRow)
                else NormalizedDiscountRow.model_validate(_coerce_discount_payload(dict(raw_row)))
            )
        except ValidationError as exc:
            report.add_issue(
                code="discount_shape_invalid",
                severity=ValidationSeverity.REJECT,
                message="connector discount payload failed schema validation",
                path=f"$.discounts[{index}]",
                details={"errors": exc.errors(include_url=False)},
            )
            continue
        rows.append(row)
    return rows


def _validate_provenance(
    *,
    report: ValidationReport,
    source_record_ref: str,
    source_record_detail: Mapping[str, Any],
    normalized_record: NormalizedReceiptRecord,
) -> None:
    if not source_record_ref.strip():
        report.add_issue(
            code="missing_source_record_ref",
            severity=ValidationSeverity.REJECT,
            message="source record reference is required for canonical provenance",
            path="$.source_record_ref",
        )
    if not dict(source_record_detail):
        report.add_issue(
            code="missing_source_record_detail",
            severity=ValidationSeverity.REJECT,
            message="source record detail snapshot is required for canonical provenance",
            path="$.source_record_detail",
        )
    if not normalized_record.raw_json:
        report.add_issue(
            code="missing_raw_json",
            severity=ValidationSeverity.REJECT,
            message="normalized receipt payload must include a raw_json provenance snapshot",
            path="$.normalized_record.raw_json",
        )


def _validate_transaction_payload(
    *,
    report: ValidationReport,
    normalized_record: NormalizedReceiptRecord,
    inspected_at: datetime,
) -> None:
    if not normalized_record.id.strip():
        report.add_issue(
            code="missing_transaction_id",
            severity=ValidationSeverity.REJECT,
            message="normalized receipt payload is missing an id",
            path="$.normalized_record.id",
        )
    if not normalized_record.store_id.strip():
        report.add_issue(
            code="missing_store_id",
            severity=ValidationSeverity.REJECT,
            message="normalized receipt payload is missing a store_id",
            path="$.normalized_record.store_id",
        )
    if not normalized_record.store_name.strip():
        report.add_issue(
            code="missing_store_name",
            severity=ValidationSeverity.WARN,
            message="normalized receipt payload is missing a store_name",
            path="$.normalized_record.store_name",
        )
    if not normalized_record.fingerprint.strip():
        report.add_issue(
            code="missing_fingerprint",
            severity=ValidationSeverity.REJECT,
            message="normalized receipt payload is missing a fingerprint",
            path="$.normalized_record.fingerprint",
        )
    if not _looks_like_currency(normalized_record.currency):
        report.add_issue(
            code="invalid_currency",
            severity=ValidationSeverity.REJECT,
            message="currency must be a three-letter alphabetic code",
            path="$.normalized_record.currency",
            details={"currency": normalized_record.currency},
        )

    purchased_at = _as_utc(normalized_record.purchased_at)
    if purchased_at < _MIN_PLAUSIBLE_PURCHASED_AT:
        report.add_issue(
            code="purchased_at_implausibly_old",
            severity=ValidationSeverity.QUARANTINE,
            message="purchased_at is implausibly old and requires review",
            path="$.normalized_record.purchased_at",
            details={"purchased_at": purchased_at.isoformat()},
        )
    if purchased_at > inspected_at + _MAX_FUTURE_SKEW:
        report.add_issue(
            code="purchased_at_in_future",
            severity=ValidationSeverity.QUARANTINE,
            message="purchased_at is implausibly far in the future",
            path="$.normalized_record.purchased_at",
            details={"purchased_at": purchased_at.isoformat()},
        )

    if normalized_record.total_gross_cents < 0:
        report.add_issue(
            code="negative_total_gross",
            severity=ValidationSeverity.REJECT,
            message="total_gross_cents must not be negative",
            path="$.normalized_record.total_gross_cents",
            details={"total_gross_cents": normalized_record.total_gross_cents},
        )
    elif normalized_record.total_gross_cents == 0:
        report.add_issue(
            code="zero_total_gross",
            severity=ValidationSeverity.WARN,
            message="total_gross_cents is zero; ingesting with warning",
            path="$.normalized_record.total_gross_cents",
        )
    elif normalized_record.total_gross_cents > _MAX_REASONABLE_TOTAL_CENTS:
        report.add_issue(
            code="total_gross_implausibly_large",
            severity=ValidationSeverity.QUARANTINE,
            message="total_gross_cents is implausibly large and requires review",
            path="$.normalized_record.total_gross_cents",
            details={"total_gross_cents": normalized_record.total_gross_cents},
        )

    if normalized_record.discount_total_cents < 0:
        report.add_issue(
            code="negative_discount_total",
            severity=ValidationSeverity.REJECT,
            message="discount_total_cents must not be negative",
            path="$.normalized_record.discount_total_cents",
            details={"discount_total_cents": normalized_record.discount_total_cents},
        )


def _validate_items(
    *,
    report: ValidationReport,
    normalized_record: NormalizedReceiptRecord,
) -> dict[int, NormalizedReceiptItem]:
    item_index: dict[int, NormalizedReceiptItem] = {}
    source_item_ids: set[str] = set()
    for item in normalized_record.items:
        item_path = f"$.normalized_record.items[{item.line_no}]"
        if item.line_no in item_index:
            report.add_issue(
                code="duplicate_line_no",
                severity=ValidationSeverity.REJECT,
                message="normalized items contain duplicate line_no values",
                path=f"{item_path}.line_no",
                details={"line_no": item.line_no},
            )
            continue
        item_index[item.line_no] = item

        if not item.name.strip():
            report.add_issue(
                code="missing_item_name",
                severity=ValidationSeverity.REJECT,
                message="normalized items must include a non-empty name",
                path=f"{item_path}.name",
            )

        qty = _parse_decimal(item.qty, path=f"{item_path}.qty", report=report)
        if qty is None:
            continue
        if qty <= 0:
            report.add_issue(
                code="non_positive_item_qty",
                severity=ValidationSeverity.REJECT,
                message="item qty must be greater than zero",
                path=f"{item_path}.qty",
                details={"qty": item.qty},
            )
        elif qty > _MAX_REASONABLE_QTY:
            report.add_issue(
                code="item_qty_implausibly_large",
                severity=ValidationSeverity.QUARANTINE,
                message="item qty is implausibly large and requires review",
                path=f"{item_path}.qty",
                details={"qty": item.qty},
            )

        allows_negative_deposit_return = bool(item.is_deposit) and item.line_total_cents < 0

        if (
            item.unit_price_cents is not None
            and item.unit_price_cents < 0
            and not allows_negative_deposit_return
        ):
            report.add_issue(
                code="negative_unit_price",
                severity=ValidationSeverity.REJECT,
                message="item unit_price_cents must not be negative",
                path=f"{item_path}.unit_price_cents",
                details={"unit_price_cents": item.unit_price_cents},
            )
        if item.line_total_cents < 0 and not allows_negative_deposit_return:
            report.add_issue(
                code="negative_line_total",
                severity=ValidationSeverity.REJECT,
                message="item line_total_cents must not be negative",
                path=f"{item_path}.line_total_cents",
                details={"line_total_cents": item.line_total_cents},
            )

        if item.source_item_id is not None and item.source_item_id.strip():
            if item.source_item_id in source_item_ids:
                report.add_issue(
                    code="duplicate_source_item_id",
                    severity=ValidationSeverity.QUARANTINE,
                    message="normalized items contain duplicate source_item_id values",
                    path=f"{item_path}.source_item_id",
                    details={"source_item_id": item.source_item_id},
                )
            source_item_ids.add(item.source_item_id)

        _validate_item_price_consistency(
            report=report,
            item=item,
            qty=qty,
            item_path=item_path,
        )
    return item_index


def _validate_item_price_consistency(
    *,
    report: ValidationReport,
    item: NormalizedReceiptItem,
    qty: Decimal,
    item_path: str,
) -> None:
    if item.unit_price_cents is None:
        return
    expected_total = int((qty * Decimal(item.unit_price_cents)).quantize(Decimal("1")))
    item_discount_total = _discount_hint_total(item.discounts)
    candidate_totals = {expected_total}
    if item_discount_total > 0:
        candidate_totals.add(max(expected_total - item_discount_total, 0))
    delta = min(abs(item.line_total_cents - candidate_total) for candidate_total in candidate_totals)
    if delta <= _WARN_TOTAL_MISMATCH_CENTS:
        return
    severity = (
        ValidationSeverity.WARN if item_discount_total > 0 else ValidationSeverity.QUARANTINE
    )
    report.add_issue(
        code="item_total_inconsistent",
        severity=severity,
        message="item line_total_cents is inconsistent with qty and unit_price_cents",
        path=f"{item_path}.line_total_cents",
        details={
            "line_total_cents": item.line_total_cents,
            "expected_total_cents": expected_total,
            "discount_hint_cents": item_discount_total,
        },
    )


def _validate_discounts(
    *,
    report: ValidationReport,
    discount_rows: Sequence[NormalizedDiscountRow],
    item_index: Mapping[int, NormalizedReceiptItem],
) -> None:
    seen_discount_keys: set[tuple[int | None, str, int, str, str]] = set()
    for index, discount in enumerate(discount_rows):
        path = f"$.discounts[{index}]"
        if not discount.label.strip():
            report.add_issue(
                code="missing_discount_label",
                severity=ValidationSeverity.REJECT,
                message="discount rows must include a non-empty label",
                path=f"{path}.label",
            )
        if discount.scope == "item" and discount.line_no is None:
            report.add_issue(
                code="item_discount_missing_line_no",
                severity=ValidationSeverity.REJECT,
                message="item-scoped discount rows must include line_no",
                path=f"{path}.line_no",
            )
        if discount.line_no is not None and discount.line_no not in item_index:
            report.add_issue(
                code="discount_line_no_missing_item",
                severity=ValidationSeverity.QUARANTINE,
                message="discount row references a missing item line",
                path=f"{path}.line_no",
                details={"line_no": discount.line_no},
            )
        if discount.scope == "transaction" and discount.line_no is not None:
            report.add_issue(
                code="transaction_discount_line_no_present",
                severity=ValidationSeverity.WARN,
                message="transaction-scoped discount row includes a line_no; ingesting with warning",
                path=f"{path}.line_no",
            )

        discount_key = (
            discount.line_no,
            discount.type,
            discount.amount_cents,
            discount.label,
            discount.scope,
        )
        if discount_key in seen_discount_keys:
            report.add_issue(
                code="duplicate_discount_row",
                severity=ValidationSeverity.WARN,
                message="duplicate discount row detected; ingesting with warning",
                path=path,
                details={"discount": discount.model_dump(mode="python")},
            )
        seen_discount_keys.add(discount_key)


def _validate_cross_field_consistency(
    *,
    report: ValidationReport,
    normalized_record: NormalizedReceiptRecord,
    discount_rows: Sequence[NormalizedDiscountRow],
) -> None:
    item_total_cents = sum(
        item.line_total_cents for item in normalized_record.items if not bool(item.is_deposit)
    )
    deposit_total_cents = sum(
        item.line_total_cents for item in normalized_record.items if bool(item.is_deposit)
    )
    extracted_discount_total = sum(row.amount_cents for row in discount_rows)
    candidate_totals = {item_total_cents, item_total_cents - extracted_discount_total}
    if normalized_record.discount_total_cents > 0:
        candidate_totals.add(
            item_total_cents - normalized_record.discount_total_cents
        )
    matched_total_cents = min(
        candidate_totals,
        key=lambda candidate_total: abs(candidate_total - normalized_record.total_gross_cents),
    )
    total_delta = abs(matched_total_cents - normalized_record.total_gross_cents)
    if total_delta > _WARN_TOTAL_MISMATCH_CENTS:
        severity = (
            ValidationSeverity.WARN
            if total_delta <= _QUARANTINE_TOTAL_MISMATCH_CENTS
            else ValidationSeverity.QUARANTINE
        )
        report.add_issue(
            code="transaction_total_mismatch",
            severity=severity,
            message="transaction total does not match the sum of normalized item totals",
            path="$.normalized_record.total_gross_cents",
            details={
                "total_gross_cents": normalized_record.total_gross_cents,
                "item_total_cents": item_total_cents,
                "deposit_total_cents": deposit_total_cents,
                "deposit_adjustment_cents": deposit_total_cents,
                "extracted_discount_total_cents": extracted_discount_total,
                "matched_total_cents": matched_total_cents,
                "delta_cents": total_delta,
            },
        )

    if normalized_record.discount_total_cents > 0:
        discount_delta = abs(extracted_discount_total - normalized_record.discount_total_cents)
        if discount_delta > _WARN_DISCOUNT_MISMATCH_CENTS:
            severity = (
                ValidationSeverity.WARN
                if discount_delta <= _QUARANTINE_DISCOUNT_MISMATCH_CENTS
                else ValidationSeverity.QUARANTINE
            )
            report.add_issue(
                code="discount_total_mismatch",
                severity=severity,
                message="discount_total_cents does not match extracted discount rows",
                path="$.normalized_record.discount_total_cents",
                details={
                    "discount_total_cents": normalized_record.discount_total_cents,
                    "extracted_discount_total_cents": extracted_discount_total,
                    "delta_cents": discount_delta,
                },
            )


def _validate_ai_assistance(
    *,
    report: ValidationReport,
    source_record_detail: Mapping[str, Any],
    normalized_record: NormalizedReceiptRecord,
) -> None:
    candidates = [
        ("$.source_record_detail.ai_mediation", source_record_detail.get("ai_mediation")),
        ("$.normalized_record.raw_json.ai_mediation", normalized_record.raw_json.get("ai_mediation")),
    ]
    for path, candidate in candidates:
        if candidate is None:
            continue
        if not isinstance(candidate, Mapping):
            report.add_issue(
                code="ai_mediation_shape_invalid",
                severity=ValidationSeverity.REJECT,
                message="embedded ai_mediation payload must be an object",
                path=path,
            )
            continue
        try:
            response = validate_ai_mediation_response(dict(candidate))
        except Exception as exc:
            report.add_issue(
                code="ai_mediation_shape_invalid",
                severity=ValidationSeverity.REJECT,
                message="embedded ai_mediation payload failed schema validation",
                path=path,
                details={"error": str(exc)},
            )
            continue
        if not response.ok:
            report.add_issue(
                code="ai_mediation_failed",
                severity=ValidationSeverity.REJECT,
                message="connector output references a failed AI mediation response",
                path=path,
                details={
                    "error_code": response.error.code if response.error is not None else None,
                    "request_id": response.request_id,
                },
            )
        elif response.warnings:
            report.add_issue(
                code="ai_mediation_warnings_present",
                severity=ValidationSeverity.WARN,
                message="connector output was AI-assisted and carries mediation warnings",
                path=path,
                details={"warnings": list(response.warnings), "request_id": response.request_id},
            )


def _parse_decimal(
    value: str,
    *,
    path: str,
    report: ValidationReport,
) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ".").strip())
    except (AttributeError, InvalidOperation):
        report.add_issue(
            code="invalid_decimal",
            severity=ValidationSeverity.REJECT,
            message="decimal field failed parsing",
            path=path,
            details={"value": value},
        )
        return None


def _discount_hint_total(discounts: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for raw_discount in discounts:
        amount = raw_discount.get("amount_cents")
        if isinstance(amount, bool):
            continue
        if isinstance(amount, int):
            total += abs(amount)
            continue
        if isinstance(amount, str):
            stripped = amount.strip()
            if stripped and stripped.lstrip("-").isdigit():
                total += abs(int(stripped))
    return total


def _looks_like_currency(value: str) -> bool:
    stripped = value.strip()
    return len(stripped) == 3 and stripped.isalpha() and stripped.upper() == stripped


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _coerce_discount_payload(raw_row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(raw_row)
    payload["type"] = str(payload.get("type") or "unknown")
    payload["label"] = str(payload.get("label") or payload["type"] or "discount")
    payload["scope"] = (
        "transaction"
        if str(payload.get("scope") or "item") in {"basket", "transaction"}
        else "item"
    )
    amount_cents = payload.get("amount_cents", 0)
    payload["amount_cents"] = abs(_coerce_int(amount_cents))
    if payload.get("line_no") is not None:
        payload["line_no"] = _coerce_int(payload["line_no"])
    if payload.get("promotion_id") is not None:
        payload["promotion_id"] = str(payload["promotion_id"])
    if payload.get("subkind") is not None:
        payload["subkind"] = str(payload["subkind"])
    if payload.get("funded_by") is not None:
        payload["funded_by"] = str(payload["funded_by"])
    return payload


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lstrip("-").isdigit():
            return int(stripped)
    return 0
