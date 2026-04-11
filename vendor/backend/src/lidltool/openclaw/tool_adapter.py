from __future__ import annotations

import json
import logging
import math
import sys
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.analytics.queries import (
    dashboard_retailer_composition,
    dashboard_savings_breakdown,
    dashboard_totals,
    dashboard_trends,
    export_receipts,
    month_stats,
    savings_breakdown,
    search_transactions,
)
from lidltool.auth.token_store import TokenStore
from lidltool.config import AppConfig, build_config, database_url
from lidltool.connectors.auth.auth_orchestration import ConnectorAuthOrchestrationService
from lidltool.connectors.connector_catalog import connector_catalog_payload
from lidltool.connectors.management import plugin_management_payload
from lidltool.connectors.market_catalog import self_hosted_market_strategy_payload
from lidltool.connectors.registry import (
    get_connector_registry,
    source_bootstrap_command,
    source_catalog,
    source_display_name,
    source_manifest_payload,
)
from lidltool.connectors.runtime.execution import ConnectorExecutionService
from lidltool.db.audit import record_audit_event
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import IngestionJob, Source, SourceAccount, SyncState
from lidltool.ingest.jobs import JobService
from lidltool.ingest.manual_ingest import (
    AGENT_SOURCE_ID,
    ManualDiscountInput,
    ManualIngestService,
    ManualItemInput,
    ManualTransactionInput,
)
from lidltool.reliability.metrics import compute_endpoint_slo_summary

CONTRACT_VERSION = "v1"
LOGGER = logging.getLogger(__name__)
SOURCE_STATUS_CONNECTED = "connected"
SOURCE_STATUS_EXPIRED_AUTH = "expired_auth"
SOURCE_STATUS_HEALTHY = "healthy"
SOURCE_STATUS_FAILING = "failing"
TERMINAL_FAILURE_STATES = {"failed", "canceled"}
FAILURE_NONE = "none"
FAILURE_AUTH_EXPIRED = "auth_expired"
FAILURE_TRANSIENT_UPSTREAM = "transient_upstream"
FAILURE_CONFIGURATION = "configuration"
FAILURE_CANCELED = "canceled"
FAILURE_UNKNOWN = "unknown"
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_METRICS_LOCK = threading.Lock()
_ACTION_METRICS: dict[str, int] = defaultdict(int)
ACTION_POLICY: dict[str, dict[str, Any]] = {
    "health": {"category": "read", "required_scopes": ("read.core",), "safe_write": False},
    "sync_status": {"category": "read", "required_scopes": ("read.core",), "safe_write": False},
    "sources_list": {"category": "read", "required_scopes": ("read.core",), "safe_write": False},
    "source_status": {"category": "read", "required_scopes": ("read.core",), "safe_write": False},
    "source_auth_status": {
        "category": "read",
        "required_scopes": ("read.core",),
        "safe_write": False,
    },
    "connector_health_dashboard": {
        "category": "read",
        "required_scopes": ("read.core",),
        "safe_write": False,
    },
    "connector_cost_performance_review": {
        "category": "read",
        "required_scopes": ("read.core",),
        "safe_write": False,
    },
    "stats_month": {"category": "read", "required_scopes": ("read.core",), "safe_write": False},
    "savings_breakdown": {
        "category": "read",
        "required_scopes": ("read.core",),
        "safe_write": False,
    },
    "dashboard_cards": {"category": "read", "required_scopes": ("read.core",), "safe_write": False},
    "dashboard_trends": {
        "category": "read",
        "required_scopes": ("read.core",),
        "safe_write": False,
    },
    "dashboard_savings_breakdown": {
        "category": "read",
        "required_scopes": ("read.core",),
        "safe_write": False,
    },
    "dashboard_retailer_composition": {
        "category": "read",
        "required_scopes": ("read.core",),
        "safe_write": False,
    },
    "search_transactions": {
        "category": "read",
        "required_scopes": ("read.core",),
        "safe_write": False,
    },
    "endpoint_reliability_dashboard": {
        "category": "read",
        "required_scopes": ("read.core",),
        "safe_write": False,
    },
    "export": {"category": "read", "required_scopes": ("read.core",), "safe_write": False},
    "sync": {"category": "safe_write", "required_scopes": ("write.sync",), "safe_write": True},
    "manual_ingest": {
        "category": "safe_write",
        "required_scopes": ("write.ingest",),
        "safe_write": True,
    },
    "source_auth_reauth_start": {
        "category": "safe_write",
        "required_scopes": ("write.auth",),
        "safe_write": True,
    },
    "source_auth_reauth_confirm": {
        "category": "safe_write",
        "required_scopes": ("write.auth",),
        "safe_write": True,
    },
}


class ActionValidationError(ValueError):
    """Raised when action parameters are invalid."""


class ActionRuntimeFailureError(RuntimeError):
    """Raised when action execution fails at runtime."""


def _response(
    ok: bool, result: Any = None, warnings: list[str] | None = None, error: str | None = None
) -> dict[str, Any]:
    return {
        "ok": ok,
        "result": result,
        "warnings": [str(item) for item in (warnings or [])],
        "error": error,
    }


def _metric_inc(metric: str) -> None:
    with _METRICS_LOCK:
        _ACTION_METRICS[metric] += 1


def _rate_limit_key(action: str, params: dict[str, Any]) -> str:
    caller_token = params.get("caller_token")
    if isinstance(caller_token, str) and caller_token:
        return f"{action}:{caller_token}"
    return f"{action}:global"


def _check_rate_limit(config: AppConfig, *, action: str, params: dict[str, Any]) -> int | None:
    if not config.openclaw_rate_limit_enabled:
        return None
    requests = max(int(config.openclaw_rate_limit_requests), 1)
    window_s = max(int(config.openclaw_rate_limit_window_s), 1)
    now = time.monotonic()
    key = _rate_limit_key(action=action, params=params)

    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_BUCKETS[key]
        cutoff = now - window_s
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= requests:
            retry_after = int(max(math.ceil(window_s - (now - bucket[0])), 1))
            return retry_after
        bucket.append(now)
    return None


def _apply_auth_guard(config: AppConfig, params: dict[str, Any], action: str) -> list[str]:
    warnings: list[str] = []
    expected_api_key = config.openclaw_api_key
    if not expected_api_key:
        return warnings
    provided_api_key = params.get("api_key")
    if provided_api_key is not None and not isinstance(provided_api_key, str):
        raise ActionValidationError("params.api_key must be a string")
    if provided_api_key == expected_api_key:
        LOGGER.info("openclaw.auth.allowed action=%s", action)
        _metric_inc("openclaw.auth.allowed")
        return warnings

    mode = str(config.openclaw_auth_mode or "enforce").lower()
    warning_message = "api auth credential missing or invalid"
    LOGGER.warning("openclaw.auth.denied action=%s mode=%s", action, mode)
    _metric_inc("openclaw.auth.denied")
    if mode == "enforce":
        raise ActionRuntimeFailureError("unauthorized request")
    if mode == "warn_only":
        warnings.append(warning_message)
    return warnings


def _coerce_scope_list(value: Any) -> list[str]:
    if isinstance(value, str):
        scopes = [item.strip() for item in value.split(",") if item.strip()]
        if not scopes:
            raise ActionValidationError(
                "params.scopes must contain at least one scope when provided"
            )
        return scopes
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        scopes = [item.strip() for item in value if item.strip()]
        if not scopes:
            raise ActionValidationError(
                "params.scopes must contain at least one scope when provided"
            )
        return scopes
    raise ActionValidationError("params.scopes must be a comma-separated string or string array")


def _resolve_caller_scopes(config: AppConfig, params: dict[str, Any]) -> set[str]:
    requested_scopes = params.get("scopes")
    if requested_scopes is not None:
        if not config.openclaw_scope_allow_param_scopes:
            raise ActionValidationError("params.scopes is not allowed by current policy")
        return set(_coerce_scope_list(requested_scopes))

    resolved_scopes = set(config.openclaw_scope_default_read_scopes)
    caller_token = params.get("caller_token")
    if isinstance(caller_token, str) and caller_token.strip():
        resolved_scopes.update(config.openclaw_scope_default_write_scopes)
    return resolved_scopes


def _enforce_action_scopes(config: AppConfig, *, action: str, params: dict[str, Any]) -> None:
    mode = str(config.openclaw_scope_mode or "off").lower()
    if mode == "off":
        return
    policy = ACTION_POLICY.get(action)
    if policy is None:
        return
    required_scopes = tuple(policy.get("required_scopes", ()))
    if not required_scopes:
        return
    caller_scopes = _resolve_caller_scopes(config=config, params=params)
    missing_scopes = [scope for scope in required_scopes if scope not in caller_scopes]
    if missing_scopes:
        _metric_inc("openclaw.scope.denied")
        if bool(policy.get("safe_write", False)):
            _metric_inc("openclaw.safe_write.denied")
        raise ActionRuntimeFailureError(
            f"forbidden action: {action} requires scopes [{', '.join(required_scopes)}]"
        )
    _metric_inc("openclaw.scope.allowed")
    if bool(policy.get("safe_write", False)):
        _metric_inc("openclaw.safe_write.allowed")


def _validate_int(error_message: str, value: Any) -> int:
    if not isinstance(value, int):
        raise ActionValidationError(error_message)
    return value


def _validate_optional_int(error_message: str, value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise ActionValidationError(error_message)
    return value


def _validate_optional_str(error_message: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ActionValidationError(error_message)
    return value


def _validate_required_str(error_message: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ActionValidationError(error_message)
    normalized = value.strip()
    if not normalized:
        raise ActionValidationError(error_message)
    return normalized


def _parse_iso_datetime(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ActionValidationError(f"{field} must be a string in ISO-8601 format")
    normalized = value.strip()
    if not normalized:
        raise ActionValidationError(f"{field} must be a non-empty ISO-8601 string")
    parsed_text = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(parsed_text)
    except ValueError as exc:
        raise ActionValidationError(f"{field} must be a valid ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _manual_items_from_params(value: Any) -> list[ManualItemInput]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ActionValidationError("manual_ingest params.items must be an array")
    items: list[ManualItemInput] = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            raise ActionValidationError("manual_ingest params.items entries must be objects")
        name = _validate_required_str(
            "manual_ingest params.items[].name must be a non-empty string",
            raw_item.get("name"),
        )
        line_total_raw = raw_item.get("line_total_cents")
        if not isinstance(line_total_raw, int):
            raise ActionValidationError(
                "manual_ingest params.items[].line_total_cents must be an integer"
            )
        if line_total_raw < 0:
            raise ActionValidationError(
                "manual_ingest params.items[].line_total_cents must be non-negative"
            )

        qty_raw = raw_item.get("qty", 1)
        if not isinstance(qty_raw, (int, float, str)):
            raise ActionValidationError(
                "manual_ingest params.items[].qty must be numeric when provided"
            )
        qty = Decimal(str(qty_raw))
        if qty <= Decimal("0"):
            raise ActionValidationError("manual_ingest params.items[].qty must be greater than 0")

        unit_price_raw = raw_item.get("unit_price_cents")
        if unit_price_raw is not None and not isinstance(unit_price_raw, int):
            raise ActionValidationError(
                "manual_ingest params.items[].unit_price_cents must be an integer"
            )
        line_no_raw = raw_item.get("line_no")
        if line_no_raw is not None and not isinstance(line_no_raw, int):
            raise ActionValidationError("manual_ingest params.items[].line_no must be an integer")
        source_item_id_raw = raw_item.get("source_item_id")
        if source_item_id_raw is not None and not isinstance(source_item_id_raw, str):
            raise ActionValidationError(
                "manual_ingest params.items[].source_item_id must be a string"
            )
        family_shared_raw = raw_item.get("family_shared", False)
        if not isinstance(family_shared_raw, bool):
            raise ActionValidationError(
                "manual_ingest params.items[].family_shared must be a boolean"
            )
        raw_payload = raw_item.get("raw_payload", {})
        if not isinstance(raw_payload, dict):
            raise ActionValidationError(
                "manual_ingest params.items[].raw_payload must be an object"
            )
        unit_raw = raw_item.get("unit")
        if unit_raw is not None and not isinstance(unit_raw, str):
            raise ActionValidationError("manual_ingest params.items[].unit must be a string")
        category_raw = raw_item.get("category")
        if category_raw is not None and not isinstance(category_raw, str):
            raise ActionValidationError("manual_ingest params.items[].category must be a string")

        items.append(
            ManualItemInput(
                name=name,
                line_total_cents=line_total_raw,
                qty=qty,
                unit=unit_raw.strip() if isinstance(unit_raw, str) and unit_raw.strip() else None,
                unit_price_cents=unit_price_raw,
                category=(
                    category_raw.strip()
                    if isinstance(category_raw, str) and category_raw.strip()
                    else None
                ),
                line_no=line_no_raw,
                source_item_id=(
                    source_item_id_raw.strip()
                    if isinstance(source_item_id_raw, str) and source_item_id_raw.strip()
                    else None
                ),
                family_shared=family_shared_raw,
                raw_payload=raw_payload,
            )
        )
    return items


def _manual_discounts_from_params(value: Any) -> list[ManualDiscountInput]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ActionValidationError("manual_ingest params.discounts must be an array")
    discounts: list[ManualDiscountInput] = []
    for raw_discount in value:
        if not isinstance(raw_discount, dict):
            raise ActionValidationError("manual_ingest params.discounts entries must be objects")
        source_label = _validate_required_str(
            "manual_ingest params.discounts[].source_label must be a non-empty string",
            raw_discount.get("source_label"),
        )
        amount_raw = raw_discount.get("amount_cents")
        if not isinstance(amount_raw, int):
            raise ActionValidationError(
                "manual_ingest params.discounts[].amount_cents must be an integer"
            )
        if amount_raw <= 0:
            raise ActionValidationError(
                "manual_ingest params.discounts[].amount_cents must be greater than 0"
            )

        scope_raw = raw_discount.get("scope", "transaction")
        if not isinstance(scope_raw, str) or scope_raw not in {"transaction", "item"}:
            raise ActionValidationError(
                "manual_ingest params.discounts[].scope must be 'transaction' or 'item'"
            )
        line_no_raw = raw_discount.get("transaction_item_line_no")
        if line_no_raw is not None and not isinstance(line_no_raw, int):
            raise ActionValidationError(
                "manual_ingest params.discounts[].transaction_item_line_no must be an integer"
            )
        if scope_raw == "item" and line_no_raw is None:
            raise ActionValidationError(
                "manual_ingest params.discounts[].transaction_item_line_no is required for item scope"
            )

        source_discount_code = raw_discount.get("source_discount_code")
        if source_discount_code is not None and not isinstance(source_discount_code, str):
            raise ActionValidationError(
                "manual_ingest params.discounts[].source_discount_code must be a string"
            )
        kind_raw = raw_discount.get("kind", "manual")
        if not isinstance(kind_raw, str):
            raise ActionValidationError("manual_ingest params.discounts[].kind must be a string")
        subkind_raw = raw_discount.get("subkind")
        if subkind_raw is not None and not isinstance(subkind_raw, str):
            raise ActionValidationError("manual_ingest params.discounts[].subkind must be a string")
        funded_by_raw = raw_discount.get("funded_by", "unknown")
        if not isinstance(funded_by_raw, str):
            raise ActionValidationError(
                "manual_ingest params.discounts[].funded_by must be a string"
            )
        is_loyalty_program_raw = raw_discount.get("is_loyalty_program", False)
        if not isinstance(is_loyalty_program_raw, bool):
            raise ActionValidationError(
                "manual_ingest params.discounts[].is_loyalty_program must be a boolean"
            )
        raw_payload = raw_discount.get("raw_payload", {})
        if not isinstance(raw_payload, dict):
            raise ActionValidationError(
                "manual_ingest params.discounts[].raw_payload must be an object"
            )

        discounts.append(
            ManualDiscountInput(
                source_label=source_label,
                amount_cents=amount_raw,
                scope=scope_raw,
                transaction_item_line_no=line_no_raw,
                source_discount_code=(
                    source_discount_code.strip()
                    if isinstance(source_discount_code, str) and source_discount_code.strip()
                    else None
                ),
                kind=kind_raw.strip() or "manual",
                subkind=(
                    subkind_raw.strip()
                    if isinstance(subkind_raw, str) and subkind_raw.strip()
                    else None
                ),
                funded_by=funded_by_raw.strip() or "unknown",
                is_loyalty_program=is_loyalty_program_raw,
                raw_payload=raw_payload,
            )
        )
    return discounts


def _session_factory_from_params(
    params: dict[str, Any],
) -> tuple[AppConfig, sessionmaker[Session]]:
    db_path = params.get("db")
    cfg_path = params.get("config")
    config = build_config(
        config_path=Path(cfg_path).expanduser() if cfg_path else None,
        db_override=Path(db_path).expanduser() if db_path else None,
    )
    db_url = database_url(config)
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    return config, session_factory(engine)


def _source_auth_state(config: AppConfig, source_id: str) -> dict[str, Any]:
    registry = get_connector_registry(config)
    manifest = registry.get_manifest(source_id)
    if manifest is None:
        return {
            "source": source_id,
            "auth_kind": "none",
            "status": "managed_externally",
            "reauth_required": False,
            "reauth_flag_set": False,
            "has_refresh_token": False,
            "state": "not_connected",
            "detail": "source is not registered in the connector auth registry",
            "available_actions": [],
            "implemented_actions": [],
            "compatibility_actions": [],
            "actions": {},
        }

    execution = ConnectorExecutionService(config=config)
    service = ConnectorAuthOrchestrationService(
        config=config,
        connector_builder=execution.build_receipt_connector,
    )
    snapshot = service.get_auth_status(source_id=source_id)
    auth_kind = snapshot.capabilities.auth_kind
    token_store = TokenStore.from_config(config) if auth_kind == "oauth_pkce" else None
    has_refresh_token = bool(token_store.get_refresh_token()) if token_store is not None else False
    reauth_flag = token_store.is_reauth_required() if token_store is not None else False
    status_map = {
        "connected": "authenticated",
        "reauth_required": "reauth_required",
        "not_connected": "missing_credentials",
        "bootstrap_running": "managed_externally",
        "bootstrap_canceled": "managed_externally",
        "auth_failed": "managed_externally",
        "connecting": "managed_externally",
    }
    auth_status = status_map.get(snapshot.state, "managed_externally")
    actions: dict[str, Any] = {}
    if source_bootstrap_command(source_id, registry=registry) is not None:
        actions["reauth_start"] = {
            "action": "source_auth_reauth_start",
            "params": {"source": source_id},
        }
    if auth_kind == "oauth_pkce":
        actions["reauth_confirm"] = {
            "action": "source_auth_reauth_confirm",
            "params": {"source": source_id},
        }
    return {
        "source": source_id,
        "auth_kind": auth_kind,
        "status": auth_status,
        "reauth_required": snapshot.state == "reauth_required",
        "reauth_flag_set": reauth_flag,
        "has_refresh_token": has_refresh_token,
        "state": snapshot.state,
        "detail": snapshot.detail,
        "available_actions": list(snapshot.available_actions),
        "implemented_actions": list(snapshot.implemented_actions),
        "compatibility_actions": list(snapshot.compatibility_actions),
        "actions": actions,
    }


def _emit_audit_event(
    sessions: sessionmaker[Session],
    *,
    action: str,
    source: str | None = None,
    actor_type: str = "agent",
    actor_id: str | None = None,
    entity_type: str | None = "source",
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        with session_scope(sessions) as session:
            record_audit_event(
                session,
                action=action,
                source=source,
                actor_type=actor_type,
                actor_id=actor_id,
                entity_type=entity_type,
                entity_id=entity_id or source,
                details=details,
            )
        _metric_inc("openclaw.audit.write.success")
    except Exception as exc:  # noqa: BLE001
        _metric_inc("openclaw.audit.write.failed")
        LOGGER.warning("audit.event.write_failed action=%s source=%s error=%s", action, source, exc)


def _handle_health(
    config: AppConfig, _: sessionmaker[Session], __: dict[str, Any]
) -> dict[str, Any]:
    return {
        "status": "ok",
        "version": CONTRACT_VERSION,
        "source": config.source,
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }


def _handle_sync(
    config: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    full = bool(params.get("full", False))
    trigger_type = str(params.get("trigger_type", "manual"))
    retry = bool(params.get("retry", False))
    window_start = _validate_optional_str(
        "sync params.window_start must be a string", params.get("window_start")
    )
    window_end = _validate_optional_str(
        "sync params.window_end must be a string", params.get("window_end")
    )
    caller_token = _validate_optional_str(
        "sync params.caller_token must be a string", params.get("caller_token")
    )
    explicit_idempotency_key = _validate_optional_str(
        "sync params.idempotency_key must be a string", params.get("idempotency_key")
    )
    source = _validate_optional_str("sync params.source must be a string", params.get("source"))
    target_source = source or config.source

    manifest = get_connector_registry(config).get_manifest(target_source)
    if manifest is not None and manifest.auth_kind == "oauth_pkce":
        token_store = TokenStore.from_config(config)
        token = token_store.get_refresh_token()
        if not token:
            raise ActionRuntimeFailureError("auth token missing; run lidltool auth bootstrap")

    jobs = JobService(session_factory=sessions, config=config)
    job, reused = jobs.create_sync_job(
        full=full,
        source=source,
        trigger_type=trigger_type,
        retry=retry,
        idempotency_key=explicit_idempotency_key,
        window_start=window_start,
        window_end=window_end,
        caller_token=caller_token,
    )
    source_id = job.source_id
    audit_action = "source.sync.retry_triggered" if retry else "source.sync.triggered"
    _emit_audit_event(
        sessions,
        action=audit_action,
        source=source_id,
        actor_type="agent",
        actor_id=caller_token,
        entity_type="ingestion_job",
        entity_id=job.id,
        details={
            "action_origin": "openclaw",
            "action_category": "safe_write",
            "contract_version": CONTRACT_VERSION,
            "job_id": job.id,
            "reused": reused,
            "trigger_type": trigger_type,
            "full": full,
            "retry": retry,
        },
    )
    return {"job_id": job.id, "status": job.status, "reused": reused, "source": job.source_id}


def _handle_manual_ingest(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    source_id = _validate_optional_str(
        "manual_ingest params.source_id must be a string", params.get("source_id")
    )
    source_display_name = _validate_optional_str(
        "manual_ingest params.source_display_name must be a string",
        params.get("source_display_name"),
    )
    source_account_ref = _validate_optional_str(
        "manual_ingest params.source_account_ref must be a string",
        params.get("source_account_ref"),
    )
    source_transaction_id = _validate_optional_str(
        "manual_ingest params.source_transaction_id must be a string",
        params.get("source_transaction_id"),
    )
    idempotency_key = _validate_optional_str(
        "manual_ingest params.idempotency_key must be a string",
        params.get("idempotency_key"),
    )
    caller_token = _validate_optional_str(
        "manual_ingest params.caller_token must be a string",
        params.get("caller_token"),
    )
    user_id = _validate_optional_str(
        "manual_ingest params.user_id must be a string", params.get("user_id")
    )
    purchased_at = _parse_iso_datetime(
        params.get("purchased_at"), field="manual_ingest params.purchased_at"
    )
    merchant_name = _validate_required_str(
        "manual_ingest params.merchant_name must be a non-empty string",
        params.get("merchant_name"),
    )
    total_gross_cents = _validate_int(
        "manual_ingest params.total_gross_cents must be an integer",
        params.get("total_gross_cents"),
    )
    if total_gross_cents < 0:
        raise ActionValidationError("manual_ingest params.total_gross_cents must be non-negative")
    currency = _validate_optional_str(
        "manual_ingest params.currency must be a string", params.get("currency")
    )
    discount_total_cents = _validate_optional_int(
        "manual_ingest params.discount_total_cents must be an integer",
        params.get("discount_total_cents"),
    )
    family_share_mode = _validate_optional_str(
        "manual_ingest params.family_share_mode must be a string",
        params.get("family_share_mode"),
    )
    resolved_family_share_mode = family_share_mode or "inherit"
    if resolved_family_share_mode not in {"receipt", "items", "none", "inherit"}:
        raise ActionValidationError(
            "manual_ingest params.family_share_mode must be one of: receipt, items, none, inherit"
        )

    confidence_raw = params.get("confidence")
    if confidence_raw is not None and not isinstance(confidence_raw, (int, float)):
        raise ActionValidationError("manual_ingest params.confidence must be numeric")
    confidence = float(confidence_raw) if confidence_raw is not None else None
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise ActionValidationError("manual_ingest params.confidence must be between 0 and 1")

    raw_payload = params.get("raw_payload", {})
    if not isinstance(raw_payload, dict):
        raise ActionValidationError("manual_ingest params.raw_payload must be an object")
    reason = _validate_optional_str(
        "manual_ingest params.reason must be a string", params.get("reason")
    )
    items = _manual_items_from_params(params.get("items"))
    discounts = _manual_discounts_from_params(params.get("discounts"))

    service = ManualIngestService(session_factory=sessions)
    ingest_result = service.ingest_transaction(
        payload=ManualTransactionInput(
            purchased_at=purchased_at,
            merchant_name=merchant_name,
            total_gross_cents=total_gross_cents,
            source_id=(source_id or AGENT_SOURCE_ID).strip(),
            source_kind="agent",
            source_display_name=(source_display_name or "Agent Ingestion").strip(),
            source_account_ref=source_account_ref or "agent",
            source_transaction_id=source_transaction_id,
            idempotency_key=idempotency_key,
            user_id=user_id,
            currency=(currency or "EUR").strip().upper(),
            discount_total_cents=discount_total_cents,
            family_share_mode=resolved_family_share_mode,
            confidence=confidence,
            items=items,
            discounts=discounts,
            raw_payload=raw_payload,
            ingest_channel="openclaw_agent",
        ),
        actor_type="agent",
        actor_id=caller_token,
        audit_action="transaction.agent_ingested",
        reason=reason,
    )
    return ingest_result


def _handle_source_auth_status(
    config: AppConfig, _: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    source_id = _validate_optional_str(
        "source_auth_status params.source must be a string", params.get("source")
    )
    target_source = source_id or config.source
    return _source_auth_state(config, target_source)


def _handle_source_auth_reauth_start(
    config: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    source_id = _validate_optional_str(
        "source_auth_reauth_start params.source must be a string", params.get("source")
    )
    actor_id = _validate_optional_str(
        "source_auth_reauth_start params.caller_token must be a string", params.get("caller_token")
    )
    target_source = source_id or config.source
    registry = get_connector_registry(config)
    manifest = registry.get_manifest(target_source)
    if manifest is None:
        raise ActionRuntimeFailureError(f"source not found: {target_source}")
    bootstrap_command = source_bootstrap_command(target_source, registry=registry)
    if bootstrap_command is None:
        raise ActionRuntimeFailureError(
            f"re-authentication bootstrap not supported for source: {target_source}"
        )
    instruction = f"Run `{' '.join(bootstrap_command)}` to re-authenticate this source."
    _emit_audit_event(
        sessions,
        action="source.reauth.started",
        source=target_source,
        actor_type="agent",
        actor_id=actor_id,
        details={
            "action_origin": "openclaw",
            "action_category": "safe_write",
            "contract_version": CONTRACT_VERSION,
            "instructions": instruction,
        },
    )
    auth = _source_auth_state(config, target_source)
    next_action = (
        {"action": "source_auth_reauth_confirm", "params": {"source": target_source}}
        if manifest.auth_kind == "oauth_pkce"
        else None
    )
    return {
        "source": target_source,
        "reauth_started": True,
        "instructions": instruction,
        "next_action": next_action,
        "auth": auth,
    }


def _handle_source_auth_reauth_confirm(
    config: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    source_id = _validate_optional_str(
        "source_auth_reauth_confirm params.source must be a string", params.get("source")
    )
    actor_id = _validate_optional_str(
        "source_auth_reauth_confirm params.caller_token must be a string",
        params.get("caller_token"),
    )
    target_source = source_id or config.source
    manifest = get_connector_registry(config).get_manifest(target_source)
    if manifest is None:
        raise ActionRuntimeFailureError(f"source not found: {target_source}")
    if manifest.auth_kind != "oauth_pkce":
        raise ActionRuntimeFailureError(
            f"re-authentication confirm is not supported for auth_kind={manifest.auth_kind}"
        )
    token_store = TokenStore.from_config(config)
    refresh_token = token_store.get_refresh_token()
    if not refresh_token:
        _emit_audit_event(
            sessions,
            action="source.reauth.failed",
            source=target_source,
            actor_type="agent",
            actor_id=actor_id,
            details={
                "action_origin": "openclaw",
                "action_category": "safe_write",
                "contract_version": CONTRACT_VERSION,
                "reason": "missing_refresh_token",
            },
        )
        raise ActionRuntimeFailureError(
            "re-authentication not confirmed: missing refresh token; run lidltool auth bootstrap"
        )

    token_store.clear_reauth_required()
    _emit_audit_event(
        sessions,
        action="source.reauth.completed",
        source=target_source,
        actor_type="agent",
        actor_id=actor_id,
        details={
            "action_origin": "openclaw",
            "action_category": "safe_write",
            "contract_version": CONTRACT_VERSION,
            "refresh_token_present": True,
        },
    )
    return {
        "source": target_source,
        "reauth_confirmed": True,
        "auth": _source_auth_state(config, target_source),
    }


def _handle_stats_month(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    started_at = time.monotonic()
    year = _validate_int("stats_month requires integer params.year", params.get("year"))
    month = _validate_optional_int(
        "stats_month params.month must be an integer", params.get("month")
    )
    with session_scope(sessions) as session:
        result = month_stats(session, year=year, month=month)
    result["query_duration_ms"] = int((time.monotonic() - started_at) * 1000)
    return result


def _job_duration_ms(job: IngestionJob) -> int | None:
    if job.started_at is None or job.finished_at is None:
        return None
    started_at = (
        job.started_at.replace(tzinfo=UTC) if job.started_at.tzinfo is None else job.started_at
    )
    finished_at = (
        job.finished_at.replace(tzinfo=UTC) if job.finished_at.tzinfo is None else job.finished_at
    )
    return max(int((finished_at - started_at).total_seconds() * 1000), 0)


def _build_source_health_summary(
    *,
    source: Source,
    jobs: list[IngestionJob],
    min_success_rate: float,
    alert_on_dead_letter: bool,
    alert_dedupe_window_hours: int,
    escalation_failure_threshold: int,
) -> dict[str, Any]:
    terminal_jobs = [
        job for job in jobs if job.status in {"success", "partial_success", "failed", "canceled"}
    ]
    successful_jobs = [job for job in terminal_jobs if job.status in {"success", "partial_success"}]
    failed_jobs = [job for job in terminal_jobs if job.status in {"failed", "canceled"}]
    success_rate = (len(successful_jobs) / len(terminal_jobs)) if terminal_jobs else 1.0
    durations = [
        duration for job in terminal_jobs if (duration := _job_duration_ms(job)) is not None
    ]
    avg_duration_ms = int(sum(durations) / len(durations)) if durations else None

    dead_letter_jobs = 0
    for job in failed_jobs:
        summary = job.summary if isinstance(job.summary, dict) else {}
        dead_letter = summary.get("dead_letter")
        if isinstance(dead_letter, dict) and dead_letter.get("dead_lettered") is True:
            dead_letter_jobs += 1

    dedupe_cutoff = datetime.now(tz=UTC) - timedelta(hours=max(alert_dedupe_window_hours, 1))
    recent_failed_jobs = [
        job
        for job in failed_jobs
        if job.created_at is not None
        and (
            job.created_at.replace(tzinfo=UTC) if job.created_at.tzinfo is None else job.created_at
        )
        >= dedupe_cutoff
    ]

    alerts: list[dict[str, Any]] = []
    if success_rate < min_success_rate and recent_failed_jobs:
        level = (
            "critical"
            if len(recent_failed_jobs) >= max(escalation_failure_threshold, 1)
            else "warning"
        )
        alerts.append(
            {
                "level": level,
                "code": "low_success_rate",
                "message": f"success rate {success_rate:.3f} below threshold {min_success_rate:.3f}",
            }
        )
    if alert_on_dead_letter and dead_letter_jobs > 0 and recent_failed_jobs:
        alerts.append(
            {
                "level": "critical",
                "code": "dead_letter_jobs",
                "message": f"{dead_letter_jobs} dead-lettered retries in lookback window",
            }
        )
    deduped_alerts: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for alert in alerts:
        code = str(alert.get("code", "unknown"))
        if code in seen_codes:
            continue
        seen_codes.add(code)
        deduped_alerts.append(alert)
    latest_error = failed_jobs[0].error if failed_jobs else None
    return {
        "source": source.id,
        "status": source.status,
        "jobs_total": len(jobs),
        "jobs_terminal": len(terminal_jobs),
        "jobs_successful": len(successful_jobs),
        "jobs_failed": len(failed_jobs),
        "dead_letter_jobs": dead_letter_jobs,
        "success_rate": round(success_rate, 4),
        "avg_duration_ms": avg_duration_ms,
        "latest_error": latest_error,
        "alerts": deduped_alerts,
    }


def _percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(min(int(math.ceil(q * len(ordered))) - 1, len(ordered) - 1), 0)
    return ordered[idx]


def _summary_result(job: IngestionJob) -> dict[str, Any]:
    summary = job.summary if isinstance(job.summary, dict) else {}
    result = summary.get("result")
    if isinstance(result, dict):
        return result
    return {}


def _estimate_cost_units(
    *,
    terminal_jobs: list[IngestionJob],
    durations_ms: list[int],
    total_new_receipts: int,
    total_new_items: int,
) -> int:
    # Cost proxy: combine runtime and ingestion volume into one additive score.
    duration_score = int(sum(durations_ms) / 1000)
    job_score = len(terminal_jobs) * 5
    receipt_score = total_new_receipts * 2
    item_score = total_new_items
    return max(duration_score + job_score + receipt_score + item_score, 0)


def _build_source_cost_performance_summary(
    *, source: Source, jobs: list[IngestionJob]
) -> dict[str, Any]:
    terminal_jobs = [
        job for job in jobs if job.status in {"success", "partial_success", "failed", "canceled"}
    ]
    successful_jobs = [job for job in terminal_jobs if job.status in {"success", "partial_success"}]
    failed_jobs = [job for job in terminal_jobs if job.status in {"failed", "canceled"}]
    success_rate = (len(successful_jobs) / len(terminal_jobs)) if terminal_jobs else 1.0
    durations = [
        duration for job in terminal_jobs if (duration := _job_duration_ms(job)) is not None
    ]
    avg_duration_ms = int(sum(durations) / len(durations)) if durations else None
    p95_duration_ms = _percentile(durations, 0.95)

    new_receipts: list[int] = []
    new_items: list[int] = []
    dead_letter_jobs = 0
    for job in terminal_jobs:
        result = _summary_result(job)
        new_receipts.append(int(result.get("new_receipts", 0) or 0))
        new_items.append(int(result.get("new_items", 0) or 0))
        summary = job.summary if isinstance(job.summary, dict) else {}
        dead_letter = summary.get("dead_letter")
        if isinstance(dead_letter, dict) and dead_letter.get("dead_lettered") is True:
            dead_letter_jobs += 1

    total_new_receipts = sum(new_receipts)
    total_new_items = sum(new_items)
    avg_new_receipts = (total_new_receipts / len(terminal_jobs)) if terminal_jobs else 0.0
    avg_new_items = (total_new_items / len(terminal_jobs)) if terminal_jobs else 0.0
    estimated_cost_units = _estimate_cost_units(
        terminal_jobs=terminal_jobs,
        durations_ms=durations,
        total_new_receipts=total_new_receipts,
        total_new_items=total_new_items,
    )
    return {
        "source": source.id,
        "status": source.status,
        "jobs_total": len(jobs),
        "jobs_terminal": len(terminal_jobs),
        "jobs_successful": len(successful_jobs),
        "jobs_failed": len(failed_jobs),
        "dead_letter_jobs": dead_letter_jobs,
        "success_rate": round(success_rate, 4),
        "avg_duration_ms": avg_duration_ms,
        "p95_duration_ms": p95_duration_ms,
        "avg_new_receipts": round(avg_new_receipts, 2),
        "avg_new_items": round(avg_new_items, 2),
        "estimated_cost_units": estimated_cost_units,
    }


def _handle_connector_health_dashboard(
    config: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    source_filter = _validate_optional_str(
        "connector_health_dashboard params.source must be a string", params.get("source")
    )
    window_days_param = _validate_optional_int(
        "connector_health_dashboard params.window_days must be an integer",
        params.get("window_days"),
    )
    lookback_days = (
        window_days_param if window_days_param is not None else config.health_window_days
    )
    lookback_days = max(int(lookback_days), 1)
    min_success_rate = float(config.health_min_success_rate)
    alert_on_dead_letter = bool(config.health_alert_on_dead_letter)
    alert_dedupe_window_hours = int(config.health_alert_dedupe_window_hours)
    escalation_failure_threshold = int(config.health_escalation_failure_threshold)
    correlation_min_sources = int(config.health_correlation_min_sources)
    since = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    with session_scope(sessions) as session:
        source_stmt = select(Source).order_by(Source.id.asc())
        sources = session.execute(source_stmt).scalars().all()
        if not sources:
            return {
                "window_days": lookback_days,
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "sources": [],
                "totals": {"sources": 0, "alerts": 0},
            }

        dashboard_sources: list[dict[str, Any]] = []
        for source in sources:
            if source_filter and source.id != source_filter:
                continue
            jobs_stmt = (
                select(IngestionJob)
                .where(IngestionJob.source_id == source.id, IngestionJob.created_at >= since)
                .order_by(IngestionJob.created_at.desc())
            )
            source_jobs = list(session.execute(jobs_stmt).scalars().all())
            dashboard_sources.append(
                _build_source_health_summary(
                    source=source,
                    jobs=source_jobs,
                    min_success_rate=min_success_rate,
                    alert_on_dead_letter=alert_on_dead_letter,
                    alert_dedupe_window_hours=alert_dedupe_window_hours,
                    escalation_failure_threshold=escalation_failure_threshold,
                )
            )

    low_success_sources = [
        item
        for item in dashboard_sources
        if any(str(alert.get("code")) == "low_success_rate" for alert in item.get("alerts", []))
    ]
    global_alerts: list[dict[str, Any]] = []
    if len(low_success_sources) >= max(correlation_min_sources, 2):
        global_alerts.append(
            {
                "level": "critical",
                "code": "correlated_source_degradation",
                "message": f"{len(low_success_sources)} sources have low_success_rate alerts",
            }
        )

    alert_count = sum(len(item.get("alerts", [])) for item in dashboard_sources)
    return {
        "window_days": lookback_days,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "thresholds": {
            "min_success_rate": min_success_rate,
            "alert_on_dead_letter": alert_on_dead_letter,
            "alert_dedupe_window_hours": alert_dedupe_window_hours,
            "escalation_failure_threshold": escalation_failure_threshold,
            "correlation_min_sources": correlation_min_sources,
        },
        "sources": dashboard_sources,
        "global_alerts": global_alerts,
        "totals": {"sources": len(dashboard_sources), "alerts": alert_count + len(global_alerts)},
    }


def _handle_connector_cost_performance_review(
    config: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    source_filter = _validate_optional_str(
        "connector_cost_performance_review params.source must be a string", params.get("source")
    )
    window_days_param = _validate_optional_int(
        "connector_cost_performance_review params.window_days must be an integer",
        params.get("window_days"),
    )
    lookback_days = (
        window_days_param if window_days_param is not None else config.health_window_days
    )
    lookback_days = max(int(lookback_days), 1)
    since = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    with session_scope(sessions) as session:
        source_stmt = select(Source).order_by(Source.id.asc())
        sources = session.execute(source_stmt).scalars().all()
        if not sources:
            return {
                "window_days": lookback_days,
                "generated_at": datetime.now(tz=UTC).isoformat(),
                "sources": [],
                "totals": {"sources": 0, "jobs_terminal": 0, "estimated_cost_units": 0},
            }

        review_sources: list[dict[str, Any]] = []
        for source in sources:
            if source_filter and source.id != source_filter:
                continue
            jobs_stmt = (
                select(IngestionJob)
                .where(IngestionJob.source_id == source.id, IngestionJob.created_at >= since)
                .order_by(IngestionJob.created_at.desc())
            )
            source_jobs = list(session.execute(jobs_stmt).scalars().all())
            review_sources.append(
                _build_source_cost_performance_summary(source=source, jobs=source_jobs)
            )

    jobs_terminal_total = sum(int(item.get("jobs_terminal", 0) or 0) for item in review_sources)
    estimated_cost_units_total = sum(
        int(item.get("estimated_cost_units", 0) or 0) for item in review_sources
    )
    return {
        "window_days": lookback_days,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "cost_model": "cost_proxy_v1",
        "sources": review_sources,
        "totals": {
            "sources": len(review_sources),
            "jobs_terminal": jobs_terminal_total,
            "estimated_cost_units": estimated_cost_units_total,
        },
    }


def _handle_sync_status(
    config: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    job_id = _validate_optional_str(
        "sync_status params.job_id must be a string", params.get("job_id")
    )
    if isinstance(job_id, str) and job_id:
        jobs = JobService(session_factory=sessions, config=config)
        result = jobs.get_job_status_payload(job_id=job_id)
        if result is None:
            raise ActionRuntimeFailureError(f"sync job not found: {job_id}")
        recovery = _build_recovery_payload(
            status=result.get("status"),
            error=result.get("error"),
        )
        result["failure_classification"] = recovery["failure_classification"]
        result["recommended_recovery_action"] = recovery["recommended_recovery_action"]
        result["capabilities"] = recovery["capabilities"]
        result["recovery_message"] = recovery["recovery_message"]
        return result

    requested_source = _validate_optional_str(
        "sync_status params.source must be a string", params.get("source")
    )
    source = requested_source or config.source
    with session_scope(sessions) as session:
        state = session.get(SyncState, source)
    if state is None:
        recovery = _build_recovery_payload(status=None, error=None)
        return {
            "source": source,
            "last_success_at": None,
            "last_seen_receipt_at": None,
            "last_seen_receipt_id": None,
            "failure_classification": recovery["failure_classification"],
            "recommended_recovery_action": recovery["recommended_recovery_action"],
            "capabilities": recovery["capabilities"],
            "recovery_message": recovery["recovery_message"],
        }
    recovery = _build_recovery_payload(status=None, error=None)
    return {
        "source": source,
        "last_success_at": (
            state.last_success_at.isoformat() if state.last_success_at is not None else None
        ),
        "last_seen_receipt_at": (
            state.last_seen_receipt_at.isoformat()
            if state.last_seen_receipt_at is not None
            else None
        ),
        "last_seen_receipt_id": state.last_seen_receipt_id,
        "failure_classification": recovery["failure_classification"],
        "recommended_recovery_action": recovery["recommended_recovery_action"],
        "capabilities": recovery["capabilities"],
        "recovery_message": recovery["recovery_message"],
    }


def _handle_sources_list(
    config: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    include_disabled = bool(params.get("include_disabled", False))
    registry = get_connector_registry(config)
    with session_scope(sessions) as session:
        sources = session.execute(select(Source).order_by(Source.id.asc())).scalars().all()
        persisted_by_id = {source.id: source for source in sources}
        items: list[dict[str, Any]] = []
        for manifest in registry.list_manifests(plugin_family="receipt"):
            source = persisted_by_id.get(manifest.source_id)
            if source is None:
                items.append(_default_source_payload(config, manifest.source_id, registry=registry))
                continue
            if not include_disabled and not source.enabled:
                continue
            account = _first_source_account(session, source.id)
            latest_job = _latest_job_for_source(session, source.id)
            sync_state = session.get(SyncState, source.id)
            auth = _source_auth_state(config, source.id)
            items.append(
                _source_payload(
                    source,
                    account,
                    latest_job,
                    sync_state=sync_state,
                    auth=auth,
                    config=config,
                    registry=registry,
                )
            )
        for source in sources:
            if source.id in persisted_by_id and registry.has_source(source.id):
                continue
            if not include_disabled and not source.enabled:
                continue
            account = _first_source_account(session, source.id)
            latest_job = _latest_job_for_source(session, source.id)
            sync_state = session.get(SyncState, source.id)
            auth = _source_auth_state(config, source.id)
            items.append(
                _source_payload(
                    source,
                    account,
                    latest_job,
                    sync_state=sync_state,
                    auth=auth,
                    config=config,
                    registry=registry,
                )
            )
        if not items:
            items.append(_default_source_payload(config, config.source, registry=registry))

    return {
        "sources": items,
        "catalog": source_catalog(config=config, registry=registry),
        "discovery_catalog": connector_catalog_payload(
            product="self_hosted",
            config=config,
            registry=registry,
        ),
        "plugin_management": plugin_management_payload(
            session,
            config=config,
            registry=registry,
        ),
        "market_strategy": self_hosted_market_strategy_payload(config),
        "sync_actions": {
            "global": {"action": "sync", "params": {}},
            "per_source": {"action": "sync", "params_template": {"source": "<source_id>"}},
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


def _handle_source_status(
    config: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    source_id = _validate_optional_str(
        "source_status params.source must be a string", params.get("source")
    )
    if not source_id:
        raise ActionValidationError("source_status requires params.source")

    registry = get_connector_registry(config)
    with session_scope(sessions) as session:
        source = session.get(Source, source_id)
        if source is None:
            if registry.has_source(source_id) or source_id == config.source:
                return _default_source_payload(config, source_id, registry=registry)
            raise ActionRuntimeFailureError(f"source not found: {source_id}")
        account = _first_source_account(session, source_id)
        latest_job = _latest_job_for_source(session, source_id)
        sync_state = session.get(SyncState, source_id)
        auth = _source_auth_state(config, source_id)
        return _source_payload(
            source,
            account,
            latest_job,
            sync_state=sync_state,
            auth=auth,
            config=config,
            registry=registry,
        )


def _first_source_account(session: Session, source_id: str) -> SourceAccount | None:
    stmt = (
        select(SourceAccount)
        .where(SourceAccount.source_id == source_id)
        .order_by(SourceAccount.created_at.asc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _latest_job_for_source(session: Session, source_id: str) -> IngestionJob | None:
    stmt = (
        select(IngestionJob)
        .where(IngestionJob.source_id == source_id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def _source_payload(
    source: Source,
    account: SourceAccount | None,
    latest_job: IngestionJob | None,
    *,
    sync_state: SyncState | None,
    auth: dict[str, Any],
    config: AppConfig,
    registry: Any,
) -> dict[str, Any]:
    status, status_reason = _derive_source_status(source, account, latest_job, auth=auth)
    progress: dict[str, Any] = {}
    timeline: list[dict[str, Any]] = []
    warnings: list[str] = []
    result: dict[str, Any] = {}
    if latest_job is not None and isinstance(latest_job.summary, dict):
        summary = latest_job.summary
        summary_progress = summary.get("progress")
        if isinstance(summary_progress, dict):
            progress = summary_progress
        summary_timeline = summary.get("timeline")
        if isinstance(summary_timeline, list):
            timeline = [item for item in summary_timeline if isinstance(item, dict)]
        summary_warnings = summary.get("warnings")
        if isinstance(summary_warnings, list):
            warnings = [str(item) for item in summary_warnings]
        summary_result = summary.get("result")
        if not warnings and isinstance(summary_result, dict):
            result_warnings = summary_result.get("warnings")
            if isinstance(result_warnings, list):
                warnings = [str(item) for item in result_warnings]
        if isinstance(summary_result, dict):
            result = summary_result

    recovery = _build_recovery_payload(
        status=latest_job.status if latest_job is not None else None,
        error=latest_job.error if latest_job is not None else None,
    )
    history = _build_sync_history_summary(
        latest_job=latest_job,
        sync_state=sync_state,
        warnings=warnings,
        result=result,
    )

    return {
        "source": source.id,
        "display_name": source.display_name,
        "kind": source.kind,
        "plugin": source_manifest_payload(source.id, config=config, registry=registry),
        "enabled": source.enabled,
        "status": status,
        "status_reason": status_reason,
        "account": {
            "id": account.id if account is not None else None,
            "account_ref": account.account_ref if account is not None else None,
            "status": account.status if account is not None else None,
            "last_success_at": (
                account.last_success_at.isoformat()
                if account is not None and account.last_success_at is not None
                else None
            ),
        },
        "latest_job": (
            {
                "job_id": latest_job.id,
                "status": latest_job.status,
                "started_at": (
                    latest_job.started_at.isoformat() if latest_job.started_at is not None else None
                ),
                "finished_at": (
                    latest_job.finished_at.isoformat()
                    if latest_job.finished_at is not None
                    else None
                ),
                "progress": progress,
                "timeline": timeline[-20:],
                "warnings": warnings,
                "error": latest_job.error,
                "failure_classification": recovery["failure_classification"],
                "recommended_recovery_action": recovery["recommended_recovery_action"],
                "capabilities": recovery["capabilities"],
                "recovery_message": recovery["recovery_message"],
            }
            if latest_job is not None
            else None
        ),
        "auth": auth,
        "recovery": recovery,
        "sync_history": history,
        "sync_action": {"action": "sync", "params": {"source": source.id}},
    }


def _default_source_payload(config: AppConfig, source_id: str, *, registry: Any) -> dict[str, Any]:
    auth = _source_auth_state(config, source_id)
    recovery = _build_recovery_payload(status=None, error=None)
    plugin = source_manifest_payload(source_id, config=config, registry=registry)
    status_reason = "source known but has no sync history yet"
    if isinstance(plugin, dict) and plugin.get("status") not in {None, "enabled"}:
        detail = plugin.get("status_detail")
        status_reason = (
            f"plugin is present but not active: {detail}"
            if isinstance(detail, str) and detail
            else "plugin is present but not active"
        )
    return {
        "source": source_id,
        "display_name": source_display_name(source_id, config=config, registry=registry),
        "kind": "connector",
        "plugin": plugin,
        "enabled": True,
        "status": SOURCE_STATUS_CONNECTED,
        "status_reason": status_reason,
        "account": {
            "id": None,
            "account_ref": None,
            "status": SOURCE_STATUS_CONNECTED,
            "last_success_at": None,
        },
        "latest_job": None,
        "auth": auth,
        "recovery": recovery,
        "sync_history": _empty_sync_history_summary(),
        "sync_action": {"action": "sync", "params": {"source": source_id}},
    }


def _derive_source_status(
    source: Source,
    account: SourceAccount | None,
    latest_job: IngestionJob | None,
    *,
    auth: dict[str, Any],
) -> tuple[str, str]:
    if not source.enabled:
        return SOURCE_STATUS_FAILING, "source is disabled"

    source_status = source.status.lower()
    account_status = account.status.lower() if account is not None else SOURCE_STATUS_CONNECTED
    latest_job_status = latest_job.status.lower() if latest_job is not None else None

    if bool(auth.get("reauth_required")):
        return SOURCE_STATUS_EXPIRED_AUTH, "source requires re-authentication"
    if source_status == SOURCE_STATUS_EXPIRED_AUTH or account_status == SOURCE_STATUS_EXPIRED_AUTH:
        return SOURCE_STATUS_EXPIRED_AUTH, "source account authentication expired"
    if _looks_like_auth_error(latest_job.error if latest_job is not None else None):
        return SOURCE_STATUS_EXPIRED_AUTH, "latest sync failed due to auth/token issue"
    if source_status == SOURCE_STATUS_FAILING or account_status == SOURCE_STATUS_FAILING:
        return SOURCE_STATUS_FAILING, "source reported failing status"
    if latest_job_status in TERMINAL_FAILURE_STATES:
        return SOURCE_STATUS_FAILING, "latest sync failed"
    if latest_job_status in {"success", "partial_success"}:
        return SOURCE_STATUS_HEALTHY, "latest sync completed"
    if source_status == SOURCE_STATUS_HEALTHY:
        return SOURCE_STATUS_HEALTHY, "source reported healthy status"
    if account_status == SOURCE_STATUS_CONNECTED:
        return SOURCE_STATUS_CONNECTED, "source account connected"
    return SOURCE_STATUS_CONNECTED, "source status inferred from account state"


def _looks_like_auth_error(error: str | None) -> bool:
    if not error:
        return False
    lowered = error.lower()
    return any(token in lowered for token in ("auth", "token", "unauthorized", "expired"))


def _classify_failure(status: Any, error: Any) -> str:
    if status is None and not error:
        return FAILURE_NONE
    status_text = str(status or "").lower()
    error_text = str(error or "").strip()
    lowered = error_text.lower()
    if status_text == "canceled":
        return FAILURE_CANCELED
    if _looks_like_auth_error(error_text):
        return FAILURE_AUTH_EXPIRED
    if any(
        token in lowered
        for token in ("timeout", "tempor", "network", "429", "500", "502", "503", "504")
    ):
        return FAILURE_TRANSIENT_UPSTREAM
    if any(
        token in lowered
        for token in ("invalid", "config", "missing", "validation", "schema", "param")
    ):
        return FAILURE_CONFIGURATION
    if status_text in TERMINAL_FAILURE_STATES or error_text:
        return FAILURE_UNKNOWN
    return FAILURE_NONE


def _build_recovery_payload(status: Any, error: Any) -> dict[str, Any]:
    failure = _classify_failure(status=status, error=error)
    action_map = {
        FAILURE_NONE: "none",
        FAILURE_AUTH_EXPIRED: "reauthenticate_source",
        FAILURE_TRANSIENT_UPSTREAM: "retry_sync",
        FAILURE_CONFIGURATION: "review_configuration",
        FAILURE_CANCELED: "retry_sync",
        FAILURE_UNKNOWN: "retry_sync",
    }
    message_map = {
        FAILURE_NONE: "No recovery action required.",
        FAILURE_AUTH_EXPIRED: "Authentication expired. Re-authenticate this source and confirm.",
        FAILURE_TRANSIENT_UPSTREAM: "Transient upstream failure detected. Retry sync.",
        FAILURE_CONFIGURATION: "Configuration issue detected. Review configuration and retry.",
        FAILURE_CANCELED: "Sync was canceled. Retry sync when ready.",
        FAILURE_UNKNOWN: "Sync failed. Retry sync and inspect latest error details.",
    }
    return {
        "failure_classification": failure,
        "recommended_recovery_action": action_map[failure],
        "capabilities": {
            "can_retry": failure
            in {
                FAILURE_TRANSIENT_UPSTREAM,
                FAILURE_CONFIGURATION,
                FAILURE_CANCELED,
                FAILURE_UNKNOWN,
            },
            "can_reauth": failure == FAILURE_AUTH_EXPIRED,
        },
        "recovery_message": message_map[failure],
    }


def _empty_sync_history_summary() -> dict[str, Any]:
    return {
        "last_success_at": None,
        "last_duration_ms": None,
        "last_new_records": 0,
        "last_new_items": 0,
        "last_error": None,
        "warnings": [],
    }


def _build_sync_history_summary(
    *,
    latest_job: IngestionJob | None,
    sync_state: SyncState | None,
    warnings: list[str],
    result: dict[str, Any],
) -> dict[str, Any]:
    summary = _empty_sync_history_summary()
    last_success = sync_state.last_success_at if sync_state is not None else None
    if (
        latest_job is not None
        and latest_job.status in {"success", "partial_success"}
        and latest_job.finished_at is not None
    ):
        last_success = latest_job.finished_at
    summary["last_success_at"] = last_success.isoformat() if last_success is not None else None

    if (
        latest_job is not None
        and latest_job.started_at is not None
        and latest_job.finished_at is not None
    ):
        duration_ms = int((latest_job.finished_at - latest_job.started_at).total_seconds() * 1000)
        summary["last_duration_ms"] = max(duration_ms, 0)
    progress: dict[str, Any] = {}
    if latest_job is not None and isinstance(latest_job.summary, dict):
        maybe_progress = latest_job.summary.get("progress")
        if isinstance(maybe_progress, dict):
            progress = maybe_progress
    summary["last_new_records"] = int(
        result.get("new_receipts", progress.get("new_receipts", 0)) or 0
    )
    summary["last_new_items"] = int(result.get("new_items", progress.get("new_items", 0)) or 0)
    summary["last_error"] = latest_job.error if latest_job is not None else None
    summary["warnings"] = warnings
    return summary


def _handle_savings_breakdown(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    year = _validate_optional_int(
        "savings_breakdown params.year must be an integer", params.get("year")
    )
    month = _validate_optional_int(
        "savings_breakdown params.month must be an integer", params.get("month")
    )
    with session_scope(sessions) as session:
        return savings_breakdown(session, year=year, month=month)


def _handle_dashboard_cards(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    started_at = time.monotonic()
    year = _validate_int("dashboard_cards requires integer params.year", params.get("year"))
    month = _validate_optional_int(
        "dashboard_cards params.month must be an integer", params.get("month")
    )
    with session_scope(sessions) as session:
        result = dashboard_totals(session, year=year, month=month)
    result["query_duration_ms"] = int((time.monotonic() - started_at) * 1000)
    return result


def _handle_dashboard_trends(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    started_at = time.monotonic()
    year = _validate_int("dashboard_trends requires integer params.year", params.get("year"))
    months_back = _validate_optional_int(
        "dashboard_trends params.months_back must be an integer", params.get("months_back")
    )
    end_month = _validate_optional_int(
        "dashboard_trends params.end_month must be an integer", params.get("end_month")
    )
    with session_scope(sessions) as session:
        result = dashboard_trends(
            session,
            year=year,
            months_back=months_back if months_back is not None else 6,
            end_month=end_month if end_month is not None else 12,
        )
    result["query_duration_ms"] = int((time.monotonic() - started_at) * 1000)
    return result


def _handle_dashboard_savings_breakdown(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    started_at = time.monotonic()
    year = _validate_int(
        "dashboard_savings_breakdown requires integer params.year", params.get("year")
    )
    month = _validate_optional_int(
        "dashboard_savings_breakdown params.month must be an integer", params.get("month")
    )
    view = _validate_optional_str(
        "dashboard_savings_breakdown params.view must be a string", params.get("view")
    )
    with session_scope(sessions) as session:
        result = dashboard_savings_breakdown(
            session,
            year=year,
            month=month,
            view=view or "native",
        )
    result["query_duration_ms"] = int((time.monotonic() - started_at) * 1000)
    return result


def _handle_dashboard_retailer_composition(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    started_at = time.monotonic()
    year = _validate_int(
        "dashboard_retailer_composition requires integer params.year", params.get("year")
    )
    month = _validate_optional_int(
        "dashboard_retailer_composition params.month must be an integer", params.get("month")
    )
    with session_scope(sessions) as session:
        result = dashboard_retailer_composition(session, year=year, month=month)
    result["query_duration_ms"] = int((time.monotonic() - started_at) * 1000)
    return result


def _handle_search_transactions(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    query = _validate_optional_str(
        "search_transactions params.query must be a string", params.get("query")
    )
    year = _validate_optional_int(
        "search_transactions params.year must be an integer", params.get("year")
    )
    month = _validate_optional_int(
        "search_transactions params.month must be an integer", params.get("month")
    )
    limit = params.get("limit", 50)
    offset = params.get("offset", 0)
    if not isinstance(limit, int):
        raise ActionValidationError("search_transactions params.limit must be an integer")
    if not isinstance(offset, int):
        raise ActionValidationError("search_transactions params.offset must be an integer")
    clamped_limit = min(max(limit, 1), 200)
    clamped_offset = max(offset, 0)
    with session_scope(sessions) as session:
        return search_transactions(
            session,
            query=query,
            year=year,
            month=month,
            limit=clamped_limit,
            offset=clamped_offset,
        )


def _handle_export(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    export_format = str(params.get("format", "json"))
    if export_format != "json":
        raise ActionValidationError("Only json export is supported")
    with session_scope(sessions) as session:
        export_result = export_receipts(session)

    out_path = params.get("out")
    if isinstance(out_path, str) and out_path:
        target = Path(out_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(export_result, indent=2, default=str), encoding="utf-8")
        return {"out": str(target), "records": len(export_result)}
    return {"records": len(export_result), "data": export_result}


def _handle_endpoint_reliability_dashboard(
    _: AppConfig, sessions: sessionmaker[Session], params: dict[str, Any]
) -> dict[str, Any]:
    window_hours = _validate_optional_int(
        "endpoint_reliability_dashboard params.window_hours must be an integer",
        params.get("window_hours"),
    )
    sync_target = _validate_optional_int(
        "endpoint_reliability_dashboard params.sync_p95_target_ms must be an integer",
        params.get("sync_p95_target_ms"),
    )
    analytics_target = _validate_optional_int(
        "endpoint_reliability_dashboard params.analytics_p95_target_ms must be an integer",
        params.get("analytics_p95_target_ms"),
    )
    min_success_rate_param = params.get("min_success_rate")
    if min_success_rate_param is not None and not isinstance(min_success_rate_param, (int, float)):
        raise ActionValidationError(
            "endpoint_reliability_dashboard params.min_success_rate must be numeric"
        )
    min_success_rate = float(min_success_rate_param) if min_success_rate_param is not None else 0.97

    with session_scope(sessions) as session:
        return compute_endpoint_slo_summary(
            session,
            window_hours=window_hours or 24,
            sync_p95_target_ms=sync_target or 2500,
            analytics_p95_target_ms=analytics_target or 2000,
            min_success_rate=min_success_rate,
        ).as_dict()


ACTION_HANDLERS: dict[str, Any] = {
    "health": _handle_health,
    "sync": _handle_sync,
    "manual_ingest": _handle_manual_ingest,
    "sync_status": _handle_sync_status,
    "sources_list": _handle_sources_list,
    "source_status": _handle_source_status,
    "source_auth_status": _handle_source_auth_status,
    "source_auth_reauth_start": _handle_source_auth_reauth_start,
    "source_auth_reauth_confirm": _handle_source_auth_reauth_confirm,
    "connector_health_dashboard": _handle_connector_health_dashboard,
    "connector_cost_performance_review": _handle_connector_cost_performance_review,
    "stats_month": _handle_stats_month,
    "savings_breakdown": _handle_savings_breakdown,
    "dashboard_cards": _handle_dashboard_cards,
    "dashboard_trends": _handle_dashboard_trends,
    "dashboard_savings_breakdown": _handle_dashboard_savings_breakdown,
    "dashboard_retailer_composition": _handle_dashboard_retailer_composition,
    "search_transactions": _handle_search_transactions,
    "endpoint_reliability_dashboard": _handle_endpoint_reliability_dashboard,
    "export": _handle_export,
}

if set(ACTION_POLICY) != set(ACTION_HANDLERS):
    LOGGER.warning(
        "openclaw.action.policy_registry_mismatch missing_policy=%s missing_handler=%s",
        sorted(set(ACTION_HANDLERS) - set(ACTION_POLICY)),
        sorted(set(ACTION_POLICY) - set(ACTION_HANDLERS)),
    )


def handle_request(payload: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    action = payload.get("action")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return _response(
            False, result=None, warnings=warnings, error="params must be a JSON object"
        )
    if not isinstance(action, str) or not action:
        return _response(
            False, result=None, warnings=warnings, error="action must be a non-empty string"
        )
    if action not in ACTION_HANDLERS:
        _metric_inc("openclaw.action.unsupported")
        return _response(
            False, result=None, warnings=warnings, error=f"unsupported action: {action}"
        )

    try:
        config, sessions = _session_factory_from_params(params)
        warnings.extend(_apply_auth_guard(config=config, params=params, action=action))
        retry_after_s = _check_rate_limit(config=config, action=action, params=params)
        if retry_after_s is not None:
            LOGGER.warning(
                "openclaw.rate_limit.denied action=%s retry_after_s=%s", action, retry_after_s
            )
            _metric_inc("openclaw.rate_limit.denied")
            return _response(
                False,
                result=None,
                warnings=warnings,
                error=f"rate limit exceeded; retry_after_s={retry_after_s}",
            )
        _enforce_action_scopes(config=config, action=action, params=params)
        _metric_inc("openclaw.action.calls")
        LOGGER.info("openclaw.action.called action=%s", action)
        result = ACTION_HANDLERS[action](config, sessions, params)
        return _response(True, result=result, warnings=warnings, error=None)
    except ActionValidationError as exc:
        LOGGER.warning("openclaw.action.validation_error action=%s error=%s", action, exc)
        _metric_inc("openclaw.action.validation_error")
        return _response(False, result=None, warnings=warnings, error=str(exc))
    except ActionRuntimeFailureError as exc:
        LOGGER.error("openclaw.action.runtime_error action=%s error=%s", action, exc)
        _metric_inc("openclaw.action.runtime_error")
        return _response(False, result=None, warnings=warnings, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("openclaw.action.unhandled_error action=%s", action)
        _metric_inc("openclaw.action.unhandled_error")
        return _response(False, result=None, warnings=warnings, error=str(exc))


def main() -> None:
    try:
        request = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        sys.stdout.write(json.dumps(_response(False, error="invalid JSON request")))
        return

    if not isinstance(request, dict):
        sys.stdout.write(json.dumps(_response(False, error="request body must be a JSON object")))
        return

    try:
        response = handle_request(request)
    except Exception as exc:  # noqa: BLE001
        response = _response(False, error=str(exc))

    sys.stdout.write(json.dumps(response, default=str))


if __name__ == "__main__":
    main()
