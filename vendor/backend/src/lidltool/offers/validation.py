from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError

from lidltool.connectors.sdk.offer import NormalizedOfferItem, NormalizedOfferRecord
from lidltool.ingest.validation_results import ValidationReport, ValidationSeverity

_MIN_PLAUSIBLE_VALIDITY = datetime(2000, 1, 1, tzinfo=UTC)
_MAX_FUTURE_VALIDITY_START = timedelta(days=366)
_MAX_REASONABLE_PRICE_CENTS = 10_000_000


def validate_normalized_offer_payload(
    *,
    source_offer_ref: str,
    source_offer_detail: Mapping[str, Any],
    connector_normalized: Mapping[str, Any],
    now: datetime | None = None,
) -> ValidationReport:
    report = ValidationReport()
    inspected_at = _as_utc(now or datetime.now(tz=UTC))
    report.inspected_at = inspected_at

    normalized_offer = _validate_offer_shape(report=report, connector_normalized=connector_normalized)
    if normalized_offer is None:
        return report

    _validate_provenance(
        report=report,
        source_offer_ref=source_offer_ref,
        source_offer_detail=source_offer_detail,
        normalized_offer=normalized_offer,
    )
    _validate_offer_fields(report=report, normalized_offer=normalized_offer, inspected_at=inspected_at)
    _validate_offer_items(report=report, normalized_offer=normalized_offer)
    return report


def _validate_offer_shape(
    *,
    report: ValidationReport,
    connector_normalized: Mapping[str, Any],
) -> NormalizedOfferRecord | None:
    try:
        return NormalizedOfferRecord.model_validate(dict(connector_normalized))
    except ValidationError as exc:
        report.add_issue(
            code="normalized_offer_shape_invalid",
            severity=ValidationSeverity.REJECT,
            message="connector normalized offer payload failed schema validation",
            path="$.normalized_offer",
            details={"errors": exc.errors(include_url=False)},
        )
        return None


def _validate_provenance(
    *,
    report: ValidationReport,
    source_offer_ref: str,
    source_offer_detail: Mapping[str, Any],
    normalized_offer: NormalizedOfferRecord,
) -> None:
    if not source_offer_ref.strip():
        report.add_issue(
            code="missing_source_offer_ref",
            severity=ValidationSeverity.REJECT,
            message="source offer reference is required for canonical provenance",
            path="$.source_offer_ref",
        )
    if not dict(source_offer_detail):
        report.add_issue(
            code="missing_source_offer_detail",
            severity=ValidationSeverity.REJECT,
            message="source offer detail snapshot is required for canonical provenance",
            path="$.source_offer_detail",
        )
    if not normalized_offer.raw_payload:
        report.add_issue(
            code="missing_raw_payload",
            severity=ValidationSeverity.REJECT,
            message="normalized offer payload must include a raw_payload provenance snapshot",
            path="$.normalized_offer.raw_payload",
        )


def _validate_offer_fields(
    *,
    report: ValidationReport,
    normalized_offer: NormalizedOfferRecord,
    inspected_at: datetime,
) -> None:
    if not normalized_offer.source_offer_id.strip():
        report.add_issue(
            code="missing_source_offer_id",
            severity=ValidationSeverity.REJECT,
            message="normalized offer payload is missing a source_offer_id",
            path="$.normalized_offer.source_offer_id",
        )
    if not normalized_offer.fingerprint.strip():
        report.add_issue(
            code="missing_fingerprint",
            severity=ValidationSeverity.REJECT,
            message="normalized offer payload is missing a fingerprint",
            path="$.normalized_offer.fingerprint",
        )
    if normalized_offer.validity_start < _MIN_PLAUSIBLE_VALIDITY:
        report.add_issue(
            code="validity_start_implausibly_old",
            severity=ValidationSeverity.QUARANTINE,
            message="validity_start is implausibly old and requires review",
            path="$.normalized_offer.validity_start",
            details={"validity_start": normalized_offer.validity_start.isoformat()},
        )
    if normalized_offer.validity_start > inspected_at + _MAX_FUTURE_VALIDITY_START:
        report.add_issue(
            code="validity_start_implausibly_far_future",
            severity=ValidationSeverity.QUARANTINE,
            message="validity_start is implausibly far in the future",
            path="$.normalized_offer.validity_start",
            details={"validity_start": normalized_offer.validity_start.isoformat()},
        )
    if normalized_offer.validity_end < normalized_offer.validity_start:
        report.add_issue(
            code="invalid_validity_window",
            severity=ValidationSeverity.REJECT,
            message="validity_end must be greater than or equal to validity_start",
            path="$.normalized_offer.validity_end",
        )
    if normalized_offer.price_cents is not None and normalized_offer.price_cents > _MAX_REASONABLE_PRICE_CENTS:
        report.add_issue(
            code="offer_price_implausibly_large",
            severity=ValidationSeverity.QUARANTINE,
            message="price_cents is implausibly large and requires review",
            path="$.normalized_offer.price_cents",
            details={"price_cents": normalized_offer.price_cents},
        )
    if (
        normalized_offer.original_price_cents is not None
        and normalized_offer.original_price_cents > _MAX_REASONABLE_PRICE_CENTS
    ):
        report.add_issue(
            code="offer_original_price_implausibly_large",
            severity=ValidationSeverity.QUARANTINE,
            message="original_price_cents is implausibly large and requires review",
            path="$.normalized_offer.original_price_cents",
            details={"original_price_cents": normalized_offer.original_price_cents},
        )
    if (
        normalized_offer.price_cents is not None
        and normalized_offer.original_price_cents is not None
        and normalized_offer.price_cents > normalized_offer.original_price_cents
    ):
        report.add_issue(
            code="offer_price_exceeds_original",
            severity=ValidationSeverity.REJECT,
            message="price_cents must not exceed original_price_cents",
            path="$.normalized_offer.price_cents",
        )
    if normalized_offer.discount_percent is not None and normalized_offer.discount_percent == 0:
        report.add_issue(
            code="zero_discount_percent",
            severity=ValidationSeverity.WARN,
            message="discount_percent is zero; ingesting with warning",
            path="$.normalized_offer.discount_percent",
        )


def _validate_offer_items(
    *,
    report: ValidationReport,
    normalized_offer: NormalizedOfferRecord,
) -> None:
    seen_lines: set[int] = set()
    for item in normalized_offer.items:
        _validate_offer_item(report=report, item=item, seen_lines=seen_lines)


def _validate_offer_item(
    *,
    report: ValidationReport,
    item: NormalizedOfferItem,
    seen_lines: set[int],
) -> None:
    path = f"$.normalized_offer.items[{item.line_no}]"
    if item.line_no in seen_lines:
        report.add_issue(
            code="duplicate_offer_item_line_no",
            severity=ValidationSeverity.REJECT,
            message="offer item line numbers must be unique",
            path=f"{path}.line_no",
        )
    seen_lines.add(item.line_no)
    if not item.title.strip():
        report.add_issue(
            code="missing_offer_item_title",
            severity=ValidationSeverity.REJECT,
            message="offer item title is required",
            path=f"{path}.title",
        )
    if (
        item.price_cents is not None
        and item.original_price_cents is not None
        and item.price_cents > item.original_price_cents
    ):
        report.add_issue(
            code="offer_item_price_exceeds_original",
            severity=ValidationSeverity.REJECT,
            message="offer item price_cents must not exceed original_price_cents",
            path=f"{path}.price_cents",
        )
    if item.price_cents is not None and item.price_cents > _MAX_REASONABLE_PRICE_CENTS:
        report.add_issue(
            code="offer_item_price_implausibly_large",
            severity=ValidationSeverity.QUARANTINE,
            message="offer item price_cents is implausibly large and requires review",
            path=f"{path}.price_cents",
            details={"price_cents": item.price_cents},
        )
    if (
        not item.canonical_product_id
        and not item.gtin_ean
        and not item.alias_candidates
        and not item.title.strip()
    ):
        report.add_issue(
            code="missing_offer_item_product_hints",
            severity=ValidationSeverity.REJECT,
            message="offer item must include at least one product hint",
            path=path,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
