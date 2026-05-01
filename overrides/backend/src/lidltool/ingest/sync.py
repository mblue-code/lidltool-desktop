from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.amazon.profiles import is_amazon_source_id
from lidltool.amazon.recalc import run_scoped_amazon_financial_recalc_if_needed
from lidltool.analytics.categorization import load_compiled_rules
from lidltool.analytics.item_categorizer import (
    CategorizationRequest,
    categorize_transaction_items,
    resolve_item_categorizer_runtime_client,
)
from lidltool.analytics.normalization import (
    NormalizationBundle,
    load_normalization_bundle,
    normalize_merchant_name,
)
from lidltool.analytics.observations import rebuild_item_observations
from lidltool.analytics.product_matcher import auto_match_unmatched_items, resolve_product_for_item
from lidltool.auth.users import SERVICE_USER_ID, ensure_service_user
from lidltool.config import AppConfig
from lidltool.connectors.base import Connector
from lidltool.connectors.lidl_adapter import LidlConnectorAdapter
from lidltool.connectors.registry import source_display_name
from lidltool.connectors.runtime.host import RuntimeHostedReceiptConnector
from lidltool.db.engine import session_scope
from lidltool.db.models import (
    DiscountEvent,
    Receipt,
    ReceiptItem,
    Source,
    SourceAccount,
    Store,
    SyncState,
    Transaction,
    TransactionItem,
)
from lidltool.ingest.dedupe import (
    build_discount_event_key,
    canonical_discount_event_exists,
    canonical_transaction_for_fingerprint,
    canonical_transaction_for_source,
    fingerprint_exists,
    receipt_exists,
)
from lidltool.ingest.json_payloads import make_json_safe
from lidltool.ingest.normalizer import normalize_receipt, parse_datetime, to_decimal
from lidltool.ingest.quarantine import quarantine_connector_payload
from lidltool.ingest.validation import validate_normalized_connector_payload
from lidltool.ingest.validation_results import ValidationOutcome, ValidationReport, ValidationSeverity
from lidltool.lidl.client import LidlClient

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SyncProgress:
    stage: str = "initializing"
    pages: int = 0
    pages_total: int | None = None
    discovered_receipts: int = 0
    receipts_seen: int = 0
    new_receipts: int = 0
    new_items: int = 0
    skipped_existing: int = 0
    current_record_ref: str | None = None


@dataclass(slots=True)
class SyncResult:
    ok: bool
    full: bool
    pages: int
    receipts_seen: int
    new_receipts: int
    new_items: int
    skipped_existing: int
    cutoff_hit: bool
    warnings: list[str] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class SyncService:
    def __init__(
        self,
        client: LidlClient | None,
        session_factory: sessionmaker[Session],
        config: AppConfig,
        connector: Connector | None = None,
        ingestion_job_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._config = config
        self._ingestion_job_id = ingestion_job_id
        self._owner_user_id = owner_user_id.strip() if owner_user_id else None
        if connector is not None:
            self._connector = connector
        else:
            if client is None:
                raise ValueError("client is required when connector is not provided")
            self._connector = LidlConnectorAdapter(client=client, page_size=config.page_size)
        self._item_categorizer_model_client = resolve_item_categorizer_runtime_client(config)

    def sync(
        self,
        *,
        full: bool,
        progress_cb: Callable[[SyncProgress], None] | None = None,
    ) -> SyncResult:
        state_warnings: list[str] = []
        progress = SyncProgress()
        cutoff_hit = False

        with session_scope(self._session_factory) as session:
            validation_outcomes: Counter[str] = Counter()
            validation_issue_codes: Counter[str] = Counter()
            blocked_outputs: list[dict[str, Any]] = []
            metadata: dict[str, Any] = {}
            rules = load_compiled_rules(session)
            normalization_bundle = load_normalization_bundle(session, source=self._config.source)
            sync_state = session.get(SyncState, self._config.source)
            if sync_state is None:
                sync_state = SyncState(source=self._config.source)
                session.add(sync_state)
                session.flush()

            newest_seen_at: datetime | None = sync_state.last_seen_receipt_at
            if newest_seen_at is not None and newest_seen_at.tzinfo is None:
                newest_seen_at = newest_seen_at.replace(tzinfo=UTC)
            newest_seen_id: str | None = sync_state.last_seen_receipt_id

            ingested_streak = 0
            max_pages = self._config.full_sync_max_pages if full else None
            cutoff = None
            if self._config.receipt_cutoff_days is not None:
                cutoff = datetime.now(tz=UTC) - timedelta(days=self._config.receipt_cutoff_days)

            source, source_account = _ensure_source_account(
                session,
                source_id=self._config.source,
                owner_user_id=self._owner_user_id,
            )
            session.commit()
            _emit_sync_progress(progress_cb, progress, stage="authenticating")
            self._connector.authenticate()
            _emit_sync_progress(progress_cb, progress, stage="refreshing_auth")
            self._connector.refresh_auth()
            _emit_sync_progress(progress_cb, progress, stage="healthcheck")
            health = self._connector.healthcheck()
            if not health.get("healthy", False):
                raise RuntimeError(str(health.get("error", "connector healthcheck failed")))
            _emit_sync_progress(progress_cb, progress, stage="discovering")
            discover_with_progress = getattr(self._connector, "discover_new_records_with_progress", None)
            if callable(discover_with_progress):
                record_refs = discover_with_progress(
                    progress_cb=lambda page_count, receipt_count: _emit_sync_progress(
                        progress_cb,
                        progress,
                        stage="discovering",
                        pages=page_count,
                        discovered_receipts=receipt_count,
                    )
                )
            else:
                record_refs = self._connector.discover_new_records()
                _emit_sync_progress(
                    progress_cb,
                    progress,
                    stage="discovering",
                    discovered_receipts=len(record_refs),
                )
            if max_pages is not None:
                max_records = max_pages * max(self._config.page_size, 1)
                record_refs = record_refs[:max_records]
                progress.pages_total = min(
                    max_pages,
                    max(
                        1, (len(record_refs) + self._config.page_size - 1) // self._config.page_size
                    ),
                )
            else:
                progress.pages_total = max(
                    1, (len(record_refs) + self._config.page_size - 1) // self._config.page_size
                )
            progress.discovered_receipts = len(record_refs)
            if progress.pages == 0:
                progress.pages = progress.pages_total or 0
            _emit_sync_progress(progress_cb, progress, stage="processing")

            for receipt_id in record_refs:
                progress.receipts_seen += 1
                progress.current_record_ref = receipt_id
                if not receipt_id:
                    state_warnings.append("Encountered empty receipt reference; skipped")
                    _emit_sync_progress(progress_cb, progress, stage="processing")
                    continue

                if not full and receipt_exists(session, receipt_id):
                    _claim_existing_transaction_if_needed(
                        session,
                        source=source,
                        source_transaction_id=receipt_id,
                    )
                    ingested_streak += 1
                    progress.skipped_existing += 1
                    session.commit()
                    _emit_sync_progress(progress_cb, progress, stage="processing")
                    if ingested_streak >= self._config.already_ingested_streak_threshold:
                        break
                    continue

                detail = self._connector.fetch_record_detail(receipt_id)
                canonical_normalized: dict[str, Any] | None = None
                try:
                    try:
                        normalized = normalize_receipt(detail, category_rules=rules)
                    except Exception as exc:  # noqa: BLE001
                        _quarantine_connector_action_failure(
                            session=session,
                            source=source,
                            source_account=source_account,
                            connector=self._connector,
                            ingestion_job_id=self._ingestion_job_id,
                            source_record_ref=receipt_id,
                            source_record_detail=detail,
                            action_name="normalize_receipt",
                            error=exc,
                            report_code="normalize_receipt_failed",
                            report_message="receipt normalization failed; payload quarantined",
                            state_warnings=state_warnings,
                            blocked_outputs=blocked_outputs,
                        )
                        validation_outcomes[ValidationOutcome.QUARANTINE.value] += 1
                        validation_issue_codes["normalize_receipt_failed"] += 1
                        _emit_sync_progress(progress_cb, progress, stage="processing")
                        continue
                    try:
                        canonical_normalized = self._connector.normalize(detail)
                    except Exception as exc:  # noqa: BLE001
                        _quarantine_connector_action_failure(
                            session=session,
                            source=source,
                            source_account=source_account,
                            connector=self._connector,
                            ingestion_job_id=self._ingestion_job_id,
                            source_record_ref=receipt_id,
                            source_record_detail=detail,
                            action_name="normalize_record",
                            error=exc,
                            report_code="normalize_record_failed",
                            report_message="connector normalize_record failed; payload quarantined",
                            state_warnings=state_warnings,
                            blocked_outputs=blocked_outputs,
                        )
                        validation_outcomes[ValidationOutcome.QUARANTINE.value] += 1
                        validation_issue_codes["normalize_record_failed"] += 1
                        _emit_sync_progress(progress_cb, progress, stage="processing")
                        continue
                    try:
                        discounts = self._connector.extract_discounts(detail)
                    except Exception as exc:  # noqa: BLE001
                        _quarantine_connector_action_failure(
                            session=session,
                            source=source,
                            source_account=source_account,
                            connector=self._connector,
                            ingestion_job_id=self._ingestion_job_id,
                            source_record_ref=receipt_id,
                            source_record_detail=detail,
                            action_name="extract_discounts",
                            connector_normalized=canonical_normalized,
                            error=exc,
                            report_code="extract_discounts_failed",
                            report_message="connector extract_discounts failed; payload quarantined",
                            state_warnings=state_warnings,
                            blocked_outputs=blocked_outputs,
                        )
                        validation_outcomes[ValidationOutcome.QUARANTINE.value] += 1
                        validation_issue_codes["extract_discounts_failed"] += 1
                        _emit_sync_progress(progress_cb, progress, stage="processing")
                        continue
                    validation_report = validate_normalized_connector_payload(
                        source_record_ref=receipt_id,
                        source_record_detail=detail,
                        connector_normalized=canonical_normalized,
                        extracted_discounts=discounts,
                    )
                    validation_outcomes[validation_report.outcome.value] += 1
                    for issue in validation_report.issues:
                        validation_issue_codes[issue.code] += 1

                    if validation_report.outcome in {
                        ValidationOutcome.QUARANTINE,
                        ValidationOutcome.REJECT,
                    }:
                        quarantine_row = quarantine_connector_payload(
                            session,
                            source_id=source.id,
                            source_account=source_account,
                            ingestion_job_id=self._ingestion_job_id,
                            connector=self._connector,
                            action_name="canonical_write_gate",
                            outcome=validation_report.outcome,
                            source_record_ref=receipt_id,
                            source_record_detail=detail,
                            connector_normalized=canonical_normalized,
                            extracted_discounts=discounts,
                            report=validation_report,
                        )
                        blocked_outputs.append(
                            {
                                "source_record_ref": receipt_id,
                                "outcome": validation_report.outcome.value,
                                "quarantine_id": quarantine_row.id,
                                "issue_codes": [issue.code for issue in validation_report.issues],
                            }
                        )
                        state_warnings.append(
                            _validation_summary_message(
                                record_ref=receipt_id,
                                outcome=validation_report.outcome,
                                issue_count=len(validation_report.issues),
                            )
                        )
                        LOGGER.warning(
                            "ingest.validation.blocked source=%s record_ref=%s outcome=%s quarantine_id=%s",
                            source.id,
                            receipt_id,
                            validation_report.outcome.value,
                            quarantine_row.id,
                        )
                        session.commit()
                        _emit_sync_progress(progress_cb, progress, stage="processing")
                        continue

                    if validation_report.outcome is ValidationOutcome.WARN:
                        state_warnings.append(
                            _validation_summary_message(
                                record_ref=receipt_id,
                                outcome=validation_report.outcome,
                                issue_count=len(validation_report.issues),
                            )
                        )
                        LOGGER.warning(
                            "ingest.validation.warn source=%s record_ref=%s issues=%s",
                            source.id,
                            receipt_id,
                            len(validation_report.issues),
                        )

                    _upsert_canonical_transaction(
                        session=session,
                        source=source,
                        source_account=source_account,
                        source_record_ref=receipt_id,
                        source_record_detail=detail,
                        connector_normalized=canonical_normalized,
                        fallback_normalized=normalized,
                        extracted_discounts=discounts,
                        normalization_bundle=normalization_bundle,
                        compiled_rules=rules,
                        use_model=self._item_categorizer_model_client is not None,
                        model_client=self._item_categorizer_model_client,
                        model_batch_size=int(
                            getattr(self._config, "item_categorizer_max_batch_size", 8) or 8
                        ),
                        model_confidence_threshold=float(
                            getattr(
                                self._config,
                                "item_categorizer_confidence_threshold",
                                getattr(
                                    self._config,
                                    "item_categorizer_low_confidence_threshold",
                                    0.65,
                                ),
                            )
                            or 0.65
                        ),
                    )

                    if receipt_exists(session, normalized.id):
                        ingested_streak += 1
                        progress.skipped_existing += 1
                        session.commit()
                        _emit_sync_progress(progress_cb, progress, stage="processing")
                        if (
                            not full
                            and ingested_streak >= self._config.already_ingested_streak_threshold
                        ):
                            break
                        continue

                    dedupe_by_source_transaction_id = bool(
                        getattr(self._connector, "dedupe_by_source_transaction_id", False)
                    )
                    if (
                        not dedupe_by_source_transaction_id
                        and fingerprint_exists(session, normalized.fingerprint)
                    ):
                        ingested_streak += 1
                        progress.skipped_existing += 1
                        session.commit()
                        _emit_sync_progress(progress_cb, progress, stage="processing")
                        continue

                    ingested_streak = 0
                    _upsert_store(
                        session,
                        normalized.store_id,
                        normalized.store_name,
                        normalized.store_address,
                    )
                    receipt_row = Receipt(
                        id=normalized.id,
                        purchased_at=normalized.purchased_at,
                        store_id=normalized.store_id,
                        store_name=normalized.store_name,
                        store_address=normalized.store_address,
                        total_gross=normalized.total_gross,
                        currency=normalized.currency,
                        discount_total=normalized.discount_total,
                        fingerprint=normalized.fingerprint,
                        raw_json=normalized.raw_json,
                    )
                    session.add(receipt_row)
                    session.flush()

                    for item in normalized.items:
                        session.add(
                            ReceiptItem(
                                receipt_id=normalized.id,
                                line_no=item.line_no,
                                name=item.name,
                                qty=item.qty,
                                unit=item.unit,
                                unit_price=item.unit_price,
                                line_total=item.line_total,
                                vat_rate=item.vat_rate,
                                category=item.category,
                                discounts=item.discounts,
                            )
                        )

                    progress.new_receipts += 1
                    progress.new_items += len(normalized.items)
                    if newest_seen_at is None or normalized.purchased_at > newest_seen_at:
                        newest_seen_at = normalized.purchased_at
                        newest_seen_id = normalized.id

                    if cutoff and normalized.purchased_at < cutoff:
                        session.commit()
                        _emit_sync_progress(progress_cb, progress, stage="processing")
                        cutoff_hit = True
                        break

                    session.commit()
                    _emit_sync_progress(progress_cb, progress, stage="processing")
                except Exception as exc:  # noqa: BLE001
                    session.rollback()
                    _quarantine_connector_action_failure(
                        session=session,
                        source=source,
                        source_account=source_account,
                        connector=self._connector,
                        ingestion_job_id=self._ingestion_job_id,
                        source_record_ref=receipt_id,
                        source_record_detail=detail,
                        action_name="process_record",
                        connector_normalized=canonical_normalized,
                        error=exc,
                        report_code="process_record_failed",
                        report_message="record processing failed unexpectedly; payload quarantined",
                        state_warnings=state_warnings,
                        blocked_outputs=blocked_outputs,
                    )
                    validation_outcomes[ValidationOutcome.QUARANTINE.value] += 1
                    validation_issue_codes["process_record_failed"] += 1
                    _emit_sync_progress(progress_cb, progress, stage="processing")
                    continue

            _emit_sync_progress(progress_cb, progress, stage="finalizing")
            sync_state.last_success_at = datetime.now(tz=UTC)
            sync_state.last_seen_receipt_at = newest_seen_at
            sync_state.last_seen_receipt_id = newest_seen_id

            if is_amazon_source_id(source.id):
                try:
                    amazon_recalc = run_scoped_amazon_financial_recalc_if_needed(
                        session,
                        source_id=source.id,
                        user_id=source.user_id,
                        shared_group_id=source.shared_group_id,
                    )
                    metadata["amazon_financial_recalc"] = amazon_recalc
                    LOGGER.info(
                        "amazon.financial_recalc.completed source=%s user_id=%s scanned=%s updated=%s skipped=%s version=%s",
                        source.id,
                        source.user_id,
                        amazon_recalc.get("scanned"),
                        amazon_recalc.get("updated"),
                        amazon_recalc.get("skipped"),
                        amazon_recalc.get("version"),
                    )
                except Exception as exc:  # noqa: BLE001
                    metadata["amazon_financial_recalc"] = {
                        "error": str(exc),
                    }
                    LOGGER.warning(
                        "amazon.financial_recalc.failed source=%s user_id=%s error=%s",
                        source.id,
                        source.user_id,
                        exc,
                    )

            try:
                matched_count = auto_match_unmatched_items(session)
                rebuilt_rows = rebuild_item_observations(session)
                LOGGER.info(
                    "analytics.rebuild.completed matched=%s rebuilt_rows=%s",
                    matched_count,
                    rebuilt_rows,
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("analytics.rebuild.failed error=%s", exc)
                state_warnings.append(f"analytics rebuild failed: {exc}")

        return SyncResult(
            ok=True,
            full=full,
            pages=progress.pages,
            receipts_seen=progress.receipts_seen,
            new_receipts=progress.new_receipts,
            new_items=progress.new_items,
            skipped_existing=progress.skipped_existing,
            cutoff_hit=cutoff_hit,
            warnings=state_warnings,
            validation=_validation_summary(
                connector=self._connector,
                validation_outcomes=validation_outcomes,
                validation_issue_codes=validation_issue_codes,
                blocked_outputs=blocked_outputs,
            ),
            metadata=metadata,
        )


def _emit_sync_progress(
    progress_cb: Callable[[SyncProgress], None] | None,
    progress: SyncProgress,
    *,
    stage: str | None = None,
    pages: int | None = None,
    pages_total: int | None = None,
    discovered_receipts: int | None = None,
) -> None:
    if stage is not None:
        progress.stage = stage
    if pages is not None:
        progress.pages = pages
    if pages_total is not None:
        progress.pages_total = pages_total
    if discovered_receipts is not None:
        progress.discovered_receipts = discovered_receipts
    if progress_cb is not None:
        progress_cb(progress)


def _quarantine_connector_action_failure(
    *,
    session: Session,
    source: Source,
    source_account: SourceAccount | None,
    connector: Connector,
    ingestion_job_id: str | None,
    source_record_ref: str,
    source_record_detail: dict[str, Any],
    action_name: str,
    error: Exception,
    report_code: str,
    report_message: str,
    state_warnings: list[str],
    blocked_outputs: list[dict[str, Any]],
    connector_normalized: dict[str, Any] | None = None,
) -> None:
    report = ValidationReport()
    report.add_issue(
        code=report_code,
        severity=ValidationSeverity.QUARANTINE,
        message=report_message,
        path="$.normalized_record",
        details={"error": str(error), "action_name": action_name},
    )
    quarantine_row = quarantine_connector_payload(
        session,
        source_id=source.id,
        source_account=source_account,
        ingestion_job_id=ingestion_job_id,
        connector=connector,
        action_name=action_name,
        outcome=ValidationOutcome.QUARANTINE,
        source_record_ref=source_record_ref,
        source_record_detail=source_record_detail,
        connector_normalized=connector_normalized or {},
        extracted_discounts=[],
        report=report,
    )
    blocked_outputs.append(
        {
            "source_record_ref": source_record_ref,
            "outcome": ValidationOutcome.QUARANTINE.value,
            "quarantine_id": quarantine_row.id,
            "issue_codes": [report_code],
        }
    )
    state_warnings.append(
        _validation_summary_message(
            record_ref=source_record_ref,
            outcome=ValidationOutcome.QUARANTINE,
            issue_count=len(report.issues),
        )
    )
    LOGGER.warning(
        "ingest.validation.connector_action_failed source=%s record_ref=%s action=%s quarantine_id=%s error=%s",
        source.id,
        source_record_ref,
        action_name,
        quarantine_row.id,
        error,
    )
    session.commit()


def _extract_receipt_id(summary: dict[str, object]) -> str | None:
    for key in ["id", "receiptId", "ticketId", "uuid"]:
        value = summary.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _extract_summary_timestamp(summary: dict[str, object]) -> datetime | None:
    for key in ["purchasedAt", "createdAt", "date", "timestamp"]:
        value = summary.get(key)
        if value is not None:
            return parse_datetime(value)
    return None


def _upsert_store(
    session: Session, store_id: str | None, name: str | None, address: str | None
) -> None:
    if not store_id:
        return
    existing = session.get(Store, store_id)
    if existing is None:
        session.add(Store(id=store_id, name=name, address=address))
        return
    if name and existing.name != name:
        existing.name = name
    if address and existing.address != address:
        existing.address = address


def _ensure_source_account(
    session: Session,
    *,
    source_id: str,
    config: AppConfig | None = None,
    owner_user_id: str | None = None,
) -> tuple[Source, SourceAccount]:
    service_user = ensure_service_user(session)
    source = session.get(Source, source_id)
    if source is None:
        source = Source(
            id=source_id,
            user_id=owner_user_id or service_user.user_id,
            kind="connector",
            display_name=source_display_name(source_id, config=config),
            status="healthy",
            enabled=True,
        )
        session.add(source)
        session.flush()
    elif source.user_id is None:
        source.user_id = owner_user_id or service_user.user_id
    elif owner_user_id and source.user_id == service_user.user_id:
        source.user_id = owner_user_id
    account = session.execute(
        select(SourceAccount).where(SourceAccount.source_id == source.id).limit(1)
    ).scalar_one_or_none()
    if account is None:
        account = SourceAccount(source_id=source.id, account_ref="default", status="connected")
        session.add(account)
        session.flush()
    return source, account


def _claim_existing_transaction_if_needed(
    session: Session,
    *,
    source: Source,
    source_transaction_id: str,
) -> None:
    existing = canonical_transaction_for_source(
        session,
        source_id=source.id,
        source_transaction_id=source_transaction_id,
    )
    if existing is not None and existing.user_id in {None, SERVICE_USER_ID}:
        existing.user_id = source.user_id


def _validation_summary_message(
    *,
    record_ref: str,
    outcome: ValidationOutcome,
    issue_count: int,
) -> str:
    return (
        f"connector validation {outcome.value} for record {record_ref}; "
        f"{issue_count} issue(s) recorded"
    )


def _validation_summary(
    *,
    connector: Connector,
    validation_outcomes: Counter[str],
    validation_issue_codes: Counter[str],
    blocked_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    outcomes = {
        ValidationOutcome.ACCEPT.value: int(validation_outcomes.get(ValidationOutcome.ACCEPT.value, 0)),
        ValidationOutcome.WARN.value: int(validation_outcomes.get(ValidationOutcome.WARN.value, 0)),
        ValidationOutcome.QUARANTINE.value: int(
            validation_outcomes.get(ValidationOutcome.QUARANTINE.value, 0)
        ),
        ValidationOutcome.REJECT.value: int(validation_outcomes.get(ValidationOutcome.REJECT.value, 0)),
    }
    records_validated = sum(outcomes.values())
    summary: dict[str, Any] = {
        "records_validated": records_validated,
        "outcomes": outcomes,
        "issue_codes": dict(validation_issue_codes),
        "blocked_outputs": blocked_outputs[:20],
        "quality_signal": (
            "degraded"
            if outcomes[ValidationOutcome.QUARANTINE.value] or outcomes[ValidationOutcome.REJECT.value]
            else "warning"
            if outcomes[ValidationOutcome.WARN.value]
            else "healthy"
        ),
    }
    if records_validated > 0:
        summary["warn_rate"] = round(outcomes[ValidationOutcome.WARN.value] / records_validated, 3)
        summary["blocked_rate"] = round(
            (
                outcomes[ValidationOutcome.QUARANTINE.value]
                + outcomes[ValidationOutcome.REJECT.value]
            )
            / records_validated,
            3,
        )
    if isinstance(connector, RuntimeHostedReceiptConnector):
        summary["connector"] = connector.runtime_identity()
    return summary


def _upsert_canonical_transaction(
    *,
    session: Session,
    source: Source,
    source_account: SourceAccount | None,
    source_record_ref: str,
    source_record_detail: dict[str, Any],
    connector_normalized: dict[str, Any],
    fallback_normalized: Any,
    extracted_discounts: list[dict[str, Any]],
    normalization_bundle: NormalizationBundle,
    compiled_rules: list[Any],
    use_model: bool,
    model_client: Any,
    model_batch_size: int,
    model_confidence_threshold: float,
) -> None:
    source_transaction_id = str(connector_normalized.get("id") or fallback_normalized.id).strip()
    fingerprint = str(
        connector_normalized.get("fingerprint") or fallback_normalized.fingerprint or ""
    ).strip()
    purchased_at_raw = connector_normalized.get("purchased_at")
    purchased_at = parse_datetime(
        purchased_at_raw if purchased_at_raw is not None else fallback_normalized.purchased_at
    )
    merchant_name_raw = (
        str(connector_normalized.get("store_name"))
        if connector_normalized.get("store_name")
        else fallback_normalized.store_name
    )
    merchant_name = normalize_merchant_name(merchant_name_raw, normalization_bundle)
    merchant_name = _source_merchant_display_name(source.id, merchant_name)
    total_gross_cents = int(
        connector_normalized.get("total_gross_cents", fallback_normalized.total_gross)
    )
    currency = str(connector_normalized.get("currency", fallback_normalized.currency) or "EUR")
    discount_total_raw = connector_normalized.get(
        "discount_total_cents", fallback_normalized.discount_total
    )
    discount_total_cents = int(discount_total_raw) if discount_total_raw is not None else None

    existing = canonical_transaction_for_source(
        session,
        source_id=source.id,
        source_transaction_id=source_transaction_id,
    )
    reason = "source_key"
    if existing is None and fingerprint and not source.id.startswith("amazon_"):
        existing = canonical_transaction_for_fingerprint(
            session,
            source_id=source.id,
            fingerprint=fingerprint,
        )
        reason = "fingerprint" if existing is not None else "insert"

    payload: dict[str, object] = {
        "source_record_ref": source_record_ref,
        "source_record_detail": source_record_detail,
        "connector_normalized": connector_normalized,
    }
    payload = make_json_safe(payload)

    if existing is not None:
        if (
            existing.purchased_at is not None
            and str(connector_normalized.get("date_source") or "").strip() == "page_year"
        ):
            purchased_at = existing.purchased_at
        if existing.user_id in {None, SERVICE_USER_ID}:
            existing.user_id = source.user_id
        existing.purchased_at = purchased_at
        existing.merchant_name = merchant_name
        existing.total_gross_cents = total_gross_cents
        existing.currency = currency
        existing.discount_total_cents = discount_total_cents
        existing.fingerprint = fingerprint or existing.fingerprint
        existing.raw_payload = payload
        if source_account is not None:
            existing.source_account_id = source_account.id
        LOGGER.info(
            "ingest.canonical.transaction decision=update reason=%s source=%s source_transaction_id=%s transaction_id=%s",
            reason,
            source.id,
            source_transaction_id,
            existing.id,
        )
        return

    transaction = Transaction(
        source_id=source.id,
        user_id=source.user_id,
        shared_group_id=source.shared_group_id,
        source_account_id=source_account.id if source_account is not None else None,
        source_transaction_id=source_transaction_id,
        purchased_at=purchased_at,
        merchant_name=merchant_name,
        total_gross_cents=total_gross_cents,
        currency=currency,
        discount_total_cents=discount_total_cents,
        fingerprint=fingerprint or None,
        raw_payload=payload,
    )
    session.add(transaction)
    session.flush()
    LOGGER.info(
        "ingest.canonical.transaction decision=insert source=%s source_transaction_id=%s transaction_id=%s",
        source.id,
        source_transaction_id,
        transaction.id,
    )

    line_to_item: dict[int, TransactionItem] = {}
    item_rows: list[TransactionItem] = []
    categorization_requests: list[CategorizationRequest] = []
    connector_items = connector_normalized.get("items")
    items = connector_items if isinstance(connector_items, list) else []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        line_no = int(item.get("line_no", index))
        source_item_id = item.get("source_item_id")
        current_category = str(item.get("category")) if item.get("category") is not None else None
        item_row = TransactionItem(
            transaction_id=transaction.id,
            shared_group_id=transaction.shared_group_id,
            source_item_id=(
                str(source_item_id) if source_item_id else f"{source_transaction_id}:{line_no}"
            ),
            line_no=line_no,
            name=str(item.get("name") or f"item_{line_no}"),
            qty=to_decimal(item.get("qty"), default=to_decimal(1)),
            unit=str(item.get("unit")) if item.get("unit") is not None else None,
            unit_price_cents=(
                int(item["unit_price_cents"]) if item.get("unit_price_cents") is not None else None
            ),
            line_total_cents=int(item.get("line_total_cents", 0)),
            is_deposit=bool(item.get("is_deposit", False)),
            category=current_category,
            raw_payload=item,
        )
        match = resolve_product_for_item(session, item=item_row, source=source)
        if match is not None:
            item_row.product_id = match.product_id
        item_rows.append(item_row)
        categorization_requests.append(
            CategorizationRequest(
                item_name=item_row.name,
                current_category=current_category,
                product_id=item_row.product_id,
                raw_payload=item,
                merchant_name=merchant_name,
                source_item_id=item_row.source_item_id,
                unit=item_row.unit,
                unit_price_cents=item_row.unit_price_cents,
                line_total_cents=item_row.line_total_cents,
            )
        )

    categorization_results = categorize_transaction_items(
        session=session,
        source=source,
        requests=categorization_requests,
        normalization_bundle=normalization_bundle,
        use_model=use_model,
        model_client=model_client,
        compiled_rules=compiled_rules,
        model_confidence_threshold=model_confidence_threshold,
        model_batch_size=model_batch_size,
    )

    for item_row, categorization_result in zip(item_rows, categorization_results, strict=True):
        item_row.category = categorization_result.category_name
        item_row.category_id = categorization_result.category_id
        item_row.category_method = categorization_result.method
        item_row.category_confidence = _to_category_decimal(categorization_result.confidence)
        item_row.category_source_value = categorization_result.source_value
        item_row.category_version = categorization_result.version
        session.add(item_row)
        session.flush()
        line_to_item[item_row.line_no] = item_row

    for discount in extracted_discounts:
        if not isinstance(discount, dict):
            continue
        line_no_raw = discount.get("line_no")
        discount_line_no = int(line_no_raw) if isinstance(line_no_raw, int) else None
        discount_item_row = (
            line_to_item.get(discount_line_no) if discount_line_no is not None else None
        )
        scope = str(
            discount.get("scope") or ("item" if discount_item_row is not None else "transaction")
        )
        raw_amount = int(discount.get("amount_cents", 0))
        amount_cents = abs(raw_amount)
        if amount_cents == 0:
            continue
        source_discount_code = (
            str(discount["promotion_id"]) if discount.get("promotion_id") is not None else None
        )
        source_label = str(discount.get("label") or discount.get("type") or "discount")
        dedupe_key = build_discount_event_key(
            source_id=source.id,
            source_transaction_id=source_transaction_id,
            source_discount_code=source_discount_code,
            source_label=source_label,
            amount_cents=amount_cents,
            scope=scope,
            source_item_ref=(
                discount_item_row.source_item_id if discount_item_row is not None else None
            ),
        )
        if canonical_discount_event_exists(
            session,
            transaction_id=transaction.id,
            transaction_item_id=discount_item_row.id if discount_item_row is not None else None,
            source=source.id,
            source_discount_code=source_discount_code,
            source_label=source_label,
            scope=scope,
            amount_cents=amount_cents,
        ):
            LOGGER.info(
                "ingest.canonical.discount decision=skip reason=duplicate source=%s transaction_id=%s event_key=%s",
                source.id,
                transaction.id,
                dedupe_key,
            )
            continue

        discount_type = str(discount.get("type") or "unknown").lower()
        event = DiscountEvent(
            transaction_id=transaction.id,
            transaction_item_id=discount_item_row.id if discount_item_row is not None else None,
            source=source.id,
            source_discount_code=source_discount_code,
            source_label=source_label,
            scope=scope,
            amount_cents=amount_cents,
            currency=currency,
            kind=discount_type,
            subkind=str(discount.get("subkind")) if discount.get("subkind") is not None else None,
            funded_by=str(discount.get("funded_by") or "retailer"),
            is_loyalty_program="loyal" in discount_type or "coupon" in discount_type,
            raw_payload={"event_key": dedupe_key, "source_discount": discount},
        )
        session.add(event)
        LOGGER.info(
            "ingest.canonical.discount decision=insert source=%s transaction_id=%s event_key=%s",
            source.id,
            transaction.id,
            dedupe_key,
        )


def _source_merchant_display_name(source_id: str, merchant_name: str | None) -> str | None:
    value = (merchant_name or "").strip()
    if source_id.startswith("lidl_plus") and value and not value.lower().startswith("lidl"):
        return f"Lidl {value}"
    return value or merchant_name


def _to_category_decimal(value: float | None) -> Any:
    if value is None:
        return None
    return to_decimal(f"{value:.3f}")
