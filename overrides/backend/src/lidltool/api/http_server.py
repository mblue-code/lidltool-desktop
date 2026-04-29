from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4

import httpx
import uvicorn
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, sessionmaker
from sqlalchemy.sql.elements import ColumnElement, SQLColumnExpression
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import HTTPConnection
from starlette.types import Scope

from lidltool.ai.clustering import cluster_products_with_llm, get_cluster_job_progress
from lidltool.api import route_auth as route_auth_module
from lidltool.ai.config import (
    get_ai_api_key,
    get_ai_oauth_access_token,
    get_item_categorizer_api_key,
    persist_ai_settings,
    persist_item_categorizer_settings,
    persist_ocr_settings,
    set_ai_api_key,
    set_ai_oauth_access_token,
    set_ai_oauth_refresh_token,
    set_item_categorizer_api_key,
)
from lidltool.analytics.advanced import (
    basket_compare,
    budget_utilization,
    create_budget_rule,
    deposit_analytics,
    hour_heatmap,
    list_budget_rules,
    patterns_summary,
    retailer_price_index,
    timing_matrix,
    weekday_heatmap,
)
from lidltool.analytics.item_categorizer import resolve_item_categorizer_runtime_client
from lidltool.analytics.recategorization import recategorize_transactions
from lidltool.analytics.queries import (
    dashboard_available_years,
    dashboard_category_spend_summary,
    display_merchant_name,
    dashboard_merchant_summary,
    dashboard_retailer_composition,
    dashboard_savings_breakdown,
    dashboard_totals,
    dashboard_trends,
    export_receipts,
    dashboard_window_totals,
    dashboard_window_transactions,
    grocery_workspace_summary,
    merchant_workspace_summary,
    review_queue,
    review_queue_detail,
    search_transactions,
    transaction_detail,
)
from lidltool.analytics.query_dsl import parse_dsl_to_query
from lidltool.analytics.scope import VisibilityContext, parse_scope, visible_transaction_ids_subquery
from lidltool.analytics.workbench import (
    add_comparison_group_member,
    comparison_group_series,
    create_comparison_group,
    create_product,
    create_saved_query,
    delete_saved_query,
    get_product_detail,
    get_saved_query,
    list_comparison_groups,
    list_product_categories,
    list_saved_queries,
    list_sources,
    low_confidence_ocr_quality,
    manual_product_match,
    merge_products,
    product_price_series,
    product_purchases,
    run_workbench_query,
    search_products,
    seed_products_from_items,
    unmatched_items_quality,
)
from lidltool.api.auth import (
    SESSION_COOKIE_NAME,
    AuthenticatedSessionContext,
    clear_session_cookie,
    get_current_auth_context,
    get_current_user,
    is_loopback_request,
    is_session_transport,
    issue_session_token,
    set_session_cookie,
)
from lidltool.api.http_state import (
    ConnectorCascadeSession,
    ConnectorCascadeSourceState,
    QualityRecategorizeJobState,
    VncRuntime,
    get_ai_oauth_lock,
    get_automation_scheduler,
    get_build,
    get_connector_auth_registry,
    get_connector_cascade_lock,
    get_connector_cascade_sessions,
    get_connector_command_sessions,
    get_http_rate_limit_buckets,
    get_http_rate_limit_lock,
    get_quality_recategorize_jobs,
    get_quality_recategorize_lock,
    get_started_at,
    get_vnc_runtime,
    initialize_http_api_state,
    set_vnc_runtime,
)
from lidltool.api.http_state import (
    get_ai_oauth_state as get_http_ai_oauth_state,
)
from lidltool.api.http_state import (
    set_ai_oauth_state as set_http_ai_oauth_state,
)
from lidltool.api.openai_payloads import (
    simple_text_message,
    stream_options_with_usage,
)
from lidltool.api.openai_payloads import (
    to_openai_messages as _to_openai_messages,
)
from lidltool.api.openai_payloads import (
    to_openai_tools as _to_openai_tools,
)
from lidltool.api.route_auth import (
    HTTP_ROUTE_AUTH_BY_KEY,
    RouteAuthPolicy,
    assert_route_auth_policy,
)
from lidltool.api.source_models import (
    build_source_status_payload as _source_status_payload,
)
from lidltool.api.source_models import (
    serialize_connector_bootstrap_payload as _serialize_connector_bootstrap,
)
from lidltool.api.source_models import (
    serialize_source_auth_status,
)
from lidltool.api.source_models import (
    serialize_source_sync_status as _serialize_source_sync_status,
)
from lidltool.auth.agent_keys import create_user_agent_key
from lidltool.auth.sessions import (
    SESSION_MODE_BOTH,
    SESSION_MODE_COOKIE,
    SESSION_MODE_TOKEN,
    SessionClientMetadata,
    available_auth_transports,
    create_user_session,
    list_active_user_sessions,
    revoke_user_session,
    revoke_user_sessions_for_user,
    serialize_user_session,
)
from lidltool.auth.user_auth import verify_password
from lidltool.auth.users import (
    SERVICE_USERNAME,
    create_local_user,
    ensure_service_user,
    get_user_by_username,
    human_user_count,
    set_user_password,
)
from lidltool.budget.service import (
    create_cashflow_entry,
    delete_cashflow_entry,
    get_budget_month,
    list_cashflow_entries,
    monthly_budget_summary,
    update_cashflow_entry,
    upsert_budget_month,
)
from lidltool.automations.scheduler import AutomationScheduler
from lidltool.automations.service import AutomationService
from lidltool.config import (
    AppConfig,
    build_config,
    database_url,
    default_config_file,
    validate_config,
)
from lidltool.connectors.auth.auth_orchestration import (
    ConnectorAuthOrchestrationService,
    ConnectorAuthSessionRegistry,
    ConnectorBootstrapSession,
    any_connector_bootstrap_running,
    connector_bootstrap_is_running,
    start_connector_command_session,
    terminate_connector_bootstrap,
)
from lidltool.connectors.discovery import connector_discovery_payload
from lidltool.connectors.lifecycle import (
    assert_connector_operation_allowed,
    connector_lifecycle_record_payload,
    install_connector,
    set_connector_enabled,
    uninstall_connector,
    update_connector_config,
)
from lidltool.connectors.management import plugin_management_payload
from lidltool.connectors.release_policy import release_policy_payload
from lidltool.connectors.registry import get_connector_registry
from lidltool.connectors.runtime.execution import ConnectorExecutionService
from lidltool.db.audit import list_transaction_history
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import (
    CashflowEntry,
    ChatMessage,
    ChatRun,
    ChatThread,
    Document,
    Goal,
    IngestionJob,
    Notification,
    MobileCapture,
    MobilePairedDevice,
    RecurringBill,
    RecurringBillMatch,
    RecurringBillOccurrence,
    Source,
    Transaction,
    TransactionItem,
    User,
    UserApiKey,
    UserSession,
)
from lidltool.deployment_policy import (
    HttpExposureMode,
    evaluate_deployment_policy,
    resolve_bind_host,
)
from lidltool.ingest.corrections import CorrectionService
from lidltool.ingest.jobs import InvalidJobTransitionError, JobService
from lidltool.ingest.manual_ingest import (
    MANUAL_SOURCE_ID,
    ManualDiscountInput,
    ManualIngestService,
    ManualItemInput,
    ManualTransactionInput,
)
from lidltool.ingest.ocr_source import OCR_SOURCE_ID, ensure_ocr_source
from lidltool.ingest.overrides import OverrideService
from lidltool.ops import backup_database
from lidltool.mobile import (
    delete_mobile_device,
    delete_mobile_devices_for_session,
    list_mobile_devices,
    upsert_mobile_device,
)
from lidltool.mobile.pairing import (
    DEFAULT_PAIRING_EXPIRES_IN_SECONDS,
    DEFAULT_TRANSPORT as MOBILE_DEFAULT_TRANSPORT,
    MAX_PAIRING_EXPIRES_IN_SECONDS,
    MIN_PAIRING_EXPIRES_IN_SECONDS,
    PROTOCOL_VERSION as MOBILE_PROTOCOL_VERSION,
    complete_pairing_handshake,
    create_pairing_session,
    require_paired_device,
)
from lidltool.offers.service import (
    create_offer_source,
    create_watchlist as create_offer_watchlist,
)
from lidltool.offers.service import (
    delete_offer_source,
    delete_watchlist as delete_offer_watchlist,
)
from lidltool.offers.service import (
    list_alerts as list_offer_alerts,
)
from lidltool.offers.service import (
    list_matches as list_offer_matches,
    list_merchant_items as list_offer_merchant_items,
)
from lidltool.offers.service import (
    list_offer_sources,
    offer_overview,
    run_offer_refresh,
)
from lidltool.offers.service import (
    list_refresh_runs as list_offer_refresh_runs,
)
from lidltool.offers.service import (
    list_watchlists as list_offer_watchlists,
)
from lidltool.offers.service import (
    mark_alert_read as mark_offer_alert_read,
)
from lidltool.offers.service import (
    update_offer_source,
    update_watchlist as update_offer_watchlist,
)
from lidltool.goals.service import create_goal, delete_goal, goals_summary, list_goals, update_goal
from lidltool.notifications.service import (
    list_notifications,
    mark_all_notifications_read,
    update_notification,
)
from lidltool.recurring.service import RecurringBillsService
from lidltool.reliability.metrics import compute_endpoint_slo_summary, record_endpoint_metric
from lidltool.reports.service import build_report_templates
from lidltool.shared_groups import (
    add_shared_group_member,
    create_shared_group,
    get_shared_group_detail,
    list_shared_group_user_directory,
    list_shared_groups,
    remove_shared_group_member,
    update_shared_group,
    update_shared_group_member,
)
from lidltool.shared_groups.ownership import (
    assign_owner,
    ownership_filter,
    resource_belongs_to_workspace,
)
from lidltool.storage.document_storage import DocumentStorage, DocumentStorageError

LOGGER = logging.getLogger(__name__)
SUPPORTED_LOCALES = {"en", "de"}


@dataclass(frozen=True, slots=True)
class ApiWarningDetail:
    message: str
    code: str | None = None


def _normalize_supported_locale(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in SUPPORTED_LOCALES:
        return normalized
    return None


def _warning(message: str, *, code: str | None = None) -> ApiWarningDetail:
    return ApiWarningDetail(message=message, code=code)


def _serialize_current_user(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "preferred_locale": _normalize_supported_locale(user.preferred_locale),
    }


def _request_client_ip(request: Request) -> str | None:
    if request.client is None or not request.client.host:
        return None
    return request.client.host


def _request_auth_context(
    *,
    request: Request,
    session: Session,
    config: AppConfig,
    required: bool = True,
) -> AuthenticatedSessionContext | None:
    return get_current_auth_context(
        request=request,
        session=session,
        config=config,
        required=required,
    )


def _request_session_record(
    *,
    request: Request,
    session: Session,
    config: AppConfig,
) -> UserSession | None:
    context = _request_auth_context(
        request=request,
        session=session,
        config=config,
        required=False,
    )
    if context is None:
        return None
    return context.session_record


def _session_client_metadata(
    *,
    request: Request,
    session_mode: str,
    device_label: str | None,
    client_name: str | None,
    client_platform: str | None,
) -> SessionClientMetadata:
    return SessionClientMetadata(
        auth_transport=session_mode,
        device_label=device_label,
        client_name=client_name,
        client_platform=client_platform,
        user_agent=request.headers.get("user-agent"),
        ip_address=_request_client_ip(request),
    )


def _session_token_payload(*, token: str, expires_at: datetime) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    expires_in_seconds = max(int((expires_at - now).total_seconds()), 0)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": expires_in_seconds,
    }


def _auth_success_result(
    *,
    user: User,
    session_record: UserSession,
    token: str | None,
) -> dict[str, Any]:
    result = _serialize_current_user(user)
    result["session"] = serialize_user_session(session_record, current=True)
    result["session_mode"] = session_record.auth_transport
    result["available_auth_transports"] = available_auth_transports(session_record.auth_transport)
    result["auth_transport"] = (
        "bearer" if token is not None else "cookie"
    )
    result["token"] = (
        _session_token_payload(token=token, expires_at=session_record.expires_at)
        if token is not None
        else None
    )
    return result


def _collection_result(
    *,
    result: dict[str, Any],
    items_key: str = "items",
    alias_key: str,
) -> dict[str, Any]:
    items = result.get(items_key)
    if isinstance(items, list):
        result[alias_key] = items
    pagination = {
        "count": int(result.get("count", len(items) if isinstance(items, list) else 0) or 0),
        "total": int(result.get("total", result.get("count", 0)) or 0),
    }
    if "limit" in result:
        pagination["limit"] = int(result.get("limit", 0) or 0)
    if "offset" in result:
        pagination["offset"] = int(result.get("offset", 0) or 0)
    result["pagination"] = pagination
    return result


def _serialize_warning_details(
    warnings: list[str | ApiWarningDetail] | None,
) -> tuple[list[str], list[dict[str, str | None]]]:
    messages: list[str] = []
    details: list[dict[str, str | None]] = []
    for warning in warnings or []:
        if isinstance(warning, ApiWarningDetail):
            messages.append(warning.message)
            details.append({"message": warning.message, "code": warning.code})
            continue
        messages.append(str(warning))
    return messages, details


def _response(
    ok: bool,
    result: Any = None,
    warnings: list[str | ApiWarningDetail] | None = None,
    error: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    warning_messages, warning_details = _serialize_warning_details(warnings)
    return {
        "ok": ok,
        "result": result,
        "warnings": warning_messages,
        "warning_details": warning_details,
        "error": error,
        "error_code": error_code,
    }


def _create_session_factory(
    config: AppConfig,
) -> tuple[AppConfig, sessionmaker[Session]]:
    db_url = database_url(config)
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    return config, session_factory(engine)


@dataclass(slots=True)
class RequestContext:
    config: AppConfig
    sessions: sessionmaker[Session]
    config_path: Path
    bind_host: str


def _resolved_runtime_config_path(
    *,
    config: AppConfig,
    config_path: Path | None,
) -> Path:
    if config_path is not None:
        return config_path.expanduser().resolve()
    configured_path = os.getenv("LIDLTOOL_CONFIG")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return default_config_file(config.config_dir)


def _build_runtime_context(
    *,
    config: AppConfig | None = None,
    config_path: Path | None = None,
    db_override: Path | None = None,
    bind_host: str | None = None,
) -> RequestContext:
    if config is None:
        app_config = build_config(config_path=config_path, db_override=db_override)
    elif db_override is not None:
        app_config = config.model_copy(update={"db_path": db_override})
    else:
        app_config = config
    resolved_config_path = _resolved_runtime_config_path(
        config=app_config,
        config_path=config_path,
    )
    resolved_bind_host = resolve_bind_host(bind_host)
    app_config, sessions = _create_session_factory(app_config)
    return RequestContext(
        config=app_config,
        sessions=sessions,
        config_path=resolved_config_path,
        bind_host=resolved_bind_host,
    )


class SPAStaticFiles(StaticFiles):
    """Serve built frontend assets and fall back to index.html for SPA routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise

        request_path = str(scope.get("path", ""))
        method = str(scope.get("method", "")).upper()
        if method not in {"GET", "HEAD"}:
            raise StarletteHTTPException(status_code=404)
        if request_path.startswith("/api/") or request_path.startswith("/vnc/"):
            raise StarletteHTTPException(status_code=404)
        if "." in Path(path).name:
            raise StarletteHTTPException(status_code=404)
        return await super().get_response("index.html", scope)


def _parse_source_ids(source_ids: str | None) -> list[str] | None:
    if source_ids is None:
        return None
    values = [value.strip() for value in source_ids.split(",")]
    filtered = [value for value in values if value]
    return filtered or None


def _resolve_request_context(
    request: HTTPConnection,
) -> RequestContext:
    cached = getattr(request.state, "request_context", None)
    if isinstance(cached, RequestContext):
        return cached
    context = getattr(request.app.state, "request_context", None)
    if not isinstance(context, RequestContext):
        raise RuntimeError("http runtime context not initialized")
    request.state.request_context = context
    return context


def _reload_request_context_config(context: RequestContext) -> AppConfig:
    refreshed = build_config(
        config_path=context.config_path,
        db_override=context.config.db_path,
    )
    context.config = refreshed
    return refreshed


def _disallowed_runtime_override_fields(connection: HTTPConnection) -> list[str]:
    return [
        field_name
        for field_name in ("db", "config")
        if connection.query_params.get(field_name)
    ]


async def _reject_runtime_override_usage(request: Request) -> JSONResponse | None:
    fields = _disallowed_runtime_override_fields(request)
    if not fields:
        return None
    joined = ", ".join(sorted(fields))
    return JSONResponse(
        status_code=400,
        content=_response(
            False,
            result=None,
            warnings=[],
            error=f"request runtime override(s) are not supported: {joined}",
            error_code="request_runtime_override_not_supported",
        ),
    )


async def _reject_form_runtime_override_usage(request: Request) -> None:
    content_type = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" not in content_type and "application/x-www-form-urlencoded" not in content_type:
        return
    form = await request.form()
    disallowed = [field_name for field_name in ("db", "config") if field_name in form]
    if not disallowed:
        return
    joined = ", ".join(sorted(disallowed))
    raise HTTPException(
        status_code=400,
        detail=f"request runtime override(s) are not supported: {joined}",
    )


def _header_api_key(request: Request) -> str | None:
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        return x_api_key.strip()
    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
        return bearer or None
    return None


def _apply_auth_guard(config: AppConfig, *, request: Request) -> list[str | ApiWarningDetail]:
    warnings: list[str | ApiWarningDetail] = []
    expected_api_key = config.openclaw_api_key
    if not expected_api_key:
        return warnings
    if _header_api_key(request) == expected_api_key:
        return warnings
    mode = str(config.openclaw_auth_mode or "enforce").lower()
    if mode == "enforce":
        raise RuntimeError("unauthorized request")
    warnings.append(
        _warning(
            "api auth credential missing or invalid",
            code="api_auth_credential_missing_or_invalid",
        )
    )
    return warnings


def _integrity_error_mapping(exc: IntegrityError) -> tuple[int, str]:
    detail = str(getattr(exc, "orig", exc)).lower()
    if "unique constraint" in detail:
        return 409, "resource conflict"
    if "foreign key constraint" in detail:
        return 400, "invalid related resource reference"
    if "not null constraint" in detail:
        return 400, "missing required field"
    if "check constraint" in detail:
        return 400, "invalid field value"
    return 409, "data integrity conflict"


def _status_code_for_exception(exc: Exception) -> int:
    if isinstance(exc, HTTPException):
        return int(exc.status_code)
    if isinstance(exc, IntegrityError):
        status_code, _ = _integrity_error_mapping(exc)
        return status_code
    if isinstance(exc, (RequestValidationError, ValueError, json.JSONDecodeError)):
        return 400
    if isinstance(exc, InvalidJobTransitionError):
        return 409
    if isinstance(exc, DocumentStorageError):
        return 400
    if isinstance(exc, RuntimeError):
        message = str(exc).lower()
        if "setup required" in message:
            return 503
        if "mobile sync token" in message:
            return 401
        if "already running" in message:
            return 409
        if "unauthorized" in message:
            return 401
        if "forbidden" in message:
            return 403
        if "not found" in message:
            return 404
        if "transition" in message or "conflict" in message:
            return 409
        if (
            "cannot" in message
            or "required" in message
            or "must be" in message
            or "invalid" in message
            or "unsupported" in message
            or "requires" in message
            or "missing" in message
            or "too large" in message
        ):
            return 400
    return 500


def _assert_route_auth_matrix_complete(app: FastAPI) -> None:
    assert_route_auth_policy(app)


def _register_runtime_route_auth_policy(policy: RouteAuthPolicy) -> None:
    key = (policy.method, policy.path)
    if key in HTTP_ROUTE_AUTH_BY_KEY:
        return
    route_auth_module.HTTP_ROUTE_AUTH_MATRIX = (*route_auth_module.HTTP_ROUTE_AUTH_MATRIX, policy)
    route_auth_module.HTTP_ROUTE_AUTH_BY_KEY[key] = policy


def _assert_route_auth_category(request: HTTPConnection, *allowed_categories: str) -> RouteAuthPolicy:
    policy = _route_auth_policy_for(request)
    if policy.category not in allowed_categories:
        allowed = ", ".join(sorted(allowed_categories))
        raise RuntimeError(
            "route auth policy mismatch: "
            f"{policy.method} {policy.path} is classified as {policy.category!r}, "
            f"but this handler requires one of: {allowed}"
        )
    return policy


def _route_auth_policy_for(request: HTTPConnection) -> RouteAuthPolicy:
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    method = "WEBSOCKET" if isinstance(request, WebSocket) else request.method.upper()
    try:
        return HTTP_ROUTE_AUTH_BY_KEY[(method, str(path))]
    except KeyError as exc:
        raise RuntimeError(f"missing route auth policy for {method} {path}") from exc


def _error_code_from_message(message: str | None, *, status_code: int) -> str | None:
    normalized = (message or "").strip().lower()
    if not normalized:
        return None

    exact_codes = {
        "admin privileges required": "admin_privileges_required",
        "api key not found": "api_key_not_found",
        "authentication required": "auth_required",
        "at least one admin user is required": "admin_user_required",
        "cannot delete current user": "cannot_delete_current_user",
        "cannot remove admin privileges from current user": "cannot_demote_current_user",
        "chat thread conflict": "chat_thread_conflict",
        "chat thread not found": "chat_thread_not_found",
        "data integrity conflict": "data_integrity_conflict",
        "document not found": "document_not_found",
        "internal server error": "internal_server_error",
        "initial bootstrap requires a loopback request or configured bootstrap token": "bootstrap_loopback_or_token_required",
        "invalid bootstrap token": "invalid_bootstrap_token",
        "invalid field value": "invalid_field_value",
        "invalid json payload": "invalid_json_payload",
        "invalid or expired session token": "invalid_or_expired_session_token",
        "invalid or expired pairing token": "invalid_or_expired_pairing_token",
        "invalid mobile sync token": "invalid_mobile_sync_token",
        "invalid related resource reference": "invalid_related_resource_reference",
        "invalid request payload": "invalid_request_payload",
        "invalid source; register source before upload": "invalid_source_for_upload",
        "invalid username or password": "auth_invalid_credentials",
        "message content is required": "message_content_required",
        "missing required field": "missing_required_field",
        "missing retryable sources; no failed or remaining sources to retry": "connector_retryable_sources_missing",
        "missing token signing secret": "missing_token_signing_secret",
        "mobile sync token required": "mobile_sync_token_required",
        "rate limit exceeded; retry after retry-after seconds": "rate_limited",
        "resource conflict": "resource_conflict",
        "request runtime override(s) are not supported: config": "request_runtime_override_not_supported",
        "request runtime override(s) are not supported: db": "request_runtime_override_not_supported",
        "request runtime override(s) are not supported: config, db": "request_runtime_override_not_supported",
        "request runtime override(s) are not supported: db, config": "request_runtime_override_not_supported",
        "service not ready": "service_not_ready",
        "session expired": "session_expired",
        "session not found": "session_not_found",
        "session revoked": "session_revoked",
        "session user not found": "session_user_not_found",
        "session_mode must be one of: cookie, token, both": "invalid_session_mode",
        "setup required": "setup_required",
        "setup already completed": "setup_already_completed",
        "source not found": "source_not_found",
        "thread is already generating": "chat_thread_already_generating",
        "transaction item not found": "transaction_item_not_found",
        "transaction not found": "transaction_not_found",
        "unauthorized request": "unauthorized_request",
        "user not found": "user_not_found",
    }
    exact = exact_codes.get(normalized)
    if exact is not None:
        return exact

    if normalized.startswith("rate limit exceeded; retry after"):
        return "rate_limited"
    if normalized.startswith("unsupported source(s) for cascade:"):
        return "connector_unsupported_sources"
    return None


def _error_code(exc: Exception) -> str | None:
    status_code = _status_code_for_exception(exc)
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _error_code_from_message(detail, status_code=status_code)
    if isinstance(exc, RequestValidationError):
        return "invalid_request_payload"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json_payload"
    if isinstance(exc, IntegrityError):
        _, message = _integrity_error_mapping(exc)
        return _error_code_from_message(message, status_code=status_code)
    if status_code >= 500:
        return "internal_server_error"
    return _error_code_from_message(str(exc), status_code=status_code)


def _error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            return detail
        return str(detail)
    if isinstance(exc, RequestValidationError):
        return "invalid request payload"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid JSON payload"
    if isinstance(exc, IntegrityError):
        _, message = _integrity_error_mapping(exc)
        return message
    if _status_code_for_exception(exc) >= 500:
        return "internal server error"
    return str(exc)


def _error_response(exc: Exception) -> JSONResponse:
    status_code = _status_code_for_exception(exc)
    error_code = _error_code(exc)
    if isinstance(exc, IntegrityError):
        LOGGER.warning("api.integrity_error status=%s", status_code, exc_info=exc)
    elif status_code >= 500:
        LOGGER.exception("api.unhandled_error status=%s", status_code)
    return JSONResponse(
        status_code=status_code,
        content=_response(
            False,
            result=None,
            warnings=[],
            error=_error_message(exc),
            error_code=error_code,
        ),
    )


async def _reject_legacy_api_key_usage(request: Request) -> JSONResponse | None:
    if "api_key" in request.query_params:
        return _error_response(
            RuntimeError("api_key query parameter is unsupported; use X-API-Key header")
        )
    return None


def _reject_legacy_form_api_key(form_value: str | None) -> None:
    if form_value is not None:
        raise RuntimeError("api_key form field is unsupported; use X-API-Key header")


@dataclass(slots=True)
class RateLimitState:
    family: str
    limit: int
    remaining: int
    reset_after_s: int
    retry_after_s: int | None
    throttled: bool


def _rate_limit_exempt(path: str) -> bool:
    return path in {"/api/v1/health", "/api/v1/ready"}


def _route_family(path: str, method: str) -> str:
    if path.startswith("/api/v1/documents/upload"):
        return "expensive"
    if path.startswith("/api/v1/documents/") and path.endswith("/process"):
        return "expensive"
    if path.startswith("/api/v1/review-queue/") and method in {"PATCH", "POST"}:
        return "expensive"
    if path.startswith("/api/v1/automations/") and path.endswith("/run"):
        return "expensive"
    if method in {"POST", "PATCH", "DELETE"}:
        return "write"
    return "read"


def _rate_limit_for_family(config: AppConfig, family: str) -> int:
    if family == "expensive":
        return max(int(config.http_rate_limit_expensive_requests), 1)
    if family == "write":
        return max(int(config.http_rate_limit_write_requests), 1)
    return max(int(config.http_rate_limit_read_requests), 1)


def _rate_limit_principal(request: Request) -> str:
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        digest = hashlib.sha256(x_api_key.strip().encode("utf-8")).hexdigest()[:16]
        return f"api_key:{digest}"
    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
        if bearer:
            family = "session" if bearer.count(".") == 2 else "api_key"
            digest = hashlib.sha256(bearer.encode("utf-8")).hexdigest()[:16]
            return f"{family}:{digest}"
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        digest = hashlib.sha256(session_token.encode("utf-8")).hexdigest()[:16]
        return f"session:{digest}"
    if request.client is not None and request.client.host:
        return f"ip:{request.client.host}"
    return "ip:unknown"


def _rate_limit_headers(limit_state: RateLimitState, window_s: int) -> dict[str, str]:
    headers = {
        "X-RateLimit-Limit": str(limit_state.limit),
        "X-RateLimit-Remaining": str(limit_state.remaining),
        "X-RateLimit-Reset": str(limit_state.reset_after_s),
        "X-RateLimit-Policy": f"family={limit_state.family};window={window_s};limit={limit_state.limit}",
    }
    if limit_state.retry_after_s is not None:
        headers["Retry-After"] = str(limit_state.retry_after_s)
    return headers


def _evaluate_rate_limit(request: Request, config: AppConfig) -> RateLimitState | None:
    if not config.http_rate_limit_enabled:
        return None
    path = request.url.path
    if _rate_limit_exempt(path):
        return None
    family = _route_family(path, request.method.upper())
    window_s = max(int(config.http_rate_limit_window_s), 1)
    limit = _rate_limit_for_family(config, family=family)
    principal = _rate_limit_principal(request)
    key = f"{principal}|{family}"
    buckets = get_http_rate_limit_buckets(request.app)
    lock = get_http_rate_limit_lock(request.app)
    now = time.monotonic()
    window_start = now - window_s
    with lock:
        bucket = [stamp for stamp in buckets.get(key, []) if stamp >= window_start]
        buckets[key] = bucket
        if len(bucket) >= limit:
            retry_after_s = max(int(window_s - (now - bucket[0])), 1)
            return RateLimitState(
                family=family,
                limit=limit,
                remaining=0,
                reset_after_s=retry_after_s,
                retry_after_s=retry_after_s,
                throttled=True,
            )
        bucket.append(now)
        buckets[key] = bucket
        remaining = max(limit - len(bucket), 0)
        reset_after_s = max(int(window_s - (now - bucket[0])), 0)
        return RateLimitState(
            family=family,
            limit=limit,
            remaining=remaining,
            reset_after_s=reset_after_s,
            retry_after_s=None,
            throttled=False,
        )


def _validate_upload_source(session: Session, source: str | None) -> str | None:
    if source is None:
        return None
    normalized_source = source.strip()
    if not normalized_source:
        raise RuntimeError("source must be a non-empty string")
    if session.get(Source, normalized_source) is None:
        raise RuntimeError("invalid source; register source before upload")
    return normalized_source


def _resolve_request_user(
    *,
    request: Request,
    session: Session,
    config: AppConfig,
    required: bool = True,
) -> User:
    _assert_route_auth_category(request, "authenticated_principal")
    resolved = get_current_user(request=request, session=session, config=config, required=False)
    if resolved is not None:
        return resolved
    if human_user_count(session) == 0:
        raise HTTPException(status_code=503, detail="setup required")
    if required:
        raise HTTPException(status_code=401, detail="authentication required")
    return ensure_service_user(session)


def _require_admin_auth_context(
    *,
    request: Request,
    session: Session,
    config: AppConfig,
) -> AuthenticatedSessionContext:
    _assert_route_auth_category(request, "admin_only")
    auth_context = _request_auth_context(
        request=request,
        session=session,
        config=config,
        required=True,
    )
    if auth_context is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if not auth_context.user.is_admin:
        raise HTTPException(status_code=403, detail="admin privileges required")
    return auth_context


def _require_user_session_auth_context(
    *,
    request: Request,
    session: Session,
    config: AppConfig,
    admin_required: bool = False,
) -> AuthenticatedSessionContext:
    _assert_route_auth_category(
        request,
        "admin_only" if admin_required else "authenticated_user_session",
    )
    auth_context = _request_auth_context(
        request=request,
        session=session,
        config=config,
        required=True,
    )
    if auth_context is None or not is_session_transport(auth_context):
        raise HTTPException(status_code=401, detail="authentication required")
    if auth_context.user.username == SERVICE_USERNAME:
        raise HTTPException(status_code=401, detail="authentication required")
    if admin_required and not auth_context.user.is_admin:
        raise HTTPException(status_code=403, detail="admin privileges required")
    return auth_context


def _provided_bootstrap_token(
    request: Request,
    payload_token: str | None,
) -> str | None:
    header_token = (request.headers.get("x-lidltool-bootstrap-token") or "").strip()
    if header_token:
        return header_token
    raw_payload = (payload_token or "").strip()
    return raw_payload or None


def _bootstrap_token_required(config: AppConfig) -> bool:
    return bool((config.auth_bootstrap_token or "").strip())


def _enforce_initial_bootstrap_guard(
    *,
    request: Request,
    config: AppConfig,
    provided_token: str | None,
) -> None:
    policy = evaluate_deployment_policy(config)
    expected_token = (config.auth_bootstrap_token or "").strip()
    if expected_token:
        if provided_token != expected_token:
            raise HTTPException(status_code=403, detail="invalid bootstrap token")
        return
    if policy.requires_remote_safeguards:
        raise HTTPException(
            status_code=403,
            detail="initial bootstrap requires a configured bootstrap token for non-local deployments",
        )
    if policy.exposure_mode == HttpExposureMode.LOCALHOST and not is_loopback_request(request):
        raise HTTPException(
            status_code=403,
            detail="initial bootstrap requires a loopback request or configured bootstrap token",
        )


def _validate_bootstrap_startup_guard(
    *,
    config: AppConfig,
    sessions: sessionmaker[Session],
    bind_host: str | None = None,
) -> None:
    with session_scope(sessions) as session:
        evaluate_deployment_policy(
            config,
            bind_host=bind_host,
            has_human_users=human_user_count(session) > 0,
        )


def _resolve_request_user_identity(
    *,
    request: Request,
    app_config: AppConfig,
    sessions: sessionmaker[Session],
) -> tuple[str, bool]:
    with session_scope(sessions) as session:
        current_user = _resolve_request_user(request=request, session=session, config=app_config)
        return current_user.user_id, current_user.username == SERVICE_USERNAME


def _visibility_for_scope(user: User, scope: str | None) -> VisibilityContext:
    parsed_scope = parse_scope(scope)
    if (
        parsed_scope.shared_group_id is not None
        and user.username != SERVICE_USERNAME
        and not any(
            membership.group_id == parsed_scope.shared_group_id
            and membership.membership_status == "active"
            for membership in user.shared_group_memberships
        )
    ):
        raise HTTPException(status_code=403, detail="shared group access denied")
    return VisibilityContext(
        user_id=user.user_id,
        is_service=(user.username == SERVICE_USERNAME),
        scope=parsed_scope.scope,
        workspace_kind=parsed_scope.workspace_kind,
        shared_group_id=parsed_scope.shared_group_id,
    )


def _document_is_visible(
    *,
    session: Session,
    document: Document,
    visibility: VisibilityContext,
) -> bool:
    if document.transaction_id:
        tx = transaction_detail(
            session, transaction_id=document.transaction_id, visibility=visibility
        )
        return tx is not None
    if document.source_id is None:
        return visibility.is_service
    source = session.get(Source, document.source_id)
    if source is None:
        return False
    return resource_belongs_to_workspace(
        visibility=visibility,
        resource_user_id=source.user_id,
        resource_shared_group_id=source.shared_group_id,
    )


def _source_is_visible(
    *,
    session: Session,
    source_id: str,
    visibility: VisibilityContext,
) -> bool:
    source = session.get(Source, source_id)
    if source is None:
        return False
    return resource_belongs_to_workspace(
        visibility=visibility,
        resource_user_id=source.user_id,
        resource_shared_group_id=source.shared_group_id,
    )


def _dashboard_summary_payload(
    app: FastAPI,
    session: Session,
    *,
    config: AppConfig,
    user: User,
    visibility: VisibilityContext,
    year: int,
    month: int,
    recent_limit: int,
) -> dict[str, Any]:
    cards = dashboard_totals(
        session,
        year=year,
        month=month,
        visibility=visibility,
    )
    recent = search_transactions(
        session,
        limit=min(max(recent_limit, 1), 20),
        offset=0,
        visibility=visibility,
    )
    recent = _collection_result(result=recent, alias_key="transactions")
    offer_counts = offer_overview(session, config=config, user_id=user.user_id)["counts"]
    auth_service = _connector_auth_service(app, config=config)
    visible_sources = session.execute(
        select(Source).where(
            Source.user_id == user.user_id
            if user.username != SERVICE_USERNAME
            else (Source.user_id == user.user_id) | Source.user_id.is_(None)
        )
    ).scalars().all()
    source_statuses = [
        _source_status_payload(
            app,
            session,
            auth_service=auth_service,
            config=config,
            source=source,
        )
        for source in visible_sources
    ]
    needs_attention = sum(1 for item in source_statuses if item["needs_attention"] is True)
    return {
        "period": cards["period"],
        "totals": cards["totals"],
        "recent_transactions": recent["transactions"],
        "recent_transactions_pagination": recent["pagination"],
        "offers": offer_counts,
        "sources": {
            "count": len(source_statuses),
            "needs_attention": needs_attention,
            "healthy": sum(1 for item in source_statuses if item["status"] == "healthy"),
            "syncing": sum(1 for item in source_statuses if item["status"] == "syncing"),
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }


def _normalize_dashboard_window(
    from_date: str | None,
    to_date: str | None,
) -> tuple[datetime, datetime]:
    today = datetime.now(tz=UTC)
    if from_date:
        parsed_from = _parse_optional_iso_datetime(from_date)
    else:
        parsed_from = today - timedelta(days=6)
    if to_date:
        parsed_to = _parse_to_date(to_date)
    else:
        parsed_to = today
    if parsed_from is None or parsed_to is None:
        raise ValueError("dashboard window could not be parsed")
    if parsed_from > parsed_to:
        raise ValueError("from_date must be <= to_date")
    return parsed_from, parsed_to


def _serialize_cashflow_points(entries: list[CashflowEntry]) -> list[dict[str, Any]]:
    by_day: dict[str, dict[str, int]] = {}
    for entry in entries:
        key = entry.effective_date.isoformat()
        bucket = by_day.setdefault(key, {"inflow_cents": 0, "outflow_cents": 0})
        if entry.direction == "inflow":
            bucket["inflow_cents"] += entry.amount_cents
        else:
            bucket["outflow_cents"] += entry.amount_cents
    return [
        {
            "date": day,
            "inflow_cents": values["inflow_cents"],
            "outflow_cents": values["outflow_cents"],
            "net_cents": values["inflow_cents"] - values["outflow_cents"],
        }
        for day, values in sorted(by_day.items())
    ]


def _cashflow_totals(entries: list[CashflowEntry]) -> dict[str, int]:
    inflow_cents = sum(
        entry.amount_cents for entry in entries if entry.direction == "inflow"
    )
    outflow_cents = sum(
        entry.amount_cents for entry in entries if entry.direction == "outflow"
    )
    return {
        "inflow_cents": inflow_cents,
        "outflow_cents": outflow_cents,
        "net_cents": inflow_cents - outflow_cents,
    }


SHOPPING_MANUAL_CATEGORY_PREFIXES = ("groceries", "shopping")
SHOPPING_MANUAL_CATEGORIES = {
    "bakery",
    "beverages",
    "deposit",
    "drugstore",
    "fish",
    "food",
    "frozen",
    "groceries",
    "household",
    "meat",
    "pantry",
    "personal_care",
    "produce",
    "snacks",
    "supermarket",
}


def _shopping_purchase_filter() -> ColumnElement[bool]:
    category_item = aliased(TransactionItem)
    normalized_category = func.lower(func.trim(func.coalesce(category_item.category, "")))
    has_shopping_manual_category = exists(
        select(category_item.id).select_from(category_item).where(
            category_item.transaction_id == Transaction.id,
            or_(
                *[
                    normalized_category.like(f"{prefix}%")
                    for prefix in SHOPPING_MANUAL_CATEGORY_PREFIXES
                ],
                normalized_category.in_(SHOPPING_MANUAL_CATEGORIES),
            ),
        ).correlate(Transaction)
    )
    has_recurring_match = exists(
        select(RecurringBillMatch.id).select_from(RecurringBillMatch).where(
            RecurringBillMatch.transaction_id == Transaction.id
        ).correlate(Transaction)
    )
    return and_(
        ~has_recurring_match,
        or_(
            Source.kind.in_(("connector", "ocr")),
            and_(Source.kind == "manual", has_shopping_manual_category),
        ),
    )


def _shopping_purchase_totals(
    session: Session,
    *,
    from_dt: datetime,
    to_dt: datetime,
    visibility: VisibilityContext,
    source_ids: list[str] | None = None,
) -> dict[str, int]:
    end = to_dt + timedelta(days=1)
    stmt = (
        select(
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.total_gross_cents), 0),
        )
        .join(Source, Source.id == Transaction.source_id)
        .where(
            Transaction.purchased_at >= from_dt,
            Transaction.purchased_at < end,
            Transaction.id.in_(visible_transaction_ids_subquery(visibility)),
            _shopping_purchase_filter(),
        )
    )
    if source_ids:
        stmt = stmt.where(Transaction.source_id.in_(source_ids))
    receipt_count, total_cents = session.execute(stmt).one()
    return {
        "receipt_count": int(receipt_count or 0),
        "total_cents": int(total_cents or 0),
    }


def _dashboard_purchase_transactions(
    session: Session,
    *,
    from_dt: datetime,
    to_dt: datetime,
    visibility: VisibilityContext,
    source_ids: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    end = to_dt + timedelta(days=1)
    stmt = (
        select(Transaction)
        .join(Source, Source.id == Transaction.source_id)
        .where(
            Transaction.purchased_at >= from_dt,
            Transaction.purchased_at < end,
            Transaction.id.in_(visible_transaction_ids_subquery(visibility)),
            _shopping_purchase_filter(),
        )
        .order_by(Transaction.purchased_at.desc(), Transaction.created_at.desc())
        .limit(limit)
    )
    if source_ids:
        stmt = stmt.where(Transaction.source_id.in_(source_ids))
    transactions = session.execute(stmt).scalars().all()
    return [
        {
            "id": transaction.id,
            "purchased_at": transaction.purchased_at.isoformat(),
            "source_id": transaction.source_id,
            "user_id": transaction.user_id,
            "shared_group_id": transaction.shared_group_id,
            "store_name": display_merchant_name(transaction.source_id, transaction.merchant_name),
            "total_gross_cents": transaction.total_gross_cents,
            "currency": transaction.currency,
            "discount_total_cents": transaction.discount_total_cents or 0,
            "source_transaction_id": transaction.source_transaction_id,
        }
        for transaction in transactions
    ]


def _dashboard_source_filters(
    session: Session,
    *,
    visibility: VisibilityContext,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            Transaction.source_id,
            func.coalesce(Source.display_name, Transaction.source_id),
            func.count(Transaction.id),
        )
        .select_from(Transaction)
        .join(Source, Source.id == Transaction.source_id, isouter=True)
        .where(Transaction.id.in_(visible_transaction_ids_subquery(visibility)))
        .group_by(Transaction.source_id, func.coalesce(Source.display_name, Transaction.source_id))
        .order_by(func.coalesce(Source.display_name, Transaction.source_id).asc())
    )
    rows = session.execute(stmt).all()
    filters: list[dict[str, Any]] = []
    for source_id, display_name, count in rows:
        source_id_text = str(source_id or "")
        label = str(display_name or source_id_text)
        if source_id_text.startswith("lidl_plus"):
            label = "Lidl"
        filters.append(
            {
                "source_id": source_id_text,
                "label": label,
                "transaction_count": int(count or 0),
            }
        )
    return filters


def _dashboard_overview_payload(
    session: Session,
    *,
    user: User,
    visibility: VisibilityContext,
    from_dt: datetime,
    to_dt: datetime,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    normalized_source_ids = sorted({source_id.strip() for source_id in source_ids or [] if source_id.strip()}) or None
    previous_days = max(1, (to_dt.date() - from_dt.date()).days + 1)
    previous_from = from_dt - timedelta(days=previous_days)
    previous_to = from_dt - timedelta(days=1)

    current_totals = dashboard_window_totals(
        session, from_date=from_dt, to_date=to_dt, visibility=visibility, source_ids=normalized_source_ids
    )
    previous_totals = dashboard_window_totals(
        session, from_date=previous_from, to_date=previous_to, visibility=visibility, source_ids=normalized_source_ids
    )
    current_purchase_totals = _shopping_purchase_totals(
        session, from_dt=from_dt, to_dt=to_dt, visibility=visibility, source_ids=normalized_source_ids
    )
    previous_purchase_totals = _shopping_purchase_totals(
        session, from_dt=previous_from, to_dt=previous_to, visibility=visibility, source_ids=normalized_source_ids
    )
    current_purchase_total_cents = current_purchase_totals["total_cents"]
    previous_purchase_total_cents = previous_purchase_totals["total_cents"]
    category_rows = dashboard_category_spend_summary(
        session, from_date=from_dt, to_date=to_dt, visibility=visibility, source_ids=normalized_source_ids
    )
    merchant_rows = dashboard_merchant_summary(
        session, from_date=from_dt, to_date=to_dt, visibility=visibility, source_ids=normalized_source_ids
    )
    recent_transactions = _dashboard_purchase_transactions(
        session, from_dt=from_dt, to_dt=to_dt, visibility=visibility, source_ids=normalized_source_ids, limit=5
    )

    cashflow_entries = [] if normalized_source_ids else session.execute(
        select(CashflowEntry)
        .where(
            CashflowEntry.user_id == user.user_id,
            CashflowEntry.effective_date >= from_dt.date(),
            CashflowEntry.effective_date <= to_dt.date(),
        )
        .order_by(CashflowEntry.effective_date.asc(), CashflowEntry.created_at.asc())
    ).scalars().all()
    previous_cashflow_entries = [] if normalized_source_ids else session.execute(
        select(CashflowEntry)
        .where(
            CashflowEntry.user_id == user.user_id,
            CashflowEntry.effective_date >= previous_from.date(),
            CashflowEntry.effective_date <= previous_to.date(),
        )
    ).scalars().all()
    current_cashflow_totals = _cashflow_totals(cashflow_entries)
    previous_cashflow_totals = _cashflow_totals(previous_cashflow_entries)

    recurring_rows = session.execute(
        select(
            RecurringBillOccurrence,
            RecurringBill,
        )
        .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
        .where(
            RecurringBill.user_id == user.user_id,
            RecurringBillOccurrence.due_date >= datetime.now(tz=UTC).date(),
            RecurringBillOccurrence.due_date
            <= max(datetime.now(tz=UTC).date(), to_dt.date() + timedelta(days=14)),
            RecurringBillOccurrence.status.in_(("upcoming", "due", "overdue")),
        )
        .order_by(RecurringBillOccurrence.due_date.asc(), RecurringBill.name.asc())
        .limit(6)
    ).all()
    upcoming_bill_items = [
        {
            "occurrence_id": occurrence.id,
            "bill_id": bill.id,
            "bill_name": bill.name,
            "status": occurrence.status,
            "due_date": occurrence.due_date.isoformat(),
            "expected_amount_cents": occurrence.expected_amount_cents,
        }
        for occurrence, bill in recurring_rows
    ]

    grocery_trip_count = current_purchase_totals["receipt_count"]
    grocery_average_cents = (
        round(current_purchase_total_cents / grocery_trip_count) if grocery_trip_count > 0 else 0
    )

    budget_rows = budget_utilization(
        session,
        year=to_dt.year,
        month=to_dt.month,
        visibility=visibility,
        user_id=user.user_id,
    )["rows"]
    goal_rows = goals_summary(
        session,
        user_id=user.user_id,
        visibility=visibility,
        from_date=from_dt.date(),
        to_date=to_dt.date(),
    )["items"]

    activity_items: list[dict[str, Any]] = []
    for transaction in recent_transactions:
        activity_items.append(
            {
                "id": f"tx:{transaction['id']}",
                "kind": "transaction",
                "title": transaction["store_name"] or transaction["source_id"],
                "subtitle": "Transaction imported",
                "amount_cents": transaction["total_gross_cents"],
                "occurred_at": transaction["purchased_at"],
                "href": f"/transactions/{transaction['id']}",
            }
        )
    for entry in reversed(cashflow_entries[-4:]):
        activity_items.append(
            {
                "id": f"cashflow:{entry.id}",
                "kind": "cashflow",
                "title": entry.description or entry.category,
                "subtitle": entry.direction.capitalize(),
                "amount_cents": entry.amount_cents,
                "occurred_at": datetime.combine(entry.effective_date, datetime.min.time(), tzinfo=UTC).isoformat(),
                "href": "/cash-flow",
            }
        )
    for occurrence, bill in recurring_rows[:3]:
        activity_items.append(
            {
                "id": f"bill:{occurrence.id}",
                "kind": "bill",
                "title": bill.name,
                "subtitle": occurrence.status.capitalize(),
                "amount_cents": occurrence.expected_amount_cents or 0,
                "occurred_at": datetime.combine(occurrence.due_date, datetime.min.time(), tzinfo=UTC).isoformat(),
                "href": "/bills",
            }
        )
    activity_items.sort(key=lambda item: item["occurred_at"], reverse=True)

    spend_delta_cents = current_totals["net_cents"] - previous_totals["net_cents"]
    spend_delta_pct = 0.0
    if previous_totals["net_cents"] > 0:
        spend_delta_pct = round(spend_delta_cents / previous_totals["net_cents"], 4)
    insight = {
        "kind": "spend_change",
        "title": "Spending insight",
        "body": (
            "Net spending is lower than the previous comparison window."
            if spend_delta_cents < 0
            else "Net spending is higher than the previous comparison window."
        ),
        "delta_cents": spend_delta_cents,
        "delta_pct": spend_delta_pct,
        "href": "/transactions",
    }

    def _delta(current: int, previous: int) -> dict[str, Any]:
        delta_cents = current - previous
        delta_pct = round(delta_cents / previous, 4) if previous > 0 else None
        return {
            "current_cents": current,
            "previous_cents": previous,
            "delta_cents": delta_cents,
            "delta_pct": delta_pct,
        }

    return {
        "period": {
            "from_date": from_dt.date().isoformat(),
            "to_date": to_dt.date().isoformat(),
            "comparison_from_date": previous_from.date().isoformat(),
            "comparison_to_date": previous_to.date().isoformat(),
            "days": previous_days,
        },
        "source_filters": _dashboard_source_filters(session, visibility=visibility),
        "selected_source_ids": normalized_source_ids or [],
        "kpis": {
            "total_spending": _delta(current_totals["net_cents"], previous_totals["net_cents"]),
            "groceries": _delta(current_purchase_total_cents, previous_purchase_total_cents),
            "cash_inflow": _delta(
                current_cashflow_totals["inflow_cents"],
                previous_cashflow_totals["inflow_cents"],
            ),
            "cash_outflow": _delta(
                current_cashflow_totals["outflow_cents"],
                previous_cashflow_totals["outflow_cents"],
            ),
        },
        "spending_overview": {
            "total_cents": current_totals["net_cents"],
            "categories": category_rows,
        },
        "cash_flow_summary": {
            "totals": {
                **current_cashflow_totals,
            },
            "points": _serialize_cashflow_points(cashflow_entries),
        },
        "upcoming_bills": {
            "count": len(upcoming_bill_items),
            "total_expected_cents": sum(
                item["expected_amount_cents"] or 0 for item in upcoming_bill_items
            ),
            "items": upcoming_bill_items,
        },
        "recent_grocery_transactions": {
            "count": len(recent_transactions),
            "total_cents": current_purchase_total_cents,
            "average_basket_cents": grocery_average_cents,
            "items": recent_transactions,
        },
        "budget_progress": {
            "count": len(budget_rows),
            "items": budget_rows[:4],
        },
        "recent_activity": {
            "count": len(activity_items),
            "items": activity_items[:8],
        },
        "insight": insight,
        "merchants": {
            "count": len(merchant_rows),
            "items": merchant_rows,
        },
        "top_goals": {
            "count": len(goal_rows),
            "items": goal_rows[:3],
        },
    }


def _owns_user_resource(
    user: User,
    *,
    resource_user_id: str | None,
    resource_shared_group_id: str | None = None,
) -> bool:
    return resource_belongs_to_workspace(
        visibility=VisibilityContext(
            user_id=user.user_id,
            is_service=(user.username == SERVICE_USERNAME),
            scope="personal",
            workspace_kind="personal",
        ),
        resource_user_id=resource_user_id,
        resource_shared_group_id=resource_shared_group_id,
    )


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin privileges required")


def _serialize_user(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "is_admin": user.is_admin,
        "preferred_locale": _normalize_supported_locale(user.preferred_locale),
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }


def _serialize_api_key(key: UserApiKey) -> dict[str, Any]:
    return {
        "key_id": key.key_id,
        "user_id": key.user_id,
        "label": key.label,
        "key_prefix": key.key_prefix,
        "is_active": key.is_active,
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at is not None else None,
        "expires_at": key.expires_at.isoformat() if key.expires_at is not None else None,
        "created_at": key.created_at.isoformat(),
    }


def _chat_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        text_value = content.get("text")
        if isinstance(text_value, str):
            return text_value.strip()
        return ""
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") != "text":
                continue
            text_value = part.get("text")
            if isinstance(text_value, str) and text_value.strip():
                chunks.append(text_value.strip())
        return "\n".join(chunks).strip()
    return ""


def _chat_parts_from_text(text: str) -> list[dict[str, str]]:
    return [{"type": "text", "text": text}]


def _normalize_chat_title(raw_title: str | None) -> str:
    if not raw_title:
        return "New chat"
    normalized = " ".join(raw_title.strip().replace("\n", " ").split())
    if not normalized:
        return "New chat"
    return normalized[:60]


def _default_chat_title_for_message(content: str) -> str:
    normalized = " ".join(content.strip().split())
    if not normalized:
        return "New chat"
    return normalized[:60]


def _serialize_chat_thread(thread: ChatThread) -> dict[str, Any]:
    return {
        "thread_id": thread.thread_id,
        "user_id": thread.user_id,
        "shared_group_id": thread.shared_group_id,
        "workspace_kind": "shared_group" if thread.shared_group_id else "personal",
        "title": thread.title,
        "stream_status": thread.stream_status,
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
        "archived_at": thread.archived_at.isoformat() if thread.archived_at else None,
    }


def _serialize_chat_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "message_id": message.message_id,
        "thread_id": message.thread_id,
        "role": message.role,
        "content_json": message.content_json,
        "tool_name": message.tool_name,
        "tool_call_id": message.tool_call_id,
        "idempotency_key": message.idempotency_key,
        "usage_json": message.usage_json,
        "error": message.error,
        "created_at": message.created_at.isoformat(),
    }


def _serialize_chat_run(run: ChatRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "thread_id": run.thread_id,
        "message_id": run.message_id,
        "model_id": run.model_id,
        "prompt_tokens": run.prompt_tokens,
        "completion_tokens": run.completion_tokens,
        "latency_ms": run.latency_ms,
        "status": run.status,
        "created_at": run.created_at.isoformat(),
    }


def _run_tokens_from_usage(usage: Any) -> tuple[int | None, int | None]:
    if not isinstance(usage, dict):
        return None, None
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if prompt_tokens is None:
        prompt_tokens = usage.get("input")
    if completion_tokens is None:
        completion_tokens = usage.get("output")
    prompt = int(prompt_tokens) if isinstance(prompt_tokens, (int, float)) else None
    completion = int(completion_tokens) if isinstance(completion_tokens, (int, float)) else None
    return prompt, completion


def _normalize_runtime_content_json(content: Any) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(content, list):
        parts: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item)
        if parts:
            return parts
        return _chat_parts_from_text("")
    if isinstance(content, str):
        return _chat_parts_from_text(content)
    if isinstance(content, dict):
        return [content]
    return _chat_parts_from_text("")


def _load_owned_chat_thread(
    *,
    session: Session,
    user: User,
    visibility: VisibilityContext,
    thread_id: str,
) -> ChatThread:
    thread = session.get(ChatThread, thread_id)
    if thread is None or thread.archived_at is not None:
        raise RuntimeError("chat thread not found")
    if not (
        _owns_user_resource(
            user,
            resource_user_id=thread.user_id,
            resource_shared_group_id=thread.shared_group_id,
        )
        or resource_belongs_to_workspace(
            visibility=visibility,
            resource_user_id=thread.user_id,
            resource_shared_group_id=thread.shared_group_id,
        )
    ):
        raise HTTPException(status_code=404, detail="chat thread not found")
    return thread


def _should_autotitle_thread(thread: ChatThread, first_user_message: str) -> bool:
    default_title = _default_chat_title_for_message(first_user_message)
    return thread.title in {"New chat", default_title}


def _schedule_chat_title_generation(
    *,
    config: AppConfig,
    sessions: sessionmaker[Session],
    config_path: Path,
    thread_id: str,
) -> None:
    def _job() -> None:
        try:
            with session_scope(sessions) as session:
                thread = session.get(ChatThread, thread_id)
                if thread is None or thread.archived_at is not None:
                    return
                user_messages = session.scalars(
                    select(ChatMessage)
                    .where(
                        ChatMessage.thread_id == thread_id,
                        ChatMessage.role == "user",
                    )
                    .order_by(ChatMessage.created_at.asc(), ChatMessage.message_id.asc())
                ).all()
                if len(user_messages) < 2:
                    return
                first_user_text = _chat_text_from_content(user_messages[0].content_json)
                if not _should_autotitle_thread(thread, first_user_text):
                    return
                messages = session.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.thread_id == thread_id)
                    .order_by(ChatMessage.created_at.asc(), ChatMessage.message_id.asc())
                ).all()
                transcript_lines: list[str] = []
                for message in messages[-12:]:
                    role = message.role.upper()
                    body = _chat_text_from_content(message.content_json)
                    if not body:
                        continue
                    transcript_lines.append(f"{role}: {body}")
            transcript = "\n".join(transcript_lines).strip()
            if not transcript:
                return

            token = _resolve_ai_bearer_token(
                config,
                config_path,
            )
            from lidltool.ai.runtime import ChatCompletionRequest, RuntimeMessage, RuntimeTask
            from lidltool.ai.runtime import RuntimePolicyMode, resolve_runtime_client

            runtime = resolve_runtime_client(
                config,
                task=RuntimeTask.PI_AGENT,
                policy_mode=RuntimePolicyMode(str(config.pi_agent_runtime_policy)),
                api_key_override=token,
            )
            if runtime is None:
                return
            model = _runtime_model_name(runtime, explicit_model=config.ai_model, app_config=config)
            completion = runtime.complete_chat(
                ChatCompletionRequest(
                    task=RuntimeTask.PI_AGENT,
                    model_name=model,
                    temperature=0.1,
                    max_tokens=24,
                    messages=[
                        RuntimeMessage(
                            role="system",
                            content="Generate a concise conversation title with 5 words or fewer.",
                        ),
                        RuntimeMessage(
                            role="user",
                            content=f"Summarize this conversation in 5 words or fewer.\n\n{transcript}",
                        ),
                    ],
                )
            )
            raw_title = completion.text
            title = _normalize_chat_title(raw_title)
            if title == "New chat":
                return

            with session_scope(sessions) as session:
                thread = session.get(ChatThread, thread_id)
                if thread is None or thread.archived_at is not None:
                    return
                user_messages = session.scalars(
                    select(ChatMessage)
                    .where(
                        ChatMessage.thread_id == thread_id,
                        ChatMessage.role == "user",
                    )
                    .order_by(ChatMessage.created_at.asc(), ChatMessage.message_id.asc())
                ).all()
                if not user_messages:
                    return
                first_user_text = _chat_text_from_content(user_messages[0].content_json)
                if not _should_autotitle_thread(thread, first_user_text):
                    return
                thread.title = title
                thread.updated_at = datetime.now(tz=UTC)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("chat.title_generation_skipped thread_id=%s error=%s", thread_id, exc)

    worker = threading.Thread(target=_job, daemon=True)
    worker.start()


def _service_metadata(app: FastAPI) -> dict[str, Any]:
    started_at = get_started_at(app)
    if started_at is not None:
        uptime_seconds = max(int((datetime.now(tz=UTC) - started_at).total_seconds()), 0)
        started_at_iso = started_at.isoformat()
    else:
        uptime_seconds = 0
        started_at_iso = datetime.now(tz=UTC).isoformat()
    return {
        "service": "lidltool-http-api",
        "version": str(app.version),
        "build": get_build(app),
        "started_at": started_at_iso,
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }


def _serialize_quality_recategorize_job(job: QualityRecategorizeJobState) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "requested_by_user_id": job.requested_by_user_id,
        "requested_at": job.requested_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "source_id": job.source_id,
        "only_fallback_other": job.only_fallback_other,
        "include_suspect_model_items": job.include_suspect_model_items,
        "max_transactions": job.max_transactions,
        "transaction_count": job.transaction_count,
        "candidate_item_count": job.candidate_item_count,
        "updated_transaction_count": job.updated_transaction_count,
        "updated_item_count": job.updated_item_count,
        "skipped_transaction_count": job.skipped_transaction_count,
        "method_counts": dict(job.method_counts or {}),
        "error": job.error,
    }


def _start_quality_recategorize_job(
    app: FastAPI,
    *,
    sessions: sessionmaker[Session],
    config: AppConfig,
    requested_by_user_id: str,
    transaction_ids: list[str],
    source_id: str | None,
    only_fallback_other: bool,
    include_suspect_model_items: bool,
    max_transactions: int | None,
) -> QualityRecategorizeJobState:
    job = QualityRecategorizeJobState(
        job_id=str(uuid4()),
        status="queued",
        requested_by_user_id=requested_by_user_id,
        requested_at=datetime.now(tz=UTC),
        source_id=source_id,
        only_fallback_other=only_fallback_other,
        include_suspect_model_items=include_suspect_model_items,
        max_transactions=max_transactions,
        method_counts={},
    )
    jobs = get_quality_recategorize_jobs(app)
    lock = get_quality_recategorize_lock(app)
    with lock:
        jobs[job.job_id] = job

    def _worker() -> None:
        def _publish_job_progress(summary: Any) -> None:
            with lock:
                job.transaction_count = summary.transaction_count
                job.candidate_item_count = summary.candidate_item_count
                job.updated_transaction_count = summary.updated_transaction_count
                job.updated_item_count = summary.updated_item_count
                job.skipped_transaction_count = summary.skipped_transaction_count
                job.method_counts = dict(summary.method_counts or {})

        with lock:
            job.status = "running"
            job.started_at = datetime.now(tz=UTC)
            job.error = None
        try:
            with session_scope(sessions) as session:
                summary = recategorize_transactions(
                    session=session,
                    config=config,
                    transaction_ids=transaction_ids,
                    source_id=source_id,
                    only_fallback_other=only_fallback_other,
                    include_suspect_model_items=include_suspect_model_items,
                    max_transactions=max_transactions,
                    require_model_runtime=True,
                    progress_callback=_publish_job_progress,
                )
            with lock:
                job.status = "completed"
                job.finished_at = datetime.now(tz=UTC)
                job.transaction_count = summary.transaction_count
                job.candidate_item_count = summary.candidate_item_count
                job.updated_transaction_count = summary.updated_transaction_count
                job.updated_item_count = summary.updated_item_count
                job.skipped_transaction_count = summary.skipped_transaction_count
                job.method_counts = dict(summary.method_counts or {})
        except Exception as exc:  # noqa: BLE001
            with lock:
                job.status = "error"
                job.finished_at = datetime.now(tz=UTC)
                job.error = str(exc)

    worker = threading.Thread(
        target=_worker,
        daemon=True,
        name=f"quality-recategorize-{job.job_id[:8]}",
    )
    worker.start()
    return job


def _readiness_db_check(sessions: sessionmaker[Session]) -> tuple[bool, str]:
    try:
        with session_scope(sessions) as session:
            session.execute(select(1))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("api.readiness.db_check_failed error=%s", exc)
        return False, "database connectivity check failed"


def _readiness_storage_check(config: AppConfig) -> tuple[bool, str]:
    storage_path = config.document_storage_path
    if not storage_path.exists():
        return False, f"storage path missing: {storage_path.name}"
    if not storage_path.is_dir():
        return False, f"storage path is not a directory: {storage_path.name}"
    if not os.access(storage_path, os.R_OK | os.W_OK):
        return False, f"storage path not readable/writable: {storage_path.name}"
    return True, "ok"


def _readiness_scheduler_check(app: FastAPI, config: AppConfig) -> tuple[bool, str]:
    if not config.automations_scheduler_enabled:
        return True, "disabled"
    scheduler = get_automation_scheduler(app)
    worker = getattr(scheduler, "_worker", None)
    if worker is None or not worker.is_alive():
        return False, "automation scheduler is not running"
    return True, "ok"


def _repo_root() -> Path:
    configured = os.getenv("LIDLTOOL_REPO_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def _frontend_dist_dir() -> Path:
    configured = os.getenv("LIDLTOOL_FRONTEND_DIST")
    if configured:
        return Path(configured).expanduser().resolve()
    return _repo_root() / "frontend" / "dist"


def _novnc_static_dir() -> Path | None:
    candidates: list[Path] = []
    configured = os.getenv("LIDLTOOL_NOVNC_DIR")
    if configured:
        candidates.append(Path(configured))
    candidates.extend(
        [
            _repo_root() / "novnc",
            Path("/app/novnc"),
            Path("/usr/share/novnc"),
            Path("/usr/share/novnc/www"),
        ]
    )
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.exists() and resolved.is_dir():
            return resolved
    return None


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _is_running_process(process: subprocess.Popen[str] | None) -> bool:
    return process is not None and process.poll() is None


def _vnc_runtime_is_healthy(runtime: VncRuntime | None) -> bool:
    if runtime is None:
        return False
    return _is_running_process(runtime.xvfb_process) and _is_running_process(runtime.x11vnc_process)


def _stop_vnc_runtime(app: FastAPI) -> None:
    runtime = get_vnc_runtime(app)
    if runtime is None:
        return
    for process in (runtime.x11vnc_process, runtime.xvfb_process):
        if not _is_running_process(process):
            continue
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    set_vnc_runtime(app, None)


def _ensure_vnc_runtime(app: FastAPI) -> VncRuntime:
    existing = get_vnc_runtime(app)
    if existing is not None and _vnc_runtime_is_healthy(existing):
        return existing
    _stop_vnc_runtime(app)

    xvfb_bin = shutil.which("Xvfb")
    x11vnc_bin = shutil.which("x11vnc")
    if not xvfb_bin or not x11vnc_bin:
        raise RuntimeError("virtual display dependencies missing (Xvfb/x11vnc not installed)")

    display = os.getenv("DISPLAY", ":99")
    if not display.startswith(":"):
        display = ":99"
    vnc_port = _pick_free_port()

    xvfb_process = subprocess.Popen(
        [xvfb_bin, display, "-screen", "0", "1280x800x24", "-ac"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    time.sleep(0.4)
    if xvfb_process.poll() is not None:
        raise RuntimeError("failed to start Xvfb virtual display")

    x11vnc_process = subprocess.Popen(
        [
            x11vnc_bin,
            "-display",
            display,
            "-rfbport",
            str(vnc_port),
            "-localhost",
            "-shared",
            "-forever",
            "-nopw",
            "-quiet",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    time.sleep(0.5)
    if x11vnc_process.poll() is not None:
        xvfb_process.terminate()
        raise RuntimeError("failed to start x11vnc")

    runtime = VncRuntime(
        display=display,
        vnc_port=vnc_port,
        xvfb_process=xvfb_process,
        x11vnc_process=x11vnc_process,
    )
    set_vnc_runtime(app, runtime)
    return runtime


def _novnc_login_url(request: Request) -> str | None:
    if _novnc_static_dir() is None:
        return None
    base = str(request.base_url).rstrip("/")
    return (
        f"{base}/vnc/vnc.html?autoconnect=true&resize=remote"
        "&path=api/v1/connectors/vnc/ws"
    )


def _connector_command(
    config: AppConfig,
    *,
    source_id: str,
    operation: Literal["bootstrap", "sync"],
    full: bool = False,
    extra_args: tuple[str, ...] = (),
) -> list[str] | None:
    resolved = ConnectorExecutionService(config=config).build_command(
        source_id=source_id,
        operation=operation,
        extra_args=(
            *(("--full",) if operation == "sync" and full else ()),
            *extra_args,
        ),
    )
    if resolved is None:
        return None
    return list(resolved.command)


def _connector_auth_service(app: FastAPI, *, config: AppConfig) -> ConnectorAuthOrchestrationService:
    execution = ConnectorExecutionService(config=config)
    return ConnectorAuthOrchestrationService(
        config=config,
        session_registry=get_connector_auth_registry(app),
        connector_builder=execution.build_receipt_connector,
        repo_root=_repo_root(),
        process_factory=subprocess.Popen,
    )


def _connector_bootstrap_is_running(session: ConnectorBootstrapSession) -> bool:
    return connector_bootstrap_is_running(session)

def _terminate_connector_bootstrap(session: ConnectorBootstrapSession) -> None:
    terminate_connector_bootstrap(session)


def _connector_any_running(
    sessions: dict[str, ConnectorBootstrapSession],
) -> bool:
    return any_connector_bootstrap_running(sessions)


def _serialize_auth_bootstrap_snapshot(snapshot: AuthBootstrapSnapshot) -> dict[str, Any]:
    return {
        "source_id": snapshot.source_id,
        "status": snapshot.state,
        "command": " ".join(snapshot.command or ()),
        "pid": snapshot.pid,
        "started_at": snapshot.started_at.isoformat() if snapshot.started_at is not None else None,
        "finished_at": snapshot.finished_at.isoformat() if snapshot.finished_at is not None else None,
        "return_code": snapshot.return_code,
        "output_tail": list(snapshot.output_tail),
        "can_cancel": snapshot.can_cancel,
    }


def _connector_process_env(app: FastAPI, *, config: AppConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["LIDLTOOL_REPO_ROOT"] = str(_repo_root())
    env["LIDLTOOL_DB"] = str(config.db_path)
    env["LIDLTOOL_CONFIG_DIR"] = str(config.config_dir)
    if config.db_url:
        env["LIDLTOOL_DB_URL"] = config.db_url
    if config.credential_encryption_key:
        env["LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY"] = config.credential_encryption_key
    runtime = get_vnc_runtime(app)
    if runtime is not None:
        env["DISPLAY"] = runtime.display
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _start_connector_command_session(
    app: FastAPI,
    *,
    source_id: str,
    command: list[str],
    config: AppConfig,
    session_kind: Literal["bootstrap", "sync"],
    thread_name: str,
) -> ConnectorBootstrapSession:
    sessions = get_connector_command_sessions(app, kind=session_kind)
    connector_session = start_connector_command_session(
        ConnectorAuthSessionRegistry(sessions),
        source_id=source_id,
        command=command,
        cwd=_repo_root(),
        env=_connector_process_env(app, config=config),
        process_factory=subprocess.Popen,
        thread_name=thread_name,
    )
    if session_kind == "sync":
        request_context = getattr(app.state, "request_context", None)
        session_factory_for_jobs = (
            request_context.sessions if isinstance(request_context, RequestContext) else None
        )
        if session_factory_for_jobs is not None:
            threading.Thread(
                target=_persist_connector_sync_session,
                kwargs={
                    "session_factory_for_jobs": session_factory_for_jobs,
                    "connector_session": connector_session,
                },
                daemon=True,
                name=f"{thread_name}-job-persist",
            ).start()
    return connector_session


def _persist_connector_sync_session(
    *,
    session_factory_for_jobs: sessionmaker[Session],
    connector_session: ConnectorBootstrapSession,
) -> None:
    _wait_for_connector_session(connector_session)
    with connector_session.lock:
        return_code = connector_session.return_code
        canceled = connector_session.canceled
        source_id = connector_session.source_id
        started_at = connector_session.started_at
        finished_at = connector_session.finished_at or datetime.now(tz=UTC)
        command = list(connector_session.command)
        output_tail = list(connector_session.output)[-30:]
    status = "success" if return_code == 0 else "canceled" if canceled else "failed"
    error = None if status == "success" else _connector_command_failure_message(output_tail, status=status)
    try:
        with session_scope(session_factory_for_jobs) as session:
            if session.get(Source, source_id) is None:
                return
            duplicate = (
                session.query(IngestionJob)
                .filter(
                    IngestionJob.source_id == source_id,
                    IngestionJob.trigger_type == "connector_sync_command",
                    IngestionJob.started_at == started_at,
                    IngestionJob.status == status,
                )
                .one_or_none()
            )
            if duplicate is not None:
                return
            session.add(
                IngestionJob(
                    source_id=source_id,
                    status=status,
                    trigger_type="connector_sync_command",
                    started_at=started_at,
                    finished_at=finished_at,
                    error=error,
                    summary={
                        "command": command,
                        "return_code": return_code,
                        "output_tail": output_tail,
                        "warnings": [error] if error else [],
                    },
                )
            )
    except Exception:  # noqa: BLE001
        LOGGER.exception("connector.sync_job_persist.failed source_id=%s", source_id)


def _connector_command_failure_message(output_tail: list[str], *, status: str) -> str:
    for line in reversed(output_tail):
        stripped = str(line).strip().strip("│╭╰─ ")
        if not stripped:
            continue
        lowered = stripped.lower()
        if lowered in {
            "error",
            "usage: python -m lidltool.cli connectors sync [options]",
            "try 'python -m lidltool.cli connectors sync --help' for help.",
        }:
            continue
        if "info  [alembic.runtime.migration]" in lowered:
            continue
        return stripped
    return f"connector sync {status}"


def _wait_for_connector_session(
    session: ConnectorBootstrapSession,
    *,
    cancel_event: threading.Event | None = None,
    poll_interval_s: float = 0.20,
) -> bool:
    while _connector_bootstrap_is_running(session):
        if cancel_event is not None and cancel_event.wait(poll_interval_s):
            _terminate_connector_bootstrap(session)
            return False
        if cancel_event is None:
            time.sleep(poll_interval_s)
    return True


def _normalize_cascade_source_ids(source_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for source_id in source_ids:
        candidate = source_id.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    if not normalized:
        raise RuntimeError("source_ids must include at least one source")
    return normalized


def _connector_is_preview_source(
    source_id: str,
    *,
    config: AppConfig,
    manifest: ConnectorManifest | None = None,
) -> bool:
    resolved_manifest = manifest
    if resolved_manifest is None:
        resolved_manifest = get_connector_registry(config).get_manifest(source_id)
    return (
        release_policy_payload(source_id=source_id, manifest=resolved_manifest).get("maturity")
        == "preview"
    )


def _idle_connector_cascade_status() -> dict[str, Any]:
    return {
        "status": "idle",
        "source_ids": [],
        "full": False,
        "started_at": None,
        "finished_at": None,
        "current_source_id": None,
        "current_step": None,
        "can_cancel": False,
        "remote_login_url": None,
        "summary": {
            "total_sources": 0,
            "completed": 0,
            "failed": 0,
            "canceled": 0,
            "pending": 0,
            "skipped": 0,
        },
        "sources": [],
    }


def _connector_cascade_is_active(cascade: ConnectorCascadeSession) -> bool:
    return cascade.status in {"running", "canceling"}


def _start_connector_cascade_session(
    app: FastAPI,
    *,
    user_id: str,
    source_ids: list[str],
    full: bool,
    config: AppConfig,
    warnings: list[str | ApiWarningDetail],
) -> ConnectorCascadeSession:
    try:
        _ensure_vnc_runtime(app)
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            f"remote browser session unavailable; falling back to local display ({exc})"
        )

    cascade = ConnectorCascadeSession(
        user_id=user_id,
        source_ids=source_ids,
        full=full,
        status="running",
        started_at=datetime.now(tz=UTC),
        lock=threading.Lock(),
        cancel_event=threading.Event(),
        sources={
            source_id: ConnectorCascadeSourceState(source_id=source_id)
            for source_id in source_ids
        },
    )
    worker = threading.Thread(
        target=_run_connector_cascade,
        kwargs={"app": app, "user_id": user_id, "config": config},
        daemon=True,
        name=f"connector-cascade-{user_id[:8]}",
    )
    cascade.worker_thread = worker
    cascade_sessions = get_connector_cascade_sessions(app)
    cascade_sessions[user_id] = cascade
    worker.start()

    if any(_connector_is_preview_source(source_id, config=config) for source_id in source_ids):
        warnings.append(
            "cascade includes preview connectors that are not fully live-validated yet"
        )
    return cascade


def _serialize_connector_cascade(
    cascade: ConnectorCascadeSession,
    *,
    request: Request | None = None,
) -> dict[str, Any]:
    source_payload: list[dict[str, Any]] = []
    completed = 0
    failed = 0
    canceled = 0
    pending = 0
    skipped = 0

    with cascade.lock:
        status = cascade.status
        source_ids = list(cascade.source_ids)
        full = cascade.full
        started_at = cascade.started_at
        finished_at = cascade.finished_at
        current_source_id = cascade.current_source_id
        current_step = cascade.current_step
        for source_id in source_ids:
            source_state = cascade.sources[source_id]
            bootstrap = (
                _serialize_connector_bootstrap(source_state.bootstrap)
                if source_state.bootstrap is not None
                else None
            )
            sync = (
                _serialize_connector_bootstrap(source_state.sync)
                if source_state.sync is not None
                else None
            )
            source_payload.append(
                {
                    "source_id": source_state.source_id,
                    "state": source_state.state,
                    "started_at": (
                        source_state.started_at.isoformat()
                        if source_state.started_at is not None
                        else None
                    ),
                    "finished_at": (
                        source_state.finished_at.isoformat()
                        if source_state.finished_at is not None
                        else None
                    ),
                    "error": source_state.error,
                    "bootstrap": bootstrap,
                    "sync": sync,
                }
            )
            if source_state.state == "completed":
                completed += 1
            elif source_state.state in {"bootstrap_failed", "sync_failed"}:
                failed += 1
            elif source_state.state == "canceled":
                canceled += 1
            elif source_state.state == "skipped":
                skipped += 1
            elif source_state.state in {"pending", "bootstrapping", "syncing"}:
                pending += 1

    remote_login_url: str | None = None
    if (
        request is not None
        and status in {"running", "canceling"}
        and current_step == "bootstrap"
    ):
        remote_login_url = _novnc_login_url(request)

    return {
        "status": status,
        "source_ids": source_ids,
        "full": full,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat() if finished_at is not None else None,
        "current_source_id": current_source_id,
        "current_step": current_step,
        "can_cancel": status in {"running", "canceling"},
        "remote_login_url": remote_login_url,
        "summary": {
            "total_sources": len(source_ids),
            "completed": completed,
            "failed": failed,
            "canceled": canceled,
            "pending": pending,
            "skipped": skipped,
        },
        "sources": source_payload,
    }


def _retryable_cascade_states(*, include_skipped: bool) -> set[str]:
    states = {
        "bootstrap_failed",
        "sync_failed",
        "canceled",
        "pending",
        "bootstrapping",
        "syncing",
    }
    if include_skipped:
        states.add("skipped")
    return states


def _mark_cascade_pending_sources_skipped(
    cascade: ConnectorCascadeSession,
    *,
    start_index: int,
    reason: str,
) -> None:
    timestamp = datetime.now(tz=UTC)
    for source_id in cascade.source_ids[start_index:]:
        source_state = cascade.sources[source_id]
        if source_state.state != "pending":
            continue
        source_state.state = "skipped"
        source_state.error = reason
        source_state.finished_at = timestamp


def _run_connector_cascade(
    app: FastAPI,
    *,
    user_id: str,
    config: AppConfig,
) -> None:
    sessions = get_connector_cascade_sessions(app)
    cascade = sessions.get(user_id)
    if cascade is None:
        return

    any_success = False
    any_failure = False
    try:
        for index, source_id in enumerate(cascade.source_ids):
            with cascade.lock:
                if cascade.cancel_event.is_set():
                    cascade.status = "canceled"
                    _mark_cascade_pending_sources_skipped(
                        cascade,
                        start_index=index,
                        reason="canceled before start",
                    )
                    break
                source_state = cascade.sources[source_id]
                source_state.state = "bootstrapping"
                source_state.started_at = datetime.now(tz=UTC)
                source_state.finished_at = None
                source_state.error = None
                cascade.current_source_id = source_id
                cascade.current_step = "bootstrap"

            bootstrap_command = _connector_command(
                config,
                source_id=source_id,
                operation="bootstrap",
            )
            if bootstrap_command is None:
                any_failure = True
                with cascade.lock:
                    source_state = cascade.sources[source_id]
                    source_state.state = "bootstrap_failed"
                    source_state.finished_at = datetime.now(tz=UTC)
                    source_state.error = f"connector bootstrap not supported for source: {source_id}"
                continue

            bootstrap = _start_connector_command_session(
                app,
                source_id=source_id,
                command=bootstrap_command,
                config=config,
                session_kind="bootstrap",
                thread_name=f"connector-cascade-bootstrap-{source_id}",
            )
            with cascade.lock:
                cascade.sources[source_id].bootstrap = bootstrap

            bootstrap_finished = _wait_for_connector_session(
                bootstrap,
                cancel_event=cascade.cancel_event,
            )
            bootstrap_result = _serialize_connector_bootstrap(bootstrap)
            if not bootstrap_finished:
                with cascade.lock:
                    source_state = cascade.sources[source_id]
                    source_state.state = "canceled"
                    source_state.finished_at = datetime.now(tz=UTC)
                    source_state.error = "canceled during bootstrap"
                    cascade.status = "canceling"
                    _mark_cascade_pending_sources_skipped(
                        cascade,
                        start_index=index + 1,
                        reason="canceled before source started",
                    )
                break
            if bootstrap_result.get("return_code") != 0:
                any_failure = True
                with cascade.lock:
                    source_state = cascade.sources[source_id]
                    source_state.state = "bootstrap_failed"
                    source_state.finished_at = datetime.now(tz=UTC)
                    source_state.error = "connector bootstrap failed"
                continue

            sync_command = _connector_command(
                config,
                source_id=source_id,
                operation="sync",
                full=cascade.full,
            )
            if sync_command is None:
                any_failure = True
                with cascade.lock:
                    source_state = cascade.sources[source_id]
                    source_state.state = "sync_failed"
                    source_state.finished_at = datetime.now(tz=UTC)
                    source_state.error = f"connector sync not supported for source: {source_id}"
                continue

            with cascade.lock:
                source_state = cascade.sources[source_id]
                source_state.state = "syncing"
                source_state.error = None
                cascade.current_step = "sync"

            sync = _start_connector_command_session(
                app,
                source_id=source_id,
                command=sync_command,
                config=config,
                session_kind="sync",
                thread_name=f"connector-cascade-sync-{source_id}",
            )
            with cascade.lock:
                cascade.sources[source_id].sync = sync

            sync_finished = _wait_for_connector_session(
                sync,
                cancel_event=cascade.cancel_event,
            )
            sync_result = _serialize_connector_bootstrap(sync)
            if not sync_finished:
                with cascade.lock:
                    source_state = cascade.sources[source_id]
                    source_state.state = "canceled"
                    source_state.finished_at = datetime.now(tz=UTC)
                    source_state.error = "canceled during sync"
                    cascade.status = "canceling"
                    _mark_cascade_pending_sources_skipped(
                        cascade,
                        start_index=index + 1,
                        reason="canceled before source started",
                    )
                break

            if sync_result.get("return_code") == 0:
                any_success = True
                with cascade.lock:
                    source_state = cascade.sources[source_id]
                    source_state.state = "completed"
                    source_state.finished_at = datetime.now(tz=UTC)
                    source_state.error = None
            else:
                any_failure = True
                with cascade.lock:
                    source_state = cascade.sources[source_id]
                    source_state.state = "sync_failed"
                    source_state.finished_at = datetime.now(tz=UTC)
                    source_state.error = "connector sync failed"
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("connector.cascade.unhandled_error user_id=%s", user_id)
        any_failure = True
        with cascade.lock:
            if cascade.current_source_id is not None:
                source_state = cascade.sources[cascade.current_source_id]
                if source_state.state in {"pending", "bootstrapping", "syncing"}:
                    source_state.state = "sync_failed"
                if source_state.finished_at is None:
                    source_state.finished_at = datetime.now(tz=UTC)
                if source_state.error is None:
                    source_state.error = f"cascade worker failed: {exc}"
            cascade.status = "failed"
    finally:
        with cascade.lock:
            cascade.current_source_id = None
            cascade.current_step = None
            cascade.finished_at = datetime.now(tz=UTC)
            if cascade.cancel_event.is_set() or cascade.status == "canceling":
                cascade.status = "canceled"
            elif any_failure and any_success:
                cascade.status = "partial_success"
            elif any_failure:
                cascade.status = "failed"
            else:
                cascade.status = "completed"


AI_OAUTH_CALLBACK_HOST = os.getenv("LIDLTOOL_AI_OAUTH_CALLBACK_BIND_HOST", "127.0.0.1")
AI_OAUTH_CALLBACK_PORT = 1455
AI_OAUTH_CALLBACK_PATH = "/auth/callback"
AI_OAUTH_REDIRECT_URI = f"http://localhost:{AI_OAUTH_CALLBACK_PORT}{AI_OAUTH_CALLBACK_PATH}"
AI_OAUTH_EXPIRES_IN_SECONDS = 300
_OPENAI_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


def _first_query_param(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    if not values:
        return None
    return values[0]


def _set_ai_oauth_state(
    app: FastAPI,
    *,
    status: Literal["pending", "connected", "error"],
    error: str | None = None,
    provider: str | None = None,
) -> None:
    lock = get_ai_oauth_lock(app)
    with lock:
        set_http_ai_oauth_state(
            app,
            {
                "status": status,
                "error": error,
                "provider": provider,
                "updated_at": datetime.now(tz=UTC).isoformat(),
            },
        )


def _get_ai_oauth_state(app: FastAPI) -> dict[str, Any]:
    lock = get_ai_oauth_lock(app)
    with lock:
        return dict(get_http_ai_oauth_state(app))


def _pkce_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _build_openai_codex_auth_url(
    *,
    state: str,
    code_challenge: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": _OPENAI_CODEX_CLIENT_ID,
        "redirect_uri": AI_OAUTH_REDIRECT_URI,
        "scope": "openid profile email offline_access",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    return f"https://auth.openai.com/oauth/authorize?{urlencode(params)}"


def _exchange_openai_oauth_code(
    *,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    response = httpx.post(
        "https://auth.openai.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": _OPENAI_CODEX_CLIENT_ID,
            "code": code,
            "redirect_uri": AI_OAUTH_REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        headers={"Accept": "application/json"},
        timeout=25.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("OAuth token response was not a JSON object")
    return payload


def _run_openai_oauth_callback_server(
    app: FastAPI,
    *,
    config: AppConfig,
    config_path: Path,
    provider: str,
    expected_state: str,
    code_verifier: str,
) -> None:
    completed = threading.Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        server_version = "lidltool-ai-oauth"

        def log_message(self, _format: str, *args: Any) -> None:  # noqa: A003
            LOGGER.info("ai.oauth.callback %s", " ".join(str(arg) for arg in args))

        def _send_html(self, status_code: int, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != AI_OAUTH_CALLBACK_PATH:
                self._send_html(404, "<html><body>Not found.</body></html>")
                return

            params = parse_qs(parsed.query, keep_blank_values=False)
            callback_state = _first_query_param(params, "state")
            if callback_state != expected_state:
                _set_ai_oauth_state(
                    app,
                    status="error",
                    error="OAuth state mismatch",
                    provider=provider,
                )
                self._send_html(400, "<html><body>OAuth state mismatch.</body></html>")
                completed.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            oauth_error = _first_query_param(params, "error")
            if oauth_error:
                description = _first_query_param(params, "error_description") or ""
                message = (
                    f"{oauth_error}: {description}" if description else str(oauth_error)
                )
                _set_ai_oauth_state(
                    app,
                    status="error",
                    error=message,
                    provider=provider,
                )
                self._send_html(400, "<html><body>OAuth authorization failed.</body></html>")
                completed.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            code = _first_query_param(params, "code")
            if not code:
                _set_ai_oauth_state(
                    app,
                    status="error",
                    error="OAuth callback did not include a code",
                    provider=provider,
                )
                self._send_html(400, "<html><body>Missing OAuth code.</body></html>")
                completed.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return

            try:
                token_payload = _exchange_openai_oauth_code(
                    code=code,
                    code_verifier=code_verifier,
                )
                access_token = str(token_payload.get("access_token") or "").strip()
                refresh_token = str(token_payload.get("refresh_token") or "").strip()
                if not access_token:
                    raise RuntimeError("OAuth token exchange did not return an access token")
                expires_in = int(token_payload.get("expires_in") or 3600)

                set_ai_oauth_access_token(config, access_token)
                set_ai_oauth_refresh_token(config, refresh_token or None)
                config.ai_oauth_provider = provider
                config.ai_oauth_expires_at = (
                    datetime.now(tz=UTC) + timedelta(seconds=max(expires_in, 1))
                ).isoformat()
                persist_ai_settings(config_path, config)
                _set_ai_oauth_state(
                    app,
                    status="connected",
                    error=None,
                    provider=provider,
                )
                self._send_html(
                    200,
                    (
                        "<html><body>"
                        "<h3>Authentication complete</h3>"
                        "<p>You can close this tab and return to Lidl Receipts.</p>"
                        "<script>window.close();</script>"
                        "</body></html>"
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                _set_ai_oauth_state(
                    app,
                    status="error",
                    error=str(exc),
                    provider=provider,
                )
                self._send_html(
                    500,
                    "<html><body>Token exchange failed. Return to the app and retry.</body></html>",
                )
            finally:
                completed.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()

    try:
        server = ThreadingHTTPServer(
            (AI_OAUTH_CALLBACK_HOST, AI_OAUTH_CALLBACK_PORT),
            CallbackHandler,
        )
        server.timeout = 1
    except OSError as exc:
        _set_ai_oauth_state(
            app,
            status="error",
            error=f"OAuth callback listener failed: {exc}",
            provider=provider,
        )
        return

    deadline = time.monotonic() + AI_OAUTH_EXPIRES_IN_SECONDS
    try:
        while time.monotonic() < deadline and not completed.is_set():
            server.handle_request()
        if not completed.is_set():
            _set_ai_oauth_state(
                app,
                status="error",
                error="OAuth callback timed out",
                provider=provider,
            )
    finally:
        server.server_close()


def _validate_ai_completion(*, base_url: str, api_key: str, model: str) -> tuple[bool, str | None]:
    try:
        from openai import OpenAI
    except Exception as exc:  # noqa: BLE001
        return False, f"openai SDK is unavailable: {exc}"
    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0,
            max_tokens=1,
        )
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return True, None


def _try_refresh_ai_oauth_token(config: AppConfig, config_path: Path) -> str | None:
    """Attempt a refresh-token grant and update config in place. Returns new access token or None."""
    refresh_token = None
    try:
        from lidltool.ai.config import get_ai_oauth_refresh_token
        refresh_token = get_ai_oauth_refresh_token(config)
    except Exception:  # noqa: BLE001
        pass
    if not refresh_token:
        return None
    try:
        response = httpx.post(
            "https://auth.openai.com/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": _OPENAI_CODEX_CLIENT_ID,
                "refresh_token": refresh_token,
            },
            headers={"Accept": "application/json"},
            timeout=15.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        new_access = str(payload.get("access_token") or "").strip()
        if not new_access:
            return None
        new_refresh = str(payload.get("refresh_token") or "").strip()
        expires_in = int(payload.get("expires_in") or 3600)
        set_ai_oauth_access_token(config, new_access)
        if new_refresh:
            set_ai_oauth_refresh_token(config, new_refresh)
        config.ai_oauth_expires_at = (
            datetime.now(tz=UTC) + timedelta(seconds=max(expires_in, 1))
        ).isoformat()
        persist_ai_settings(config_path, config)
        LOGGER.info("ai.oauth refresh succeeded; new token expires at %s", config.ai_oauth_expires_at)
        return new_access
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("ai.oauth refresh failed: %s", exc)
        return None


def _resolve_ai_oauth_bearer_token(config: AppConfig, config_path: Path | None = None) -> str | None:
    oauth_token = get_ai_oauth_access_token(config)
    if oauth_token:
        expires_at_str = config.ai_oauth_expires_at
        if expires_at_str and config_path:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now(tz=UTC) >= expires_at - timedelta(minutes=5):
                    refreshed = _try_refresh_ai_oauth_token(config, config_path)
                    if refreshed:
                        return refreshed
            except Exception:  # noqa: BLE001
                pass
        return oauth_token


def _resolve_ai_api_key_token(config: AppConfig) -> str | None:
    return get_ai_api_key(config)


def _resolve_ai_bearer_token(config: AppConfig, config_path: Path | None = None) -> str | None:
    return _resolve_ai_oauth_bearer_token(config, config_path) or _resolve_ai_api_key_token(config)


DEFAULT_LOCAL_CHAT_MODEL = "qwen3.5:0.8b"
DEFAULT_CHATGPT_CHAT_MODEL = "gpt-5.4"
DEFAULT_CATEGORIZATION_OAUTH_MODEL = "gpt-5.4-mini"
CHATGPT_OAUTH_CHAT_MODELS: tuple[tuple[str, str, str], ...] = (
    (
        "gpt-5.4",
        "GPT-5.4",
        "Current general ChatGPT/Codex subscription model.",
    ),
    (
        "gpt-5.4-mini",
        "GPT-5.4-Mini",
        "Smaller and cheaper ChatGPT/Codex subscription model.",
    ),
    (
        "gpt-5.3-codex",
        "GPT-5.3-Codex",
        "Codex-tuned ChatGPT subscription model.",
    ),
    (
        "gpt-5.3-codex-spark",
        "GPT-5.3-Codex-Spark",
        "Fast Codex-oriented ChatGPT subscription model.",
    ),
    (
        "gpt-5.2",
        "GPT-5.2",
        "Earlier GPT-5 generation model still available in your ChatGPT/Codex subscription.",
    ),
)


def _chatgpt_oauth_connected(app_config: AppConfig) -> bool:
    return bool(
        app_config.ai_oauth_provider == "openai-codex"
        and _resolve_ai_oauth_bearer_token(app_config)
    )


def _configured_local_chat_model(app_config: AppConfig) -> str:
    return (
        (app_config.local_text_model_name or "").strip()
        or (app_config.item_categorizer_model or "").strip()
        or DEFAULT_LOCAL_CHAT_MODEL
    )


def _configured_oauth_chat_model(app_config: AppConfig) -> str:
    configured = (getattr(app_config, "ai_oauth_model", None) or "").strip()
    return configured or DEFAULT_CHATGPT_CHAT_MODEL


def _configured_api_chat_model(app_config: AppConfig) -> str | None:
    if not app_config.ai_enabled:
        return None
    base_url = (app_config.ai_base_url or "").strip()
    model = (app_config.ai_model or "").strip()
    api_key = _resolve_ai_api_key_token(app_config)
    if not base_url or not model or not api_key:
        return None
    return model


def _iter_chatgpt_oauth_models(app_config: AppConfig) -> list[tuple[str, str, str]]:
    models: list[tuple[str, str, str]] = []
    seen_ids: set[str] = set()
    configured_model = _configured_oauth_chat_model(app_config)
    configured_label = configured_model
    configured_description = "Configured ChatGPT/Codex model via your ChatGPT sign-in."
    for model_id, label, description in CHATGPT_OAUTH_CHAT_MODELS:
        if model_id == configured_model:
            configured_label = label
            configured_description = description
            break
    candidates = [(configured_model, configured_label, configured_description), *CHATGPT_OAUTH_CHAT_MODELS]
    for model_id, label, description in candidates:
        normalized_model_id = (model_id or "").strip()
        if not normalized_model_id or normalized_model_id in seen_ids:
            continue
        seen_ids.add(normalized_model_id)
        models.append((normalized_model_id, label, description))
    return models


def _configured_categorization_model(app_config: AppConfig) -> str:
    provider = _configured_categorization_provider(app_config)
    configured_model = (app_config.item_categorizer_model or "").strip()
    if provider == "oauth_codex":
        if not configured_model or configured_model == DEFAULT_LOCAL_CHAT_MODEL:
            return DEFAULT_CATEGORIZATION_OAUTH_MODEL
        return configured_model
    if configured_model and configured_model != DEFAULT_LOCAL_CHAT_MODEL:
        return configured_model
    return _default_categorization_model(
        provider=provider,
        base_url=(app_config.item_categorizer_base_url or app_config.ai_base_url),
        fallback_model=app_config.ai_model,
    )


def _configured_categorization_provider(app_config: AppConfig) -> str:
    configured = (getattr(app_config, "item_categorizer_provider", "") or "").strip()
    if configured:
        return configured
    if (app_config.item_categorizer_base_url or "").strip():
        return "api_compatible"
    if _chatgpt_oauth_connected(app_config):
        return "oauth_codex"
    return "api_compatible"


def _default_categorization_model(
    *,
    provider: str,
    base_url: str | None,
    fallback_model: str | None,
) -> str:
    if provider == "oauth_codex":
        return DEFAULT_CATEGORIZATION_OAUTH_MODEL
    normalized_base = (base_url or "").strip().lower()
    if "api.openai.com" in normalized_base:
        return "gpt-4o-mini"
    if "api.x.ai" in normalized_base:
        return "grok-3-mini"
    fallback = (fallback_model or "").strip()
    return fallback or "gpt-4o-mini"


def _local_chat_model_enabled(app_config: AppConfig) -> bool:
    from lidltool.ai.runtime import RuntimePolicyMode, RuntimeTask, resolve_runtime

    resolution = resolve_runtime(
        app_config,
        task=RuntimeTask.PI_AGENT,
        policy_mode=RuntimePolicyMode.LOCAL_ONLY,
        api_key_override=_resolve_ai_oauth_bearer_token(app_config) or _resolve_ai_api_key_token(app_config),
    )
    return resolution.selected


def _available_chat_models(app_config: AppConfig) -> list[dict[str, Any]]:
    local_model = _configured_local_chat_model(app_config)
    api_model = _configured_api_chat_model(app_config)
    models: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def add_model(
        *,
        model_id: str | None,
        label: str,
        source: Literal["local", "api", "oauth"],
        enabled: bool,
        description: str,
    ) -> None:
        normalized_model_id = (model_id or "").strip()
        if not normalized_model_id or normalized_model_id in seen_ids:
            return
        seen_ids.add(normalized_model_id)
        models.append(
            {
                "id": normalized_model_id,
                "label": label,
                "source": source,
                "enabled": enabled,
                "description": description,
            }
        )

    add_model(
        model_id=local_model,
        label="Local Qwen (tiny)" if "qwen" in local_model.lower() else "Local model",
        source="local",
        enabled=_local_chat_model_enabled(app_config),
        description=(
            "Very small shipped local fallback model. Private and available by default, but weaker for deeper analysis."
            if "qwen" in local_model.lower()
            else "Local model runtime on your self-hosted stack."
        ),
    )
    for model_id, label, description in _iter_chatgpt_oauth_models(app_config):
        add_model(
            model_id=model_id,
            label=label,
            source="oauth",
            enabled=_chatgpt_oauth_connected(app_config),
            description=description,
        )
    if api_model:
        add_model(
            model_id=api_model,
            label=api_model,
            source="api",
            enabled=True,
            description="Configured API model from AI Settings.",
        )
    return models


def _preferred_chat_model(app_config: AppConfig) -> str:
    available_models = _available_chat_models(app_config)
    enabled_models = [model for model in available_models if model["enabled"]]
    configured_oauth_model = _configured_oauth_chat_model(app_config)
    if _chatgpt_oauth_connected(app_config):
        for model in enabled_models:
            if model["source"] == "oauth" and str(model["id"]) == configured_oauth_model:
                return configured_oauth_model
    for source in ("api", "local", "oauth"):
        for model in enabled_models:
            if model["source"] == source:
                return str(model["id"])
    return _configured_local_chat_model(app_config)


def _resolve_selected_chat_model(app_config: AppConfig, requested_model_id: str | None) -> str:
    normalized_requested = (requested_model_id or "").strip()
    available_models = _available_chat_models(app_config)
    enabled_model_ids = {
        str(model["id"]) for model in available_models if bool(model.get("enabled"))
    }
    if normalized_requested and normalized_requested in enabled_model_ids:
        return normalized_requested
    preferred_model = _preferred_chat_model(app_config)
    if preferred_model in enabled_model_ids:
        return preferred_model
    return next(iter(enabled_model_ids), preferred_model)


def _resolve_pi_agent_runtime_for_model(
    app_config: AppConfig,
    *,
    selected_model_id: str,
) -> Any:
    from lidltool.ai.runtime import RuntimePolicyMode, RuntimeTask, resolve_runtime_client

    local_model = _configured_local_chat_model(app_config)
    api_model = _configured_api_chat_model(app_config)
    local_api_token = _resolve_ai_oauth_bearer_token(app_config) or _resolve_ai_api_key_token(app_config)
    if selected_model_id == local_model:
        runtime = resolve_runtime_client(
            app_config,
            task=RuntimeTask.PI_AGENT,
            policy_mode=RuntimePolicyMode.LOCAL_ONLY,
            api_key_override=local_api_token,
        )
        if runtime is None:
            raise RuntimeError("selected local chat model is not available")
        return runtime

    if api_model and selected_model_id == api_model:
        api_key = _resolve_ai_api_key_token(app_config)
        runtime = resolve_runtime_client(
            app_config,
            task=RuntimeTask.PI_AGENT,
            policy_mode=RuntimePolicyMode.REMOTE_ALLOWED,
            api_key_override=api_key,
        )
        if runtime is None:
            raise RuntimeError("selected API chat model is not available")
        return runtime

    raise RuntimeError(f"unknown or unavailable chat model: {selected_model_id}")


def _should_route_stream_via_chatgpt(app_config: AppConfig, model_id: str) -> bool:
    if not _chatgpt_oauth_connected(app_config):
        return False
    normalized_model_id = (model_id or "").strip()
    return any(candidate_id == normalized_model_id for candidate_id, _, _ in _iter_chatgpt_oauth_models(app_config))


def _runtime_model_name(
    runtime: Any,
    *,
    explicit_model: str | None,
    app_config: AppConfig,
    fallback: str = "gpt-5.2-codex",
) -> str:
    normalized_explicit = (explicit_model or "").strip()
    if normalized_explicit:
        return normalized_explicit
    runtime_model = getattr(runtime, "model_name", None)
    if isinstance(runtime_model, str) and runtime_model.strip():
        return runtime_model.strip()
    local_text_model = (app_config.local_text_model_name or "").strip()
    if local_text_model:
        return local_text_model
    ai_model = (app_config.ai_model or "").strip()
    if ai_model:
        return ai_model
    return fallback


def _authorize_stream_proxy_request(*, request: Request, session: Session, config: AppConfig) -> None:
    context = _require_user_session_auth_context(
        request=request,
        session=session,
        config=config,
    )
    if context is None:
        raise HTTPException(status_code=401, detail="authentication required")


def _sse_data(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


class ReviewDecisionRequest(BaseModel):
    actor_id: str | None = None
    reason: str | None = None


class ReviewCorrectionRequest(BaseModel):
    actor_id: str | None = None
    reason: str | None = None
    corrections: dict[str, Any] = Field(default_factory=dict)


class TransactionItemOverride(BaseModel):
    item_id: str
    corrections: dict[str, Any] = Field(default_factory=dict)


class TransactionOverrideRequest(BaseModel):
    actor_id: str | None = None
    reason: str | None = None
    mode: str = "local"
    transaction_corrections: dict[str, Any] = Field(default_factory=dict)
    item_corrections: list[TransactionItemOverride] = Field(default_factory=list)


class QualityRecategorizeRequest(BaseModel):
    source_id: str | None = None
    only_fallback_other: bool = True
    include_suspect_model_items: bool = False
    max_transactions: int | None = Field(default=250, ge=1, le=5000)


class ManualTransactionItemRequest(BaseModel):
    name: str
    line_total_cents: int
    qty: float = 1.0
    unit: str | None = None
    unit_price_cents: int | None = None
    category: str | None = None
    line_no: int | None = None
    source_item_id: str | None = None
    shared: bool = False
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ManualTransactionDiscountRequest(BaseModel):
    source_label: str
    amount_cents: int
    scope: Literal["transaction", "item"] = "transaction"
    transaction_item_line_no: int | None = None
    source_discount_code: str | None = None
    kind: str = "manual"
    subkind: str | None = None
    funded_by: str = "unknown"
    is_loyalty_program: bool = False
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ManualTransactionCreateRequest(BaseModel):
    purchased_at: datetime
    merchant_name: str
    total_gross_cents: int
    source_id: str = MANUAL_SOURCE_ID
    source_display_name: str | None = None
    source_transaction_id: str | None = None
    source_account_ref: str | None = "manual"
    idempotency_key: str | None = None
    currency: str = "EUR"
    discount_total_cents: int | None = None
    allocation_mode: Literal["personal", "shared_receipt", "split_items"] = "personal"
    confidence: float | None = None
    items: list[ManualTransactionItemRequest] = Field(default_factory=list)
    discounts: list[ManualTransactionDiscountRequest] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    actor_id: str | None = None
    reason: str | None = None


class AutomationRuleCreateRequest(BaseModel):
    name: str
    rule_type: str
    enabled: bool = True
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    action_config: dict[str, Any] = Field(default_factory=dict)
    actor_id: str | None = None


class AutomationRuleUpdateRequest(BaseModel):
    name: str | None = None
    rule_type: str | None = None
    enabled: bool | None = None
    trigger_config: dict[str, Any] | None = None
    action_config: dict[str, Any] | None = None
    actor_id: str | None = None


class AutomationRunRequest(BaseModel):
    actor_id: str | None = None


class OfferRefreshRequest(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    discovery_limit: int | None = Field(default=None, ge=1, le=500)


class OfferSourceCreateRequest(BaseModel):
    merchant_name: str
    merchant_url: str
    display_name: str | None = None
    country_code: str = Field(default="DE", min_length=2, max_length=2)
    notes: str | None = None


class OfferSourceUpdateRequest(BaseModel):
    merchant_name: str | None = None
    merchant_url: str | None = None
    display_name: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    notes: str | None = None
    active: bool | None = None


class OfferWatchlistCreateRequest(BaseModel):
    product_id: str | None = None
    query_text: str | None = None
    source_id: str | None = None
    min_discount_percent: float | None = Field(default=None, ge=0, le=100)
    max_price_cents: int | None = Field(default=None, ge=0)
    notes: str | None = None


class OfferWatchlistUpdateRequest(BaseModel):
    product_id: str | None = None
    query_text: str | None = None
    source_id: str | None = None
    min_discount_percent: float | None = Field(default=None, ge=0, le=100)
    max_price_cents: int | None = Field(default=None, ge=0)
    active: bool | None = None
    notes: str | None = None


class OfferAlertReadRequest(BaseModel):
    read: bool = True


class SavedQueryCreateRequest(BaseModel):
    name: str
    description: str | None = None
    query_json: dict[str, Any] = Field(default_factory=dict)


class QueryRunRequest(BaseModel):
    metrics: list[str]
    dimensions: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    scope: str = "personal"
    time_grain: str | None = None
    sort_by: str | None = None
    sort_dir: str = "desc"
    limit: int | None = None
    chart_pref: str | None = None


class QueryDslRequest(BaseModel):
    dsl: str


class ManualProductMatchRequest(BaseModel):
    product_id: str
    raw_name: str
    source_kind: str | None = None
    raw_sku: str | None = None


class ProductCreateRequest(BaseModel):
    canonical_name: str
    brand: str | None = None
    default_unit: str | None = None
    gtin_ean: str | None = None


class ProductMergeRequest(BaseModel):
    source_product_ids: list[str] = Field(default_factory=list)


class ProductClusterRequest(BaseModel):
    force: bool = False


class AISettingsUpdateRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str


class AIChatSettingsUpdateRequest(BaseModel):
    oauth_model: str | None = None


class AICategorizationSettingsUpdateRequest(BaseModel):
    enabled: bool = False
    provider: Literal["oauth_codex", "api_compatible"] = "oauth_codex"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class OCRSettingsUpdateRequest(BaseModel):
    default_provider: Literal["glm_ocr_local", "openai_compatible", "external_api"]
    fallback_enabled: bool = False
    fallback_provider: Literal["glm_ocr_local", "openai_compatible", "external_api"] | None = None
    glm_local_base_url: str | None = None
    glm_local_api_mode: Literal["ollama_generate", "openai_chat_completion"] | None = None
    glm_local_model: str | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None


class AIOAuthStartRequest(BaseModel):
    provider: Literal["openai-codex", "github-copilot", "google-gemini-cli"]


class StreamProxyModelRef(BaseModel):
    id: str
    provider: str
    api: str | None = None


class StreamProxyContext(BaseModel):
    systemPrompt: str | None = None  # noqa: N815
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)


class StreamProxyOptions(BaseModel):
    temperature: float = 0.7
    maxTokens: int = 4096  # noqa: N815


class StreamProxyRequest(BaseModel):
    model: StreamProxyModelRef
    context: StreamProxyContext
    options: StreamProxyOptions = Field(default_factory=StreamProxyOptions)


class ChatThreadCreateRequest(BaseModel):
    thread_id: str | None = None
    title: str | None = None


class ChatThreadUpdateRequest(BaseModel):
    title: str | None = None
    archived: bool | None = None
    abandon_stream: bool | None = None
    stream_status: Literal["idle", "streaming", "failed"] | None = None


class ChatMessageCreateRequest(BaseModel):
    content: str = Field(max_length=32768)
    idempotency_key: str | None = None


class ChatStreamRequest(BaseModel):
    model_id: str | None = None


class ChatRunPersistRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)
    model_id: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None
    status: Literal["ok", "error", "timeout"] = "ok"
    error: str | None = None


class ComparisonGroupCreateRequest(BaseModel):
    name: str
    unit_standard: str | None = None
    notes: str | None = None


class ComparisonGroupMemberCreateRequest(BaseModel):
    product_id: str
    weight: float = 1.0


class BasketCompareItemRequest(BaseModel):
    product_id: str
    quantity: float = 1.0


class BasketCompareRequest(BaseModel):
    items: list[BasketCompareItemRequest] = Field(default_factory=list)
    net: bool = True


class BudgetRuleCreateRequest(BaseModel):
    scope_type: str
    scope_value: str
    period: str = "monthly"
    amount_cents: int
    currency: str = "EUR"
    active: bool = True


class BudgetMonthUpdateRequest(BaseModel):
    planned_income_cents: int | None = None
    target_savings_cents: int | None = None
    opening_balance_cents: int | None = None
    currency: str = "EUR"
    notes: str | None = None


class CashflowEntryCreateRequest(BaseModel):
    effective_date: date
    direction: Literal["inflow", "outflow"]
    category: str
    amount_cents: int
    currency: str = "EUR"
    description: str | None = None
    source_type: str = "manual"
    linked_transaction_id: str | None = None
    linked_recurring_occurrence_id: str | None = None
    notes: str | None = None


class CashflowEntryUpdateRequest(BaseModel):
    effective_date: date | None = None
    direction: Literal["inflow", "outflow"] | None = None
    category: str | None = None
    amount_cents: int | None = None
    currency: str | None = None
    description: str | None = None
    source_type: str | None = None
    linked_transaction_id: str | None = None
    linked_recurring_occurrence_id: str | None = None
    notes: str | None = None


class GoalCreateRequest(BaseModel):
    name: str
    goal_type: str
    target_amount_cents: int
    currency: str = "EUR"
    period: str = "current_window"
    category: str | None = None
    merchant_name: str | None = None
    recurring_bill_id: str | None = None
    target_date: date | None = None
    notes: str | None = None


class GoalUpdateRequest(BaseModel):
    name: str | None = None
    goal_type: str | None = None
    target_amount_cents: int | None = None
    currency: str | None = None
    period: str | None = None
    category: str | None = None
    merchant_name: str | None = None
    recurring_bill_id: str | None = None
    target_date: date | None = None
    notes: str | None = None
    active: bool | None = None


class NotificationUpdateRequest(BaseModel):
    unread: bool


RecurringBillFrequency = Literal["weekly", "biweekly", "monthly", "quarterly", "yearly"]
RecurringOccurrenceStatus = Literal["upcoming", "due", "paid", "overdue", "skipped", "unmatched"]


class RecurringBillCreateRequest(BaseModel):
    name: str
    merchant_canonical: str | None = None
    merchant_alias_pattern: str | None = None
    category: str = "uncategorized"
    frequency: RecurringBillFrequency
    interval_value: int = 1
    amount_cents: int | None = None
    amount_tolerance_pct: float = 0.1
    currency: str = "EUR"
    anchor_date: date
    active: bool = True
    notes: str | None = None


class RecurringBillUpdateRequest(BaseModel):
    name: str | None = None
    merchant_canonical: str | None = None
    merchant_alias_pattern: str | None = None
    category: str | None = None
    frequency: RecurringBillFrequency | None = None
    interval_value: int | None = None
    amount_cents: int | None = None
    amount_tolerance_pct: float | None = None
    currency: str | None = None
    anchor_date: date | None = None
    active: bool | None = None
    notes: str | None = None


class RecurringGenerateOccurrencesRequest(BaseModel):
    from_date: date | None = None
    to_date: date | None = None
    horizon_months: int = 6


class RecurringRunMatchingRequest(BaseModel):
    auto_match_threshold: float = 0.9
    review_threshold: float = 0.7


class RecurringOccurrenceStatusUpdateRequest(BaseModel):
    status: RecurringOccurrenceStatus
    notes: str | None = None


class RecurringOccurrenceSkipRequest(BaseModel):
    notes: str | None = None


class RecurringOccurrenceReconcileRequest(BaseModel):
    transaction_id: str
    match_confidence: float = 1.0
    match_method: str = "manual"
    notes: str | None = None


class AuthLoginRequest(BaseModel):
    username: str
    password: str
    session_mode: Literal["cookie", "token", "both"] = "cookie"
    device_label: str | None = None
    client_name: str | None = None
    client_platform: str | None = None


class AuthSetupRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None
    bootstrap_token: str | None = None
    session_mode: Literal["cookie", "token", "both"] = "cookie"
    device_label: str | None = None
    client_name: str | None = None
    client_platform: str | None = None


class AuthApiKeyCreateRequest(BaseModel):
    label: str
    expires_at: datetime | None = None


class UserCreateRequest(BaseModel):
    username: str
    display_name: str | None = None
    password: str
    is_admin: bool = False


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    password: str | None = None
    is_admin: bool | None = None


class UserLocalePreferenceUpdateRequest(BaseModel):
    preferred_locale: Literal["en", "de"] | None = None


class SharedGroupCreateRequest(BaseModel):
    name: str
    group_type: Literal["household", "community"]


class SharedGroupUpdateRequest(BaseModel):
    name: str | None = None
    group_type: Literal["household", "community"] | None = None
    status: Literal["active", "archived"] | None = None


class SharedGroupMemberCreateRequest(BaseModel):
    user_id: str
    role: Literal["owner", "manager", "member"] = "member"


class SharedGroupMemberUpdateRequest(BaseModel):
    role: Literal["owner", "manager", "member"] | None = None
    membership_status: Literal["active", "removed"] | None = None


class MobileDeviceRegisterRequest(BaseModel):
    installation_id: str = Field(min_length=8, max_length=128)
    client_platform: Literal["ios", "android"]
    push_provider: Literal["apns", "fcm"]
    push_token: str = Field(min_length=16, max_length=4096)
    notifications_enabled: bool = True
    device_label: str | None = None
    client_name: str | None = None
    app_version: str | None = None
    locale: Literal["en", "de"] | None = None


class MobilePairingSessionCreateRequest(BaseModel):
    endpoint_url: str | None = None
    bridge_endpoint_url: str | None = None
    expires_in_seconds: int = Field(
        default=DEFAULT_PAIRING_EXPIRES_IN_SECONDS,
        ge=MIN_PAIRING_EXPIRES_IN_SECONDS,
        le=MAX_PAIRING_EXPIRES_IN_SECONDS,
    )
    transport: Literal["lan_http"] = MOBILE_DEFAULT_TRANSPORT


class MobilePairingHandshakeRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=128)
    device_name: str | None = None
    platform: Literal["ios", "android"]
    pairing_token: str = Field(min_length=16)
    public_key_fingerprint: str | None = Field(default=None, max_length=128)


class MobileManualTransactionCreateRequest(BaseModel):
    purchased_at: datetime | None = None
    merchant_name: str = Field(min_length=1, max_length=240)
    total_cents: int = Field(ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    note: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=120)
    idempotency_key: str | None = Field(default=None, max_length=160)


def _mobile_capture_status(ocr_status: str | None, review_status: str | None) -> str:
    if review_status == "needs_review":
        return "needs_review"
    if ocr_status in {"completed", "success"}:
        return "completed"
    if ocr_status in {"queued", "pending"}:
        return "processing_on_desktop"
    if ocr_status in {"processing", "starting_engine", "running"}:
        return "processing_on_desktop"
    if ocr_status in {"failed", "canceled"}:
        return "failed"
    return "uploaded"


def _serialize_mobile_transaction_item(item: TransactionItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "transaction_id": item.transaction_id,
        "line_no": item.line_no,
        "name": item.name,
        "qty": float(item.qty),
        "unit": item.unit,
        "unit_price_cents": item.unit_price_cents,
        "line_total_cents": item.line_total_cents,
        "category": item.category,
    }


def _serialize_mobile_budget_summary(summary: dict[str, Any]) -> dict[str, Any]:
    totals = summary.get("totals", {})
    period = summary.get("period", {})
    month = summary.get("month") or {}
    year = period.get("year")
    month_number = period.get("month")
    period_label = (
        f"{int(year):04d}-{int(month_number):02d}"
        if isinstance(year, int) and isinstance(month_number, int)
        else "Current period"
    )
    planned_outflow_cents = int(totals.get("planned_outflow_cents", 0) or 0)
    total_outflow_cents = int(totals.get("total_outflow_cents", 0) or 0)
    return {
        "year": period.get("year"),
        "month": period.get("month"),
        "period": period_label,
        "period_label": period_label,
        "currency": month.get("currency", "EUR"),
        "spent_cents": total_outflow_cents,
        "budget_cents": planned_outflow_cents,
        "category_summaries": [],
        "planned_income_cents": totals.get("planned_income_cents", 0),
        "actual_income_cents": totals.get("actual_income_cents", 0),
        "total_outflow_cents": total_outflow_cents,
        "remaining_cents": totals.get("remaining_cents", 0),
        "saved_cents": totals.get("saved_cents", 0),
        "savings_delta_cents": totals.get("savings_delta_cents", 0),
        "receipt_spend_cents": totals.get("receipt_spend_cents", 0),
        "manual_outflow_cents": totals.get("manual_outflow_cents", 0),
        "budget_rules": summary.get("budget_rules", []),
        "recurring": summary.get("recurring", {}),
        "cashflow": summary.get("cashflow", {}),
    }


def _serialize_mobile_capture(session: Session, capture: MobileCapture) -> dict[str, Any]:
    document = session.get(Document, capture.document_id) if capture.document_id else None
    if document is not None:
        capture.status = _mobile_capture_status(document.ocr_status, document.review_status)
    return {
        "capture_id": capture.mobile_capture_id,
        "mobile_capture_id": capture.mobile_capture_id,
        "desktop_capture_id": capture.capture_id,
        "document_id": capture.document_id,
        "job_id": capture.job_id,
        "transaction_id": document.transaction_id if document is not None else None,
        "status": capture.status,
        "message": capture.failure_reason,
        "failure_reason": capture.failure_reason,
        "file_name": capture.file_name,
        "mime_type": capture.mime_type,
        "sha256": capture.sha256,
        "uploaded_at": capture.uploaded_at.isoformat(),
        "updated_at": capture.updated_at.isoformat(),
        "ocr_status": document.ocr_status if document is not None else None,
        "review_status": document.review_status if document is not None else None,
    }


def _default_mobile_endpoint_url(request: Request) -> str:
    port = request.url.port or 80
    candidates: list[str] = []
    with suppress(Exception):
        candidates.append(socket.gethostbyname(socket.gethostname()))
    for candidate in candidates:
        if candidate and not candidate.startswith("127."):
            return f"{request.url.scheme}://{candidate}:{port}"
    return str(request.base_url).rstrip("/")


class SourceWorkspaceUpdateRequest(BaseModel):
    workspace_kind: Literal["personal", "shared_group"]
    shared_group_id: str | None = None


class ConnectorCascadeStartRequest(BaseModel):
    source_ids: list[str] = Field(min_length=1)
    full: bool = False


class ConnectorCascadeRetryRequest(BaseModel):
    full: bool | None = None
    include_skipped: bool = True


class ConnectorConfigUpdateRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    clear_secret_keys: list[str] = Field(default_factory=list)


class ConnectorBootstrapConfirmRequest(BaseModel):
    callback_url: str


class ConnectorUninstallRequest(BaseModel):
    purge_config: bool = False


class TransactionWorkspaceUpdateRequest(BaseModel):
    allocation_mode: Literal["personal", "shared_receipt", "split_items"]
    shared_group_id: str | None = None


class TransactionItemAllocationUpdateRequest(BaseModel):
    shared: bool


class SystemBackupRequest(BaseModel):
    output_dir: str | None = None
    include_documents: bool = True
    include_export_json: bool = True


UploadFormFile = Annotated[UploadFile, File(...)]
TransactionSortBy = Literal[
    "purchased_at", "merchant_name", "source_id", "total_gross_cents", "discount_total_cents"
]
TransactionSortDir = Literal["asc", "desc"]


def _parse_optional_iso_datetime(raw: str | None) -> datetime | None:
    if raw is None or raw.strip() == "":
        return None
    parsed = datetime.fromisoformat(raw.strip())
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _parse_to_date(raw: str | None) -> datetime | None:
    """Parse an upper-bound date string, treating bare dates (YYYY-MM-DD) as end-of-day.

    This ensures `to_date=2025-12-31` includes purchases made anywhere on that day,
    not just before midnight.
    """
    if raw is None or raw.strip() == "":
        return None
    s = raw.strip()
    # Bare date: no time component → set to 23:59:59 so <= filter includes the whole day
    if len(s) == 10 and "T" not in s and " " not in s:
        return datetime.fromisoformat(s).replace(hour=23, minute=59, second=59, tzinfo=UTC)
    parsed = datetime.fromisoformat(s)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _parse_optional_iso_date(raw: str | None) -> date | None:
    if raw is None or raw.strip() == "":
        return None
    return date.fromisoformat(raw.strip())


def _validate_tz_offset_minutes(value: int) -> int:
    if not -840 <= value <= 840:
        raise RuntimeError("tz_offset_minutes must be between -840 and 840")
    return value


def _validate_weekday(value: int | None) -> int | None:
    if value is not None and not 0 <= value <= 6:
        raise RuntimeError("weekday must be between 0 and 6")
    return value


def _validate_hour(value: int | None) -> int | None:
    if value is not None and not 0 <= value <= 23:
        raise RuntimeError("hour must be between 0 and 23")
    return value


def _to_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _manual_item_payload(
    items: list[ManualTransactionItemRequest],
    *,
    shared_group_id: str | None = None,
) -> list[ManualItemInput]:
    parsed: list[ManualItemInput] = []
    for item in items:
        qty = Decimal(str(item.qty))
        if qty <= Decimal("0"):
            raise RuntimeError("item qty must be greater than 0")
        if item.line_total_cents < 0:
            raise RuntimeError("item line_total_cents must be non-negative")
        parsed.append(
            ManualItemInput(
                name=item.name.strip(),
                line_total_cents=item.line_total_cents,
                qty=qty,
                unit=item.unit.strip() if item.unit else None,
                unit_price_cents=item.unit_price_cents,
                category=item.category.strip() if item.category else None,
                line_no=item.line_no,
                source_item_id=item.source_item_id.strip() if item.source_item_id else None,
                shared=item.shared,
                shared_group_id=shared_group_id if item.shared else None,
                raw_payload=item.raw_payload,
            )
        )
    return parsed


def _manual_discount_payload(
    discounts: list[ManualTransactionDiscountRequest],
) -> list[ManualDiscountInput]:
    parsed: list[ManualDiscountInput] = []
    for discount in discounts:
        if discount.amount_cents <= 0:
            raise RuntimeError("discount amount_cents must be greater than 0")
        parsed.append(
            ManualDiscountInput(
                source_label=discount.source_label.strip(),
                amount_cents=discount.amount_cents,
                scope=discount.scope,
                transaction_item_line_no=discount.transaction_item_line_no,
                source_discount_code=(
                    discount.source_discount_code.strip() if discount.source_discount_code else None
                ),
                kind=discount.kind.strip() or "manual",
                subkind=discount.subkind.strip() if discount.subkind else None,
                funded_by=discount.funded_by.strip() if discount.funded_by else "unknown",
                is_loyalty_program=discount.is_loyalty_program,
                raw_payload=discount.raw_payload,
            )
        )
    return parsed


def _run_periodic_connector_sync(
    app: FastAPI,
    *,
    source_ids: list[str],
    interval: int,
    stop_event: threading.Event,
    config: Any,
) -> None:
    """Background thread: runs incremental connector sync every `interval` seconds."""
    logger = logging.getLogger(__name__)
    logger.info("connector.live_sync.started interval=%s source_ids=%s", interval, source_ids)
    while not stop_event.wait(interval):
        cascade_sessions = get_connector_cascade_sessions(app)
        if any(_connector_cascade_is_active(cascade) for cascade in cascade_sessions.values()):
            logger.info("connector.live_sync.skipped (cascade active)")
            continue
        for source_id in source_ids:
            try:
                sync_sessions = get_connector_command_sessions(app, kind="sync")
                existing = sync_sessions.get(source_id)
                if existing is not None and _connector_bootstrap_is_running(existing):
                    logger.info("connector.live_sync.skipped source_id=%s (already running)", source_id)
                    continue
                command = _connector_command(
                    config,
                    source_id=source_id,
                    operation="sync",
                )
                if command is None:
                    continue
                sync_session = _start_connector_command_session(
                    app,
                    source_id=source_id,
                    command=command,
                    config=config,
                    session_kind="sync",
                    thread_name=f"connector-sync-{source_id}",
                )
                logger.info(
                    "connector.live_sync.triggered source_id=%s pid=%s",
                    source_id,
                    sync_session.process.pid,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("connector.live_sync.error source_id=%s error=%s", source_id, exc)
    logger.info("connector.live_sync.stopped")


def create_app(
    *,
    config: AppConfig | None = None,
    config_path: Path | None = None,
    db_override: Path | None = None,
    bind_host: str | None = None,
) -> FastAPI:
    runtime_context = _build_runtime_context(
        config=config,
        config_path=config_path,
        db_override=db_override,
        bind_host=bind_host,
    )
    base_config = runtime_context.config

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        config = runtime_context.config
        sessions = runtime_context.sessions
        validate_config(config, bind_host=runtime_context.bind_host)
        _validate_bootstrap_startup_guard(
            config=config,
            sessions=sessions,
            bind_host=runtime_context.bind_host,
        )
        scheduler: AutomationScheduler | None = None
        scheduler = AutomationScheduler(session_factory=sessions, config=config)
        scheduler.start()
        app.state.automation_scheduler = scheduler
        live_sync_stop = threading.Event()
        app.state.connector_live_sync_stop = live_sync_stop
        if config.connector_live_sync_enabled:
            live_sync_thread = threading.Thread(
                target=_run_periodic_connector_sync,
                kwargs={
                    "app": app,
                    "source_ids": ["lidl_plus_de"],
                    "interval": config.connector_live_sync_interval_seconds,
                    "stop_event": live_sync_stop,
                    "config": config,
                },
                daemon=True,
                name="connector-live-sync",
            )
            live_sync_thread.start()
        try:
            yield
        finally:
            bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
            for session in bootstrap_sessions.values():
                try:
                    _terminate_connector_bootstrap(session)
                except Exception:  # noqa: BLE001
                    pass
            sync_sessions = get_connector_command_sessions(app, kind="sync")
            for session in sync_sessions.values():
                try:
                    _terminate_connector_bootstrap(session)
                except Exception:  # noqa: BLE001
                    pass
            cascade_sessions = get_connector_cascade_sessions(app)
            for cascade in cascade_sessions.values():
                cascade.cancel_event.set()
                for source_state in cascade.sources.values():
                    if (
                        source_state.bootstrap is not None
                        and _connector_bootstrap_is_running(source_state.bootstrap)
                    ):
                        with suppress(Exception):
                            _terminate_connector_bootstrap(source_state.bootstrap)
                    if source_state.sync is not None and _connector_bootstrap_is_running(
                        source_state.sync
                    ):
                        with suppress(Exception):
                            _terminate_connector_bootstrap(source_state.sync)
                if cascade.worker_thread is not None and cascade.worker_thread.is_alive():
                    cascade.worker_thread.join(timeout=2)
            try:
                _stop_vnc_runtime(app)
            except Exception:  # noqa: BLE001
                pass
            live_sync_stop.set()
            if scheduler is not None:
                scheduler.stop()

    app = FastAPI(title="lidltool OCR API", version="1", lifespan=lifespan)
    initialize_http_api_state(app)
    app.state.request_context = runtime_context

    if base_config.http_cors_enabled and base_config.http_cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=base_config.http_cors_allowed_origins,
            allow_methods=base_config.http_cors_allowed_methods,
            allow_headers=base_config.http_cors_allowed_headers,
            allow_credentials=base_config.http_cors_allow_credentials,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(exc)

    @app.middleware("http")
    async def request_metrics(request: Request, call_next):  # type: ignore[no-untyped-def]
        override_response = await _reject_runtime_override_usage(request)
        if override_response is not None:
            return override_response
        legacy_key_response = await _reject_legacy_api_key_usage(request)
        if legacy_key_response is not None:
            return legacy_key_response
        rate_limit_state = _evaluate_rate_limit(request, base_config)
        if rate_limit_state is not None and rate_limit_state.throttled:
            return JSONResponse(
                status_code=429,
                headers=_rate_limit_headers(
                    rate_limit_state, window_s=max(int(base_config.http_rate_limit_window_s), 1)
                ),
                content=_response(
                    False,
                    result=None,
                    warnings=[],
                    error="rate limit exceeded; retry after Retry-After seconds",
                    error_code="rate_limited",
                ),
            )
        started_at = time.monotonic()
        response = await call_next(request)
        if rate_limit_state is not None:
            rate_limit_headers = _rate_limit_headers(
                rate_limit_state, window_s=max(int(base_config.http_rate_limit_window_s), 1)
            )
            for header_name, header_value in rate_limit_headers.items():
                response.headers[header_name] = header_value
        route_template = getattr(request.scope.get("route"), "path", request.url.path)
        try:
            context = getattr(request.state, "request_context", None)
            if not isinstance(context, RequestContext):
                context = _resolve_request_context(request)
            record_endpoint_metric(
                context.sessions,
                route=str(route_template),
                method=request.method,
                status_code=int(response.status_code),
                duration_ms=int((time.monotonic() - started_at) * 1000),
                source=request.query_params.get("source"),
            )
        except Exception:  # noqa: BLE001
            # Metrics must never break API behavior.
            pass
        return response

    @app.get("/api/v1/health")
    def health() -> Any:
        return _response(
            True,
            result={
                "status": "alive",
                "ready": True,
                "pid": os.getpid(),
                "checks": {"process": {"ok": True}},
            },
            warnings=[],
            error=None,
        )

    @app.get("/api/v1/ready")
    def ready(
        request: Request,
    ) -> JSONResponse:
        try:
            context = _resolve_request_context(request)
            db_ok, db_detail = _readiness_db_check(context.sessions)
            storage_ok, storage_detail = _readiness_storage_check(context.config)
            scheduler_ok, scheduler_detail = _readiness_scheduler_check(app, context.config)
            checks = {
                "db": {"ok": db_ok},
                "storage": {"ok": storage_ok},
                "scheduler": {"ok": scheduler_ok},
            }
            ready_state = all(item["ok"] for item in checks.values())
            status_code = 200 if ready_state else 503
            return JSONResponse(
                status_code=status_code,
                content=_response(
                    ready_state,
                    result={
                        "status": "ready" if ready_state else "degraded",
                        "ready": ready_state,
                        "checks": checks,
                    },
                    warnings=[],
                    error=None if ready_state else "service not ready",
                    error_code=None if ready_state else "service_not_ready",
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/auth/setup-required")
    def auth_setup_required(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                required = human_user_count(session) == 0
            return _response(
                True,
                result={
                    "required": required,
                    "bootstrap_token_required": required and _bootstrap_token_required(context.config),
                },
                warnings=[],
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/auth/setup")
    def auth_setup(
        request: Request,
        payload: AuthSetupRequest,
    ) -> JSONResponse:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                if human_user_count(session) > 0:
                    raise RuntimeError("setup already completed")
                _enforce_initial_bootstrap_guard(
                    request=request,
                    config=context.config,
                    provided_token=_provided_bootstrap_token(request, payload.bootstrap_token),
                )
                user = create_local_user(
                    session,
                    username=payload.username,
                    password=payload.password,
                    display_name=payload.display_name,
                    is_admin=True,
                )
                session_record = create_user_session(
                    session,
                    user=user,
                    metadata=_session_client_metadata(
                        request=request,
                        session_mode=payload.session_mode,
                        device_label=payload.device_label,
                        client_name=payload.client_name,
                        client_platform=payload.client_platform,
                    ),
                )
                token = issue_session_token(
                    user=user,
                    session_id=session_record.session_id,
                    config=context.config,
                )
                result = _auth_success_result(
                    user=user,
                    session_record=session_record,
                    token=token if payload.session_mode in {SESSION_MODE_TOKEN, SESSION_MODE_BOTH} else None,
                )
            response = JSONResponse(
                content=_response(True, result=result, warnings=[], error=None),
                status_code=200,
            )
            if payload.session_mode in {SESSION_MODE_COOKIE, SESSION_MODE_BOTH} and token is not None:
                set_session_cookie(response, token=token, request=request, config=context.config)
            return response
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/auth/login")
    def auth_login(
        request: Request,
        payload: AuthLoginRequest,
    ) -> JSONResponse:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                if human_user_count(session) == 0:
                    raise HTTPException(status_code=503, detail="setup required")
                user = get_user_by_username(session, username=payload.username)
                if (
                    user is None
                    or user.username == SERVICE_USERNAME
                    or not verify_password(payload.password, user.password_hash)
                ):
                    raise HTTPException(status_code=401, detail="invalid username or password")
                session_record = create_user_session(
                    session,
                    user=user,
                    metadata=_session_client_metadata(
                        request=request,
                        session_mode=payload.session_mode,
                        device_label=payload.device_label,
                        client_name=payload.client_name,
                        client_platform=payload.client_platform,
                    ),
                )
                token = issue_session_token(
                    user=user,
                    session_id=session_record.session_id,
                    config=context.config,
                )
                result = _auth_success_result(
                    user=user,
                    session_record=session_record,
                    token=token if payload.session_mode in {SESSION_MODE_TOKEN, SESSION_MODE_BOTH} else None,
                )
            response = JSONResponse(
                content=_response(True, result=result, warnings=[], error=None),
                status_code=200,
            )
            if payload.session_mode in {SESSION_MODE_COOKIE, SESSION_MODE_BOTH} and token is not None:
                set_session_cookie(response, token=token, request=request, config=context.config)
            return response
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/auth/logout")
    def auth_logout(
        request: Request,
    ) -> JSONResponse:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                revoke_user_session(
                    session,
                    record=auth_context.session_record,
                    reason="user_logout",
                )
                session_id = auth_context.session_record.session_id
            response = JSONResponse(
                content=_response(
                    True,
                    result={"logged_out": True, "revoked": True, "session_id": session_id},
                )
            )
            clear_session_cookie(response, request=request, config=context.config)
            return response
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/auth/me")
    def auth_me(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = _serialize_current_user(auth_context.user)
                result["session"] = (
                    serialize_user_session(auth_context.session_record, current=True)
                    if auth_context.session_record is not None
                    else None
                )
                result["session_mode"] = (
                    auth_context.session_record.auth_transport
                    if auth_context.session_record is not None
                    else None
                )
                result["available_auth_transports"] = (
                    available_auth_transports(auth_context.session_record.auth_transport)
                    if auth_context.session_record is not None
                    else [auth_context.auth_transport]
                )
                result["auth_transport"] = auth_context.auth_transport
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/auth/sessions")
    def auth_list_sessions(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                current_session_id = (
                    auth_context.session_record.session_id
                    if auth_context.session_record is not None
                    else None
                )
                sessions_payload = [
                    serialize_user_session(
                        record,
                        current=(record.session_id == current_session_id),
                    )
                    for record in list_active_user_sessions(session, user_id=auth_context.user.user_id)
                ]
                result = _collection_result(
                    result={"count": len(sessions_payload), "items": sessions_payload},
                    alias_key="sessions",
                )
                result["current_session_id"] = current_session_id
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/auth/sessions/{session_id}")
    def auth_revoke_session(
        request: Request,
        session_id: str,
    ) -> JSONResponse:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                target = session.get(UserSession, session_id)
                if target is None or target.user_id != auth_context.user.user_id:
                    raise RuntimeError("session not found")
                revoke_user_session(session, record=target, reason="user_revoked")
                result = {
                    "revoked": True,
                    "session": serialize_user_session(
                        target,
                        current=(
                            auth_context.session_record is not None
                            and auth_context.session_record.session_id == target.session_id
                        ),
                    ),
                }
            response = JSONResponse(content=_response(True, result=result, warnings=[], error=None))
            session_payload = result["session"]
            if isinstance(session_payload, dict) and session_payload.get("current") is True:
                clear_session_cookie(response, request=request, config=context.config)
            return response
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/users/me/preferences")
    def patch_my_user_preferences(
        request: Request,
        payload: UserLocalePreferenceUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                current_user = auth_context.user
                current_user.preferred_locale = _normalize_supported_locale(payload.preferred_locale)
                current_user.updated_at = datetime.now(tz=UTC)
                session.flush()
                result = {"preferred_locale": _normalize_supported_locale(current_user.preferred_locale)}
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/mobile/devices")
    def get_mobile_device_registrations(
        request: Request,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = list_mobile_devices(
                    session,
                    user_id=auth_context.user.user_id,
                    limit=limit,
                    offset=offset,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.put("/api/v1/mobile/devices/current")
    def put_current_mobile_device(
        request: Request,
        payload: MobileDeviceRegisterRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = upsert_mobile_device(
                    session,
                    user_id=auth_context.user.user_id,
                    session_id=(
                        auth_context.session_record.session_id
                        if auth_context.session_record is not None
                        else None
                    ),
                    installation_id=payload.installation_id,
                    client_platform=payload.client_platform,
                    push_provider=payload.push_provider,
                    push_token=payload.push_token,
                    notifications_enabled=payload.notifications_enabled,
                    device_label=payload.device_label,
                    client_name=payload.client_name,
                    app_version=payload.app_version,
                    locale=payload.locale,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/mobile/devices")
    def post_mobile_device(
        request: Request,
        payload: MobileDeviceRegisterRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = upsert_mobile_device(
                    session,
                    user_id=auth_context.user.user_id,
                    session_id=(
                        auth_context.session_record.session_id
                        if auth_context.session_record is not None
                        else None
                    ),
                    installation_id=payload.installation_id,
                    client_platform=payload.client_platform,
                    push_provider=payload.push_provider,
                    push_token=payload.push_token,
                    notifications_enabled=payload.notifications_enabled,
                    device_label=payload.device_label,
                    client_name=payload.client_name,
                    app_version=payload.app_version,
                    locale=payload.locale,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/mobile/devices/current")
    def delete_current_mobile_device_registration(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                if auth_context.session_record is None:
                    raise RuntimeError("authenticated session not found")
                result = delete_mobile_devices_for_session(
                    session,
                    user_id=auth_context.user.user_id,
                    session_id=auth_context.session_record.session_id,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/mobile/devices/{device_id}")
    def delete_mobile_device_registration(
        request: Request,
        device_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = delete_mobile_device(
                    session,
                    user_id=auth_context.user.user_id,
                    device_id=device_id,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/mobile-pair/v1/sessions")
    def create_mobile_pairing_session(
        request: Request,
        payload: MobilePairingSessionCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                endpoint_url = (
                    (payload.bridge_endpoint_url or "").strip()
                    or (payload.endpoint_url or "").strip()
                    or _default_mobile_endpoint_url(request)
                )
                result = create_pairing_session(
                    session,
                    endpoint_url=endpoint_url,
                    created_by_user_id=auth_context.user.user_id,
                    expires_in_seconds=payload.expires_in_seconds,
                    transport=payload.transport,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/mobile-pair/v1/handshake")
    def mobile_pairing_handshake(
        payload: MobilePairingHandshakeRequest,
    ) -> Any:
        try:
            context = runtime_context
            with session_scope(context.sessions) as session:
                result, _ = complete_pairing_handshake(
                    session,
                    pairing_token=payload.pairing_token,
                    device_id=payload.device_id,
                    device_name=payload.device_name,
                    platform=payload.platform,
                    public_key_fingerprint=payload.public_key_fingerprint,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/mobile-captures/v1")
    async def upload_mobile_capture(
        request: Request,
        file: UploadFormFile,
        capture_id: str | None = Form(default=None),
        mobile_capture_id: str | None = Form(default=None),
        captured_at: str | None = Form(default=None),
        metadata_json: str | None = Form(default=None),
        metadata: str | None = Form(default=None),
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            bearer_token = _header_api_key(request)
            payload = await file.read()
            mime_type = file.content_type or "application/octet-stream"
            loaded_metadata: dict[str, Any] = {}
            raw_metadata = metadata_json or metadata
            if raw_metadata:
                loaded = json.loads(raw_metadata)
                if isinstance(loaded, dict):
                    loaded_metadata.update(loaded)
            resolved_capture_id = (
                capture_id
                or mobile_capture_id
                or loaded_metadata.get("mobile_capture_id")
                or loaded_metadata.get("capture_id")
            )
            if not isinstance(resolved_capture_id, str) or not resolved_capture_id.strip():
                raise RuntimeError("capture_id is required")
            capture_id = resolved_capture_id.strip()
            mobile_metadata: dict[str, Any] = {"mobile_capture_id": capture_id}
            if captured_at:
                mobile_metadata["captured_at"] = captured_at
            mobile_metadata.update(loaded_metadata)
            storage = DocumentStorage(app_config)
            storage_uri, sha256 = storage.store(
                file_name=file.filename or f"{capture_id}.bin",
                mime_type=mime_type,
                payload=payload,
            )
            with session_scope(context.sessions) as session:
                paired = require_paired_device(session, bearer_token=bearer_token)
                existing = session.execute(
                    select(MobileCapture).where(
                        MobileCapture.paired_device_id == paired.paired_device_id,
                        MobileCapture.mobile_capture_id == capture_id,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return _response(
                        True,
                        result=_serialize_mobile_capture(session, existing),
                        warnings=[],
                        error=None,
                    )
                ensured_source, source_account = ensure_ocr_source(session, owner_user_id=paired.user_id)
                mobile_metadata.setdefault("uploader_user_id", paired.user_id)
                mobile_metadata.setdefault("paired_device_id", paired.paired_device_id)
                document = Document(
                    transaction_id=None,
                    source_id=ensured_source.id,
                    shared_group_id=None,
                    storage_uri=storage_uri,
                    mime_type=mime_type,
                    sha256=sha256,
                    file_name=file.filename,
                    ocr_status="pending",
                    metadata_json=mobile_metadata,
                    created_at=datetime.now(tz=UTC),
                )
                session.add(document)
                session.flush()
                job = IngestionJob(
                    source_id=ensured_source.id,
                    source_account_id=source_account.id if source_account is not None else None,
                    status="queued",
                    trigger_type="manual",
                    idempotency_key=hashlib.sha256(
                        f"ocr|{document.id}|{capture_id}".encode("utf-8")
                    ).hexdigest(),
                    summary={
                        "job_type": "ocr_process",
                        "document_id": document.id,
                        "progress": {
                            "phase": "queued",
                            "processed": 0,
                            "total": 1,
                            "percent": 0,
                        },
                        "warnings": [],
                        "timeline": [
                            {
                                "event": "queued",
                                "status": "queued",
                                "message": "ocr job queued",
                                "timestamp": datetime.now(tz=UTC).isoformat(),
                            }
                        ],
                    },
                )
                session.add(job)
                session.flush()
                if job.status == "queued":
                    document.ocr_status = "queued"
                capture = MobileCapture(
                    paired_device_id=paired.paired_device_id,
                    mobile_capture_id=capture_id,
                    document_id=document.id,
                    job_id=job.id,
                    file_name=file.filename,
                    mime_type=mime_type,
                    sha256=sha256,
                    status=_mobile_capture_status(document.ocr_status, document.review_status),
                    metadata_json=mobile_metadata,
                    uploaded_at=datetime.now(tz=UTC),
                    created_at=datetime.now(tz=UTC),
                    updated_at=datetime.now(tz=UTC),
                )
                session.add(capture)
                session.flush()
                result = _serialize_mobile_capture(session, capture)
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/mobile-sync/v1/changes")
    def mobile_sync_changes(
        request: Request,
        cursor: str | None = None,
        limit: int = 100,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            now = datetime.now(tz=UTC)
            clamped_limit = min(max(limit, 1), 200)
            with session_scope(context.sessions) as session:
                paired = require_paired_device(session, bearer_token=_header_api_key(request))
                visibility = VisibilityContext(
                    user_id=paired.user_id,
                    is_service=False,
                    scope="personal",
                    workspace_kind="personal",
                )
                tx_result = search_transactions(
                    session,
                    sort_by="purchased_at",
                    sort_dir="desc",
                    limit=clamped_limit,
                    offset=0,
                    visibility=visibility,
                )
                transaction_ids = [item["id"] for item in tx_result["items"]]
                mobile_transactions = []
                for item in tx_result["items"]:
                    total_cents = int(item.get("total_gross_cents", 0) or 0)
                    mobile_transactions.append(
                        {
                            **item,
                            "merchant_name": item.get("merchant_name") or item.get("store_name") or "Unknown merchant",
                            "total_cents": total_cents,
                            "total_gross_cents": total_cents,
                            "category": item.get("category"),
                            "note": item.get("note"),
                            "needs_review": bool(item.get("needs_review", False)),
                            "updated_at": item.get("updated_at"),
                        }
                    )
                items = [
                    _serialize_mobile_transaction_item(row)
                    for row in session.execute(
                        select(TransactionItem)
                        .where(TransactionItem.transaction_id.in_(transaction_ids))
                        .order_by(TransactionItem.transaction_id.asc(), TransactionItem.line_no.asc())
                    ).scalars().all()
                ] if transaction_ids else []
                budget = monthly_budget_summary(
                    session,
                    user_id=paired.user_id,
                    year=now.year,
                    month=now.month,
                    visibility=visibility,
                )
                captures = session.execute(
                    select(MobileCapture)
                    .where(MobileCapture.paired_device_id == paired.paired_device_id)
                    .order_by(MobileCapture.updated_at.desc(), MobileCapture.created_at.desc())
                    .limit(clamped_limit)
                ).scalars().all()
                result = {
                    "protocol_version": MOBILE_PROTOCOL_VERSION,
                    "cursor": now.isoformat(),
                    "previous_cursor": cursor,
                    "server_time": now.isoformat(),
                    "transactions": mobile_transactions,
                    "transaction_items": items,
                    "budget_summary": _serialize_mobile_budget_summary(budget),
                    "capture_statuses": [
                        _serialize_mobile_capture(session, capture) for capture in captures
                    ],
                }
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/mobile-sync/v1/manual-transactions")
    def create_mobile_manual_transaction(
        request: Request,
        payload: MobileManualTransactionCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                paired = require_paired_device(session, bearer_token=_header_api_key(request))
                paired_user_id = paired.user_id
                paired_device_id = paired.paired_device_id
            service = ManualIngestService(session_factory=sessions)
            purchased_at = payload.purchased_at or datetime.now(tz=UTC)
            mobile_source_id = f"{MANUAL_SOURCE_ID}:mobile"
            manual_input = ManualTransactionInput(
                purchased_at=_to_utc_datetime(purchased_at),
                merchant_name=payload.merchant_name.strip(),
                total_gross_cents=payload.total_cents,
                source_id=mobile_source_id,
                source_kind="manual",
                source_display_name="Mobile Manual Entries",
                source_account_ref="mobile",
                source_transaction_id=None,
                idempotency_key=payload.idempotency_key,
                user_id=paired_user_id,
                shared_group_id=None,
                currency=payload.currency.strip().upper(),
                discount_total_cents=None,
                allocation_mode="personal",
                confidence=1.0,
                items=[
                    ManualItemInput(
                        name=payload.note.strip() if payload.note and payload.note.strip() else payload.merchant_name.strip(),
                        line_total_cents=payload.total_cents,
                        qty=Decimal("1.0"),
                        unit=None,
                        unit_price_cents=payload.total_cents,
                        category=payload.category,
                        line_no=1,
                        source_item_id=None,
                        shared_group_id=None,
                        raw_payload={"source": "mobile_manual"},
                    )
                ],
                discounts=[],
                raw_payload={"source": "mobile_manual", "note": payload.note},
                ingest_channel="mobile_manual_api",
            )
            create_result = service.ingest_transaction(
                payload=manual_input,
                actor_type="mobile_device",
                actor_id=paired_device_id,
                audit_action="transaction.mobile_manual_ingested",
                reason="mobile manual expense",
            )
            with session_scope(sessions) as session:
                visibility = VisibilityContext(
                    user_id=paired_user_id,
                    is_service=False,
                    scope="personal",
                    workspace_kind="personal",
                )
                details = transaction_detail(
                    session,
                    transaction_id=str(create_result["transaction_id"]),
                    visibility=visibility,
                )
            create_result["transaction"] = details["transaction"] if details else None
            return _response(True, result=create_result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/auth/keys")
    def auth_list_keys(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request, session=session, config=context.config
                )
                current_user = auth_context.user
                keys = (
                    session.execute(
                        select(UserApiKey)
                        .where(UserApiKey.user_id == current_user.user_id)
                        .order_by(UserApiKey.created_at.desc(), UserApiKey.key_id.desc())
                    )
                    .scalars()
                    .all()
                )
                result = {"keys": [_serialize_api_key(key) for key in keys], "count": len(keys)}
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/auth/keys")
    def auth_create_key(
        request: Request,
        payload: AuthApiKeyCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request, session=session, config=context.config
                )
                current_user = auth_context.user
                expires_at = _to_utc_datetime(payload.expires_at) if payload.expires_at else None
                key, plain_token = create_user_agent_key(
                    session,
                    user_id=current_user.user_id,
                    label=payload.label,
                    expires_at=expires_at,
                )
                result = {
                    "api_key": plain_token,
                    "key": _serialize_api_key(key),
                }
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/auth/keys/{key_id}")
    def auth_revoke_key(
        request: Request,
        key_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request, session=session, config=context.config
                )
                current_user = auth_context.user
                key = session.get(UserApiKey, key_id)
                if key is None:
                    raise RuntimeError("API key not found")
                if not current_user.is_admin and key.user_id != current_user.user_id:
                    raise RuntimeError("API key not found")
                key.is_active = False
                session.flush()
                result = {"key_id": key.key_id, "revoked": True}
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/users")
    def list_users(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                    admin_required=True,
                )
                users = (
                    session.execute(
                        select(User)
                        .where(User.username != SERVICE_USERNAME)
                        .order_by(User.username.asc())
                    )
                    .scalars()
                    .all()
                )
                result = {"users": [_serialize_user(user) for user in users], "count": len(users)}
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/users")
    def create_user(
        request: Request,
        payload: UserCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                    admin_required=True,
                )
                user = create_local_user(
                    session,
                    username=payload.username,
                    password=payload.password,
                    display_name=payload.display_name,
                    is_admin=payload.is_admin,
                )
                result = _serialize_user(user)
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/users/{user_id}")
    def patch_user(
        request: Request,
        user_id: str,
        payload: UserUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                    admin_required=True,
                )
                current_user = auth_context.user
                user = session.get(User, user_id)
                if user is None or user.username == SERVICE_USERNAME:
                    raise RuntimeError("user not found")

                if payload.display_name is not None:
                    user.display_name = payload.display_name.strip() or None
                if payload.password is not None:
                    set_user_password(session, user=user, password=payload.password)
                    revoke_user_sessions_for_user(
                        session,
                        user_id=user.user_id,
                        reason="password_changed",
                        exclude_session_id=(
                            auth_context.session_record.session_id
                            if auth_context.session_record is not None
                            and auth_context.user.user_id == user.user_id
                            else None
                        ),
                    )
                if payload.is_admin is not None:
                    if (
                        user.is_admin
                        and not payload.is_admin
                        and user.user_id == current_user.user_id
                    ):
                        raise RuntimeError("cannot remove admin privileges from current user")
                    if user.is_admin and not payload.is_admin:
                        admin_count = int(
                            session.execute(
                                select(func.count(User.user_id)).where(
                                    User.is_admin.is_(True),
                                    User.username != SERVICE_USERNAME,
                                )
                            ).scalar_one()
                        )
                        if admin_count <= 1:
                            raise RuntimeError("at least one admin user is required")
                    user.is_admin = payload.is_admin
                user.updated_at = datetime.now(tz=UTC)
                session.flush()
                result = _serialize_user(user)
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/users/{user_id}")
    def delete_user(
        request: Request,
        user_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                    admin_required=True,
                )
                current_user = auth_context.user
                user = session.get(User, user_id)
                if user is None or user.username == SERVICE_USERNAME:
                    raise RuntimeError("user not found")
                if user.user_id == current_user.user_id:
                    raise RuntimeError("cannot delete current user")
                if user.is_admin:
                    admin_count = int(
                        session.execute(
                            select(func.count(User.user_id)).where(
                                User.is_admin.is_(True),
                                User.username != SERVICE_USERNAME,
                            )
                        ).scalar_one()
                    )
                    if admin_count <= 1:
                        raise RuntimeError("at least one admin user is required")

                owns_sources = (
                    session.execute(
                        select(Source.id).where(Source.user_id == user.user_id).limit(1)
                    ).scalar_one_or_none()
                    is not None
                )
                owns_transactions = (
                    session.execute(
                        select(Transaction.id).where(Transaction.user_id == user.user_id).limit(1)
                    ).scalar_one_or_none()
                    is not None
                )
                if owns_sources or owns_transactions:
                    raise RuntimeError("cannot delete user with owned data")

                session.delete(user)
                result = {"user_id": user_id, "deleted": True}
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/shared-groups/user-directory")
    def get_shared_group_user_directory(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = list_shared_group_user_directory(session)
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/shared-groups")
    def get_shared_groups(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = list_shared_groups(session, user=auth_context.user)
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/shared-groups")
    def post_shared_group(
        request: Request,
        payload: SharedGroupCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = create_shared_group(
                    session,
                    creator=auth_context.user,
                    name=payload.name,
                    group_type=payload.group_type,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/shared-groups/{group_id}")
    def get_shared_group(
        request: Request,
        group_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = get_shared_group_detail(session, user=auth_context.user, group_id=group_id)
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/shared-groups/{group_id}")
    def patch_shared_group(
        request: Request,
        group_id: str,
        payload: SharedGroupUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = update_shared_group(
                    session,
                    actor=auth_context.user,
                    group_id=group_id,
                    name=payload.name,
                    group_type=payload.group_type,
                    status=payload.status,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/shared-groups/{group_id}/members")
    def post_shared_group_member(
        request: Request,
        group_id: str,
        payload: SharedGroupMemberCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = add_shared_group_member(
                    session,
                    actor=auth_context.user,
                    group_id=group_id,
                    user_id=payload.user_id,
                    role=payload.role,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/shared-groups/{group_id}/members/{user_id}")
    def patch_shared_group_member(
        request: Request,
        group_id: str,
        user_id: str,
        payload: SharedGroupMemberUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = update_shared_group_member(
                    session,
                    actor=auth_context.user,
                    group_id=group_id,
                    user_id=user_id,
                    role=payload.role,
                    membership_status=payload.membership_status,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/shared-groups/{group_id}/members/{user_id}")
    def delete_shared_group_member(
        request: Request,
        group_id: str,
        user_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=context.config,
                )
                result = remove_shared_group_member(
                    session,
                    actor=auth_context.user,
                    group_id=group_id,
                    user_id=user_id,
                )
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/system/backup")
    def run_system_backup(
        request: Request,
        payload: SystemBackupRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            with session_scope(context.sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=app_config,
                    admin_required=True,
                )
                current_user = auth_context.user

                timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
                if payload.output_dir and payload.output_dir.strip():
                    output_dir = Path(payload.output_dir.strip()).expanduser().resolve()
                else:
                    output_dir = (app_config.config_dir / "desktop-backups" / f"backup-{timestamp}").resolve()

                output_dir.mkdir(parents=True, exist_ok=True)
                if any(output_dir.iterdir()):
                    raise RuntimeError(f"backup output directory must be empty: {output_dir}")

                backup_result = backup_database(
                    app_config, output_dir, include_documents=payload.include_documents
                )
                copied: list[str] = [str(backup_result.db_artifact)]
                skipped: list[str] = []

                token_artifact: str | None = None
                if backup_result.token_artifact:
                    token_artifact = str(backup_result.token_artifact)
                    copied.append(token_artifact)
                else:
                    skipped.append("token file not found")

                documents_artifact: str | None = None
                if payload.include_documents:
                    if backup_result.documents_artifact:
                        documents_artifact = str(backup_result.documents_artifact)
                        copied.append(documents_artifact)
                    else:
                        skipped.append("documents directory not found")
                else:
                    skipped.append("documents excluded by request")

                credential_key_artifact: str | None = None
                credential_key = (
                    os.getenv("LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY")
                    or app_config.credential_encryption_key
                )
                if credential_key and credential_key.strip():
                    key_artifact = output_dir / "credential_encryption_key.txt"
                    key_artifact.write_text(f"{credential_key.strip()}\n", encoding="utf-8")
                    credential_key_artifact = str(key_artifact)
                    copied.append(credential_key_artifact)
                else:
                    skipped.append("credential encryption key not available")

                export_artifact: str | None = None
                export_records: int | None = None
                if payload.include_export_json:
                    export_payload = export_receipts(session)
                    export_file = output_dir / "receipts-export.json"
                    export_file.write_text(
                        json.dumps(export_payload, indent=2, default=str), encoding="utf-8"
                    )
                    export_artifact = str(export_file)
                    export_records = len(export_payload)
                    copied.append(export_artifact)

                manifest_path = output_dir / "backup-manifest.json"
                manifest_payload = {
                    "created_at": datetime.now(tz=UTC).isoformat(),
                    "requested_by_user_id": current_user.user_id,
                    "provider": backup_result.provider,
                    "output_dir": str(output_dir),
                    "db_artifact": str(backup_result.db_artifact),
                    "token_artifact": token_artifact,
                    "documents_artifact": documents_artifact,
                    "credential_key_artifact": credential_key_artifact,
                    "export_artifact": export_artifact,
                    "export_records": export_records,
                    "include_documents": payload.include_documents,
                    "include_export_json": payload.include_export_json,
                    "copied": copied,
                    "skipped": skipped,
                }
                manifest_path.write_text(
                    json.dumps(manifest_payload, indent=2), encoding="utf-8"
                )
                copied.append(str(manifest_path))

                result = {
                    "provider": backup_result.provider,
                    "output_dir": str(output_dir),
                    "db_artifact": str(backup_result.db_artifact),
                    "token_artifact": token_artifact,
                    "documents_artifact": documents_artifact,
                    "credential_key_artifact": credential_key_artifact,
                    "export_artifact": export_artifact,
                    "export_records": export_records,
                    "manifest_path": str(manifest_path),
                    "copied": copied,
                    "skipped": skipped,
                }
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/documents/upload")
    async def upload_document(
        request: Request,
        file: UploadFormFile,
        source: str | None = Form(default=None),
        scope: str = Form(default="personal"),
        metadata_json: str | None = Form(default=None),
        legacy_api_key: str | None = Form(default=None, alias="api_key"),
    ) -> Any:
        try:
            _reject_legacy_form_api_key(legacy_api_key)
            await _reject_form_runtime_override_usage(request)
            context = _resolve_request_context(request)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)
            storage = DocumentStorage(app_config)
            payload = await file.read()
            mime_type = file.content_type or "application/octet-stream"
            storage_uri, sha256 = storage.store(
                file_name=file.filename or "upload.bin",
                mime_type=mime_type,
                payload=payload,
            )
            metadata: dict[str, Any] = {}
            if metadata_json:
                loaded = json.loads(metadata_json)
                if isinstance(loaded, dict):
                    metadata = loaded
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                normalized_source = (source or "").strip() or None
                if normalized_source == OCR_SOURCE_ID:
                    ensured_source, _ = ensure_ocr_source(
                        session,
                        owner_user_id=current_user.user_id,
                    )
                    if visibility.shared_group_id and ensured_source.shared_group_id is None:
                        ensured_source.shared_group_id = visibility.shared_group_id
                    validated_source = ensured_source.id
                else:
                    validated_source = _validate_upload_source(session, normalized_source)
                if (
                    validated_source is not None
                    and session.get(Source, validated_source) is not None
                    and not _source_is_visible(
                        session=session, source_id=validated_source, visibility=visibility
                    )
                ):
                    raise RuntimeError("invalid source; register source before upload")
                metadata.setdefault("uploader_user_id", current_user.user_id)
                document = Document(
                    transaction_id=None,
                    source_id=validated_source,
                    shared_group_id=visibility.shared_group_id,
                    storage_uri=storage_uri,
                    mime_type=mime_type,
                    sha256=sha256,
                    file_name=file.filename,
                    ocr_status="pending",
                    metadata_json=metadata,
                    created_at=datetime.now(tz=UTC),
                )
                session.add(document)
                session.flush()
                return _response(
                    True,
                    {
                        "document_id": document.id,
                        "storage_uri": storage_uri,
                        "sha256": sha256,
                        "mime_type": mime_type,
                        "status": document.ocr_status,
                    },
                    warnings=warnings,
                    error=None,
                )
        except DocumentStorageError as exc:
            return _error_response(exc)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/documents/{document_id}/process")
    async def process_document(
        request: Request,
        document_id: str,
        scope: str = Form(default="personal"),
        caller_token: str | None = Form(default=None),
        legacy_api_key: str | None = Form(default=None, alias="api_key"),
    ) -> Any:
        try:
            _reject_legacy_form_api_key(legacy_api_key)
            await _reject_form_runtime_override_usage(request)
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                document = session.get(Document, document_id)
                if document is None:
                    raise RuntimeError("document not found")
                if not _document_is_visible(
                    session=session, document=document, visibility=visibility
                ):
                    raise RuntimeError("document not found")
                source_id = document.source_id or OCR_SOURCE_ID
            jobs = JobService(session_factory=sessions, config=app_config)
            job, reused = jobs.create_ocr_job(
                document_id=document_id,
                source=source_id,
                caller_token=caller_token,
            )
            if not reused and job.status == "queued":
                with session_scope(sessions) as session:
                    document = session.get(Document, document_id)
                    if document is not None:
                        document.ocr_status = "queued"
            return _response(
                True,
                {
                    "document_id": document_id,
                    "job_id": job.id,
                    "status": job.status,
                    "reused": reused,
                },
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/documents/{document_id}/status")
    def document_status(
        request: Request,
        document_id: str,
        scope: str = "personal",
        job_id: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                document = session.get(Document, document_id)
                if document is None:
                    raise RuntimeError("document not found")
                if not _document_is_visible(
                    session=session, document=document, visibility=visibility
                ):
                    raise RuntimeError("document not found")
                result: dict[str, Any] = {
                    "document_id": document.id,
                    "transaction_id": document.transaction_id,
                    "source_id": document.source_id,
                    "status": document.ocr_status,
                    "review_status": document.review_status,
                    "ocr_provider": document.ocr_provider,
                    "ocr_confidence": (
                        float(document.ocr_confidence)
                        if document.ocr_confidence is not None
                        else None
                    ),
                    "ocr_fallback_used": document.ocr_fallback_used,
                    "ocr_latency_ms": document.ocr_latency_ms,
                    "processed_at": (
                        document.ocr_processed_at.isoformat()
                        if document.ocr_processed_at is not None
                        else None
                    ),
                }
            if job_id:
                jobs = JobService(session_factory=sessions, config=app_config)
                result["job"] = jobs.get_job_status_payload(job_id=job_id)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/review-queue")
    def list_review_queue(
        request: Request,
        scope: str = "personal",
        limit: int = 50,
        offset: int = 0,
        status: str = "needs_review",
        threshold: float | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = review_queue(
                    session,
                    threshold=(
                        threshold
                        if threshold is not None
                        else app_config.ocr_review_confidence_threshold
                    ),
                    limit=limit,
                    offset=offset,
                    status=status,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/transactions")
    def list_transactions(
        request: Request,
        scope: str = "personal",
        query: str | None = None,
        year: int | None = None,
        month: int | None = None,
        source_id: str | None = None,
        source_kind: str | None = None,
        weekday: int | None = None,
        hour: int | None = None,
        tz_offset_minutes: int = 0,
        merchant_name: str | None = None,
        min_total_cents: int | None = None,
        max_total_cents: int | None = None,
        purchased_from: str | None = None,
        purchased_to: str | None = None,
        sort_by: str = "purchased_at",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            purchased_from_dt = _parse_optional_iso_datetime(purchased_from)
            purchased_to_dt = _parse_to_date(purchased_to)
            validated_tz_offset_minutes = _validate_tz_offset_minutes(tz_offset_minutes)
            validated_weekday = _validate_weekday(weekday)
            validated_hour = _validate_hour(hour)
            clamped_limit = min(max(limit, 1), 200)
            clamped_offset = max(offset, 0)
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = search_transactions(
                    session,
                    query=query,
                    year=year,
                    month=month,
                    source_id=source_id,
                    source_kind=source_kind,
                    weekday=validated_weekday,
                    hour=validated_hour,
                    tz_offset_minutes=validated_tz_offset_minutes,
                    merchant_name=merchant_name,
                    min_total_cents=min_total_cents,
                    max_total_cents=max_total_cents,
                    purchased_from=purchased_from_dt,
                    purchased_to=purchased_to_dt,
                    sort_by=cast(TransactionSortBy, sort_by),
                    sort_dir=cast(TransactionSortDir, sort_dir),
                    limit=clamped_limit,
                    offset=clamped_offset,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/items/search")
    def search_items(
        request: Request,
        scope: str = "personal",
        query: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        """Search receipt line items by name across all transactions."""
        try:
            from lidltool.analytics.scope import visible_transaction_ids_subquery
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            clamped_limit = min(max(limit, 1), 500)
            clamped_offset = max(offset, 0)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                visible_ids = visible_transaction_ids_subquery(visibility)
                base = (
                    select(
                        TransactionItem.id.label("item_id"),
                        TransactionItem.name,
                        TransactionItem.qty,
                        TransactionItem.unit,
                        TransactionItem.unit_price_cents,
                        TransactionItem.line_total_cents,
                        TransactionItem.category,
                        Transaction.id.label("transaction_id"),
                        Transaction.purchased_at,
                        Transaction.source_id,
                        Transaction.merchant_name,
                    )
                    .join(Transaction, Transaction.id == TransactionItem.transaction_id)
                    .where(Transaction.id.in_(visible_ids))
                    .order_by(Transaction.purchased_at.desc())
                )
                if query:
                    base = base.where(TransactionItem.name.ilike(f"%{query}%"))
                if from_date:
                    from_dt = _parse_optional_iso_datetime(from_date)
                    if from_dt:
                        base = base.where(Transaction.purchased_at >= from_dt)
                if to_date:
                    to_dt = _parse_to_date(to_date)
                    if to_dt:
                        base = base.where(Transaction.purchased_at <= to_dt)
                if source_id:
                    base = base.where(Transaction.source_id == source_id)
                total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
                rows = session.execute(base.limit(clamped_limit).offset(clamped_offset)).all()
                items = [
                    {
                        "item_id": row.item_id,
                        "name": row.name,
                        "qty": float(row.qty),
                        "unit": row.unit,
                        "unit_price_cents": row.unit_price_cents,
                        "line_total_cents": row.line_total_cents,
                        "category": row.category,
                        "transaction_id": row.transaction_id,
                        "purchased_at": row.purchased_at.isoformat() if row.purchased_at else None,
                        "source_id": row.source_id,
                        "merchant_name": row.merchant_name,
                    }
                    for row in rows
                ]
            return _response(
                True,
                result={"total": total, "limit": clamped_limit, "offset": clamped_offset, "items": items},
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/items/aggregate")
    def aggregate_items(
        request: Request,
        scope: str = "personal",
        query: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        source_id: str | None = None,
        group_by: str | None = None,
    ) -> Any:
        """Aggregate receipt line items: returns total spend, count, and optional breakdown.
        group_by can be 'source_id', 'month', 'year', 'name', or 'category'.
        """
        with open("/tmp/aggregate_items.log", "a") as _dbg:
            _dbg.write(f"aggregate_items called: query={query!r} from_date={from_date!r} to_date={to_date!r} source_id={source_id!r} group_by={group_by!r}\n")
        try:
            from lidltool.analytics.scope import visible_transaction_ids_subquery
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                visible_ids = visible_transaction_ids_subquery(visibility)

                base_filter: list[ColumnElement[bool]] = [Transaction.id.in_(visible_ids)]
                if query:
                    base_filter.append(TransactionItem.name.ilike(f"%{query}%"))
                if from_date:
                    from_dt = _parse_optional_iso_datetime(from_date)
                    if from_dt:
                        base_filter.append(Transaction.purchased_at >= from_dt)
                if to_date:
                    to_dt = _parse_to_date(to_date)
                    if to_dt:
                        base_filter.append(Transaction.purchased_at <= to_dt)
                if source_id:
                    base_filter.append(Transaction.source_id == source_id)

                group_col: SQLColumnExpression[str | None] | None
                if group_by == "source_id":
                    group_col = Transaction.source_id
                elif group_by == "month":
                    group_col = cast(
                        SQLColumnExpression[str | None],
                        func.strftime("%Y-%m", Transaction.purchased_at),
                    )
                elif group_by == "year":
                    group_col = cast(
                        SQLColumnExpression[str | None],
                        func.strftime("%Y", Transaction.purchased_at),
                    )
                elif group_by == "name":
                    group_col = TransactionItem.name
                elif group_by == "category":
                    group_col = func.coalesce(TransactionItem.category, "uncategorized")
                else:
                    group_col = None

                if group_col is not None:
                    rows = cast(
                        Sequence[tuple[str | None, int | None, int, Decimal | None]],
                        session.execute(
                            select(
                                group_col.label("group"),
                                func.sum(TransactionItem.line_total_cents).label("total_cents"),
                                func.count(TransactionItem.id).label("item_count"),
                                func.sum(TransactionItem.qty).label("total_qty"),
                            )
                            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
                            .where(*base_filter)
                            .group_by(group_col)
                            .order_by(func.sum(TransactionItem.line_total_cents).desc())
                        ).tuples().all(),
                    )
                    result = {
                        "groups": [
                            {
                                "group": group_value,
                                "total_cents": total_cents,
                                "item_count": item_count,
                                "total_qty": float(total_qty) if total_qty is not None else None,
                            }
                            for group_value, total_cents, item_count, total_qty in rows
                        ],
                        "grand_total_cents": sum(total_cents or 0 for _, total_cents, _, _ in rows),
                        "grand_item_count": sum(item_count or 0 for _, _, item_count, _ in rows),
                        "grand_total_qty": sum(float(total_qty or 0) for _, _, _, total_qty in rows),
                    }
                else:
                    totals_stmt = (
                        select(
                            func.sum(TransactionItem.line_total_cents).label("total_cents"),
                            func.count(TransactionItem.id).label("item_count"),
                            func.sum(TransactionItem.qty).label("total_qty"),
                        )
                        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
                        .where(*base_filter)
                    )
                    row = session.execute(totals_stmt).one()
                    result = {
                        "total_cents": row.total_cents or 0,
                        "item_count": row.item_count or 0,
                        "total_qty": float(row.total_qty) if row.total_qty is not None else None,
                    }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/transactions/manual")
    def create_manual_transaction(
        request: Request,
        payload: ManualTransactionCreateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            if payload.total_gross_cents < 0:
                raise RuntimeError("total_gross_cents must be non-negative")
            source_id = payload.source_id.strip()
            if not source_id:
                raise RuntimeError("source_id must be a non-empty string")
            source_display_name = (
                payload.source_display_name.strip()
                if isinstance(payload.source_display_name, str)
                and payload.source_display_name.strip()
                else "Manual Entries"
            )
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id
                visibility = _visibility_for_scope(current_user, scope)
            service = ManualIngestService(session_factory=sessions)
            manual_input = ManualTransactionInput(
                purchased_at=_to_utc_datetime(payload.purchased_at),
                merchant_name=payload.merchant_name.strip(),
                total_gross_cents=payload.total_gross_cents,
                source_id=source_id,
                source_kind="manual",
                source_display_name=source_display_name,
                source_account_ref=payload.source_account_ref,
                source_transaction_id=payload.source_transaction_id,
                idempotency_key=payload.idempotency_key,
                user_id=current_user_id,
                shared_group_id=visibility.shared_group_id,
                currency=payload.currency.strip().upper(),
                discount_total_cents=payload.discount_total_cents,
                allocation_mode=payload.allocation_mode,
                confidence=payload.confidence,
                items=_manual_item_payload(
                    payload.items,
                    shared_group_id=visibility.shared_group_id,
                ),
                discounts=_manual_discount_payload(payload.discounts),
                raw_payload=payload.raw_payload,
                ingest_channel="manual_api",
            )
            create_result = service.ingest_transaction(
                payload=manual_input,
                actor_type="user",
                actor_id=payload.actor_id or current_user_id,
                audit_action="transaction.manual_ingested",
                reason=payload.reason,
            )
            with session_scope(sessions) as session:
                details = transaction_detail(
                    session,
                    transaction_id=str(create_result["transaction_id"]),
                    visibility=visibility,
                )
            create_result["transaction"] = details["transaction"] if details else None
            return _response(True, result=create_result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/transactions/{transaction_id}")
    def get_transaction_detail(
        request: Request,
        transaction_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = transaction_detail(
                    session, transaction_id=transaction_id, visibility=visibility
                )
                if result is None:
                    raise RuntimeError("transaction not found")
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/transactions/{transaction_id}/history")
    def get_transaction_history(
        request: Request,
        transaction_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                details = transaction_detail(
                    session, transaction_id=transaction_id, visibility=visibility
                )
                if details is None:
                    raise RuntimeError("transaction not found")
                document_ids = [str(document["id"]) for document in details["documents"]]
                item_ids = [str(item["id"]) for item in details["items"]]
                events = list_transaction_history(
                    session,
                    transaction_id=transaction_id,
                    document_ids=document_ids,
                    item_ids=item_ids,
                )
                result = {
                    "transaction_id": transaction_id,
                    "count": len(events),
                    "events": events,
                }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/documents/{document_id}/preview")
    def preview_document(
        request: Request,
        document_id: str,
        scope: str = "personal",
    ) -> Response:
        context = _resolve_request_context(request)
        app_config = context.config
        sessions = context.sessions
        try:
            _apply_auth_guard(app_config, request=request)
        except RuntimeError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        with session_scope(sessions) as session:
            current_user = _resolve_request_user(
                request=request, session=session, config=app_config
            )
            visibility = _visibility_for_scope(current_user, scope)
            document = session.get(Document, document_id)
            if document is None:
                raise HTTPException(status_code=404, detail="document not found")
            if not _document_is_visible(session=session, document=document, visibility=visibility):
                raise HTTPException(status_code=404, detail="document not found")
            storage_uri = document.storage_uri
            mime_type = document.mime_type
            file_name = document.file_name or f"document-{document.id}"
        storage = DocumentStorage(app_config)
        try:
            payload = storage.read_bytes(storage_uri=storage_uri)
        except DocumentStorageError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        response = Response(content=payload, media_type=mime_type)
        response.headers["Content-Disposition"] = f'inline; filename="{file_name}"'
        return response

    @app.patch("/api/v1/transactions/{transaction_id}/overrides")
    def patch_transaction_overrides(
        request: Request,
        transaction_id: str,
        payload: TransactionOverrideRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            mode = payload.mode.strip().lower()
            if mode not in {"local", "global", "both"}:
                raise RuntimeError("mode must be one of: local, global, both")
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                details = transaction_detail(
                    session, transaction_id=transaction_id, visibility=visibility
                )
                if details is None:
                    raise RuntimeError("transaction not found")
                service = OverrideService(session=session)
                result = service.apply(
                    transaction_id=transaction_id,
                    mode=mode,
                    actor_id=payload.actor_id,
                    reason=payload.reason,
                    transaction_corrections=payload.transaction_corrections,
                    item_corrections=[
                        {"item_id": item.item_id, "corrections": item.corrections}
                        for item in payload.item_corrections
                    ],
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/chat/threads")
    def create_chat_thread(
        request: Request,
        payload: ChatThreadCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                thread_id = (
                    payload.thread_id.strip()
                    if isinstance(payload.thread_id, str) and payload.thread_id.strip()
                    else str(uuid4())
                )
                existing = session.get(ChatThread, thread_id)
                if existing is not None:
                    if not _owns_user_resource(current_user, resource_user_id=existing.user_id):
                        raise RuntimeError("chat thread conflict")
                    return _response(
                        True,
                        result=_serialize_chat_thread(existing),
                        warnings=warnings,
                        error=None,
                    )
                title = _normalize_chat_title(payload.title)
                thread = ChatThread(
                    thread_id=thread_id,
                    user_id=current_user.user_id,
                    title=title,
                    stream_status="idle",
                )
                session.add(thread)
                session.flush()
                result = _serialize_chat_thread(thread)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/chat/threads")
    def list_chat_threads(
        request: Request,
        limit: int = 50,
        offset: int = 0,
        include_archived: bool = False,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            safe_limit = max(1, min(limit, 200))
            safe_offset = max(offset, 0)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                where_conditions = [ownership_filter(ChatThread, visibility=visibility)]
                if not include_archived:
                    where_conditions.append(ChatThread.archived_at.is_(None))
                query = (
                    select(ChatThread)
                    .where(*where_conditions)
                    .order_by(ChatThread.updated_at.desc(), ChatThread.created_at.desc())
                    .limit(safe_limit)
                    .offset(safe_offset)
                )
                items = session.scalars(query).all()
                total = session.scalar(
                    select(func.count())
                    .select_from(ChatThread)
                    .where(*where_conditions)
                )
                result = {
                    "items": [_serialize_chat_thread(item) for item in items],
                    "total": int(total or 0),
                }
            return _response(
                True,
                result=result,
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/chat/threads/{thread_id}")
    def get_chat_thread(
        request: Request,
        thread_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                thread = _load_owned_chat_thread(
                    session=session,
                    user=current_user,
                    visibility=visibility,
                    thread_id=thread_id,
                )
                result = _serialize_chat_thread(thread)
            return _response(
                True,
                result=result,
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/chat/threads/{thread_id}")
    def patch_chat_thread(
        request: Request,
        thread_id: str,
        payload: ChatThreadUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                thread = _load_owned_chat_thread(
                    session=session,
                    user=current_user,
                    visibility=visibility,
                    thread_id=thread_id,
                )
                if payload.title is not None:
                    thread.title = _normalize_chat_title(payload.title)
                if payload.archived is not None:
                    thread.archived_at = datetime.now(tz=UTC) if payload.archived else None
                if payload.abandon_stream:
                    thread.stream_status = "idle"
                if payload.stream_status is not None:
                    if payload.stream_status == "streaming" and thread.stream_status == "streaming":
                        raise HTTPException(status_code=409, detail="thread is already generating")
                    thread.stream_status = payload.stream_status
                thread.updated_at = datetime.now(tz=UTC)
                session.flush()
                result = _serialize_chat_thread(thread)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/chat/threads/{thread_id}")
    def delete_chat_thread(
        request: Request,
        thread_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                thread = _load_owned_chat_thread(
                    session=session,
                    user=current_user,
                    visibility=visibility,
                    thread_id=thread_id,
                )
                thread.archived_at = datetime.now(tz=UTC)
                thread.stream_status = "idle"
                thread.updated_at = datetime.now(tz=UTC)
                session.flush()
                result = {"deleted": True, "thread": _serialize_chat_thread(thread)}
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/chat/threads/{thread_id}/messages")
    def list_chat_messages(
        request: Request,
        thread_id: str,
        limit: int = 200,
        offset: int = 0,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            safe_limit = max(1, min(limit, 500))
            safe_offset = max(offset, 0)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                _load_owned_chat_thread(
                    session=session,
                    user=current_user,
                    visibility=visibility,
                    thread_id=thread_id,
                )
                query = (
                    select(ChatMessage)
                    .where(ChatMessage.thread_id == thread_id)
                    .order_by(ChatMessage.created_at.asc(), ChatMessage.message_id.asc())
                    .limit(safe_limit)
                    .offset(safe_offset)
                )
                items = session.scalars(query).all()
                total = session.scalar(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.thread_id == thread_id)
                )
                result = {
                    "items": [_serialize_chat_message(item) for item in items],
                    "total": int(total or 0),
                }
            return _response(
                True,
                result=result,
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/chat/threads/{thread_id}/messages")
    def create_chat_message(
        request: Request,
        thread_id: str,
        payload: ChatMessageCreateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)
            content = payload.content.strip()
            if not content:
                raise RuntimeError("message content is required")
            idempotency_key = (
                payload.idempotency_key.strip()
                if isinstance(payload.idempotency_key, str) and payload.idempotency_key.strip()
                else None
            )

            schedule_title_generation = False
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                thread = session.get(ChatThread, thread_id)
                if thread is None:
                    thread = ChatThread(
                        thread_id=thread_id,
                        user_id=current_user.user_id,
                        shared_group_id=visibility.shared_group_id,
                        title=_default_chat_title_for_message(content),
                        stream_status="idle",
                    )
                    session.add(thread)
                    session.flush()
                if not (
                    _owns_user_resource(
                        current_user,
                        resource_user_id=thread.user_id,
                        resource_shared_group_id=thread.shared_group_id,
                    )
                    or resource_belongs_to_workspace(
                        visibility=visibility,
                        resource_user_id=thread.user_id,
                        resource_shared_group_id=thread.shared_group_id,
                    )
                ):
                    raise HTTPException(status_code=404, detail="chat thread not found")
                if thread.archived_at is not None:
                    raise RuntimeError("chat thread not found")
                if thread.stream_status == "streaming":
                    raise HTTPException(status_code=409, detail="thread is already generating")

                if idempotency_key:
                    existing_message = session.scalar(
                        select(ChatMessage)
                        .where(
                            ChatMessage.thread_id == thread.thread_id,
                            ChatMessage.role == "user",
                            ChatMessage.idempotency_key == idempotency_key,
                        )
                        .order_by(ChatMessage.created_at.desc(), ChatMessage.message_id.desc())
                        .limit(1)
                    )
                    if existing_message is not None:
                        result = {
                            "thread": _serialize_chat_thread(thread),
                            "message": _serialize_chat_message(existing_message),
                        }
                        return _response(True, result=result, warnings=warnings, error=None)

                message = ChatMessage(
                    thread_id=thread.thread_id,
                    role="user",
                    content_json=_chat_parts_from_text(content),
                    idempotency_key=idempotency_key,
                )
                session.add(message)
                thread.updated_at = datetime.now(tz=UTC)
                try:
                    session.flush()
                except IntegrityError as exc:
                    if not idempotency_key:
                        raise
                    session.rollback()
                    thread = session.get(ChatThread, thread_id)
                    if thread is None or thread.archived_at is not None:
                        raise exc
                    if not (
                        _owns_user_resource(
                            current_user,
                            resource_user_id=thread.user_id,
                            resource_shared_group_id=thread.shared_group_id,
                        )
                        or resource_belongs_to_workspace(
                            visibility=visibility,
                            resource_user_id=thread.user_id,
                            resource_shared_group_id=thread.shared_group_id,
                        )
                    ):
                        raise HTTPException(
                            status_code=404,
                            detail="chat thread not found",
                        ) from None
                    existing_message = session.scalar(
                        select(ChatMessage)
                        .where(
                            ChatMessage.thread_id == thread.thread_id,
                            ChatMessage.role == "user",
                            ChatMessage.idempotency_key == idempotency_key,
                        )
                        .order_by(ChatMessage.created_at.desc(), ChatMessage.message_id.desc())
                        .limit(1)
                    )
                    if existing_message is None:
                        raise exc
                    result = {
                        "thread": _serialize_chat_thread(thread),
                        "message": _serialize_chat_message(existing_message),
                    }
                    return _response(True, result=result, warnings=warnings, error=None)

                user_message_count = session.scalar(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(
                        ChatMessage.thread_id == thread.thread_id,
                        ChatMessage.role == "user",
                    )
                )
                schedule_title_generation = int(user_message_count or 0) >= 2
                result = {
                    "thread": _serialize_chat_thread(thread),
                    "message": _serialize_chat_message(message),
                }
            if schedule_title_generation:
                _schedule_chat_title_generation(
                    config=app_config,
                    sessions=sessions,
                    config_path=context.config_path,
                    thread_id=thread_id,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/chat/threads/{thread_id}/stream")
    async def stream_chat_thread(
        request: Request,
        thread_id: str,
        payload: ChatStreamRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            _apply_auth_guard(app_config, request=request)
            selected_model_id = _resolve_selected_chat_model(app_config, payload.model_id)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                thread = _load_owned_chat_thread(
                    session=session,
                    user=current_user,
                    visibility=visibility,
                    thread_id=thread_id,
                )
                if thread.stream_status == "streaming":
                    raise HTTPException(status_code=409, detail="thread is already generating")
                stored_messages = session.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.thread_id == thread_id)
                    .order_by(ChatMessage.created_at.asc(), ChatMessage.message_id.asc())
                ).all()
                if not stored_messages:
                    raise RuntimeError("at least one message is required")
                openai_messages = []
                system_messages: list[str] = []
                proxy_context_messages: list[dict[str, Any]] = []
                for stored_message in stored_messages:
                    if stored_message.role not in {"system", "user", "assistant"}:
                        continue
                    text = _chat_text_from_content(stored_message.content_json)
                    if not text:
                        continue
                    if stored_message.role == "system":
                        system_messages.append(text)
                        openai_messages.append(simple_text_message(role="system", content=text))
                    elif stored_message.role == "assistant":
                        openai_messages.append(simple_text_message(role="assistant", content=text))
                        proxy_context_messages.append(
                            {"role": "assistant", "content": [{"type": "text", "text": text}]}
                        )
                    else:
                        openai_messages.append(simple_text_message(role="user", content=text))
                        proxy_context_messages.append(
                            {"role": "user", "content": [{"type": "text", "text": text}]}
                        )
                if not openai_messages:
                    raise RuntimeError("at least one text message is required")
                thread.stream_status = "streaming"
                thread.updated_at = datetime.now(tz=UTC)

            from lidltool.ai.runtime import RuntimeTask, StreamChatRequest
            if _should_route_stream_via_chatgpt(app_config, selected_model_id):
                oauth_token = _resolve_ai_oauth_bearer_token(app_config, context.config_path)
                if not oauth_token:
                    raise RuntimeError("AI provider credentials are not configured")
                proxy_payload = StreamProxyRequest(
                    model=StreamProxyModelRef(
                        id=selected_model_id,
                        provider="openai",
                    ),
                    context=StreamProxyContext(
                        systemPrompt="\n\n".join(system_messages) or None,
                        messages=proxy_context_messages,
                        tools=[],
                    ),
                    options=StreamProxyOptions(),
                )
                return await _chatgpt_codex_stream(payload=proxy_payload, bearer_token=oauth_token)

            runtime = _resolve_pi_agent_runtime_for_model(
                app_config,
                selected_model_id=selected_model_id,
            )
            model_id = _runtime_model_name(
                runtime,
                explicit_model=selected_model_id,
                app_config=app_config,
            )
            start_time = time.perf_counter()

            async def event_stream() -> Any:
                text_chunks: list[str] = []
                input_tokens = 0
                output_tokens = 0
                total_tokens = 0
                finish_reason = "stop"
                stream_error: Exception | None = None
                try:
                    async for event in runtime.stream_chat(
                        StreamChatRequest(
                            task=RuntimeTask.PI_AGENT,
                            model_name=model_id,
                            messages=openai_messages,
                            temperature=0.7,
                            max_tokens=4096,
                        )
                    ):
                        if event.type == "text_delta" and event.delta:
                            text_chunks.append(event.delta)
                        if event.type == "done":
                            finish_reason = event.reason or "stop"
                            usage = event.usage or {}
                            input_tokens = int(usage.get("input", 0) or 0)
                            output_tokens = int(usage.get("output", 0) or 0)
                            total_tokens = int(usage.get("totalTokens", 0) or 0)
                        payload = {"type": event.type}
                        if event.content_index is not None:
                            payload["contentIndex"] = event.content_index
                        if event.delta is not None:
                            payload["delta"] = event.delta
                        if event.tool_call_id is not None:
                            payload["id"] = event.tool_call_id
                        if event.tool_name is not None:
                            payload["toolName"] = event.tool_name
                        if event.reason is not None:
                            payload["reason"] = event.reason
                        if event.usage:
                            payload["usage"] = event.usage
                        yield _sse_data(payload)
                except Exception as exc:  # noqa: BLE001
                    stream_error = exc

                latency_ms = int((time.perf_counter() - start_time) * 1000)
                normalized_total_tokens = total_tokens or (input_tokens + output_tokens)

                if stream_error is not None:
                    with session_scope(sessions) as session:
                        thread = session.get(ChatThread, thread_id)
                        if thread is not None:
                            thread.stream_status = "failed"
                            thread.updated_at = datetime.now(tz=UTC)
                        run = ChatRun(
                            thread_id=thread_id,
                            message_id=None,
                            model_id=model_id,
                            prompt_tokens=input_tokens or None,
                            completion_tokens=output_tokens or None,
                            latency_ms=latency_ms,
                            status="error",
                        )
                        session.add(run)
                    yield _sse_data({"type": "text_end", "contentIndex": 0})
                    yield _sse_data(
                        {
                            "type": "done",
                            "reason": "error",
                            "usage": {
                                "input": input_tokens,
                                "output": output_tokens,
                                "cacheRead": 0,
                                "cacheWrite": 0,
                                "totalTokens": normalized_total_tokens,
                                "cost": None,
                            },
                        }
                    )
                    return

                assistant_text = "".join(text_chunks).strip()
                run_status = "timeout" if finish_reason == "length" else "ok"
                with session_scope(sessions) as session:
                    thread = session.get(ChatThread, thread_id)
                    if thread is not None:
                        thread.stream_status = "idle"
                        thread.updated_at = datetime.now(tz=UTC)
                    assistant_message = ChatMessage(
                        thread_id=thread_id,
                        role="assistant",
                        content_json=_chat_parts_from_text(assistant_text),
                        usage_json={
                            "prompt_tokens": input_tokens,
                            "completion_tokens": output_tokens,
                            "total_tokens": normalized_total_tokens,
                        },
                    )
                    session.add(assistant_message)
                    session.flush()
                    run = ChatRun(
                        thread_id=thread_id,
                        message_id=assistant_message.message_id,
                        model_id=model_id,
                        prompt_tokens=input_tokens or None,
                        completion_tokens=output_tokens or None,
                        latency_ms=latency_ms,
                        status=run_status,
                    )
                    session.add(run)

                yield _sse_data({"type": "text_end", "contentIndex": 0})
                yield _sse_data(
                    {
                        "type": "done",
                        "reason": "length" if finish_reason == "length" else "stop",
                        "usage": {
                            "input": input_tokens,
                            "output": output_tokens,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                            "totalTokens": normalized_total_tokens,
                            "cost": None,
                        },
                    }
                )

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/chat/threads/{thread_id}/runs")
    def persist_chat_run(
        request: Request,
        thread_id: str,
        payload: ChatRunPersistRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                thread = _load_owned_chat_thread(
                    session=session,
                    user=current_user,
                    visibility=visibility,
                    thread_id=thread_id,
                )

                created_messages: list[ChatMessage] = []
                last_assistant_message: ChatMessage | None = None
                prompt_tokens = payload.prompt_tokens
                completion_tokens = payload.completion_tokens

                for runtime_message in payload.messages:
                    role_raw = str(runtime_message.get("role") or "").strip()
                    if role_raw == "user":
                        continue
                    mapped_role = "tool" if role_raw == "toolResult" else role_raw
                    if mapped_role not in {"assistant", "tool"}:
                        continue
                    usage_json = (
                        runtime_message.get("usage")
                        if isinstance(runtime_message.get("usage"), dict)
                        else None
                    )
                    if usage_json and (prompt_tokens is None or completion_tokens is None):
                        parsed_prompt, parsed_completion = _run_tokens_from_usage(usage_json)
                        if prompt_tokens is None:
                            prompt_tokens = parsed_prompt
                        if completion_tokens is None:
                            completion_tokens = parsed_completion

                    message = ChatMessage(
                        thread_id=thread_id,
                        role=mapped_role,
                        content_json=_normalize_runtime_content_json(runtime_message.get("content")),
                        tool_name=(
                            str(runtime_message.get("toolName"))
                            if mapped_role == "tool" and runtime_message.get("toolName")
                            else None
                        ),
                        tool_call_id=(
                            str(runtime_message.get("toolCallId"))
                            if mapped_role == "tool" and runtime_message.get("toolCallId")
                            else None
                        ),
                        usage_json=cast(dict[str, object] | None, usage_json),
                        error=(
                            str(runtime_message.get("error"))
                            if isinstance(runtime_message.get("error"), str)
                            else None
                        ),
                    )
                    session.add(message)
                    created_messages.append(message)
                    if mapped_role == "assistant":
                        last_assistant_message = message

                session.flush()

                run = ChatRun(
                    thread_id=thread_id,
                    message_id=last_assistant_message.message_id if last_assistant_message else None,
                    model_id=(payload.model_id or app_config.ai_model or "gpt-5.2-codex"),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_ms=payload.latency_ms,
                    status=payload.status,
                )
                session.add(run)

                if payload.status == "error":
                    thread.stream_status = "failed"
                else:
                    thread.stream_status = "idle"
                thread.updated_at = datetime.now(tz=UTC)
                session.flush()
                result = {
                    "thread": _serialize_chat_thread(thread),
                    "messages": [_serialize_chat_message(message) for message in created_messages],
                    "run": _serialize_chat_run(run),
                }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/automations")
    def list_automations(
        request: Request,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = _reload_request_context_config(context)
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            service = AutomationService(session_factory=sessions, config=app_config)
            result = service.list_rules(limit=limit, offset=offset)
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/automations")
    def create_automation(
        request: Request,
        payload: AutomationRuleCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            service = AutomationService(session_factory=sessions, config=app_config)
            result = service.create_rule(
                name=payload.name,
                rule_type=payload.rule_type,
                enabled=payload.enabled,
                trigger_config=payload.trigger_config,
                action_config=payload.action_config,
                actor_id=payload.actor_id,
            )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/automations/executions")
    def list_automation_executions(
        request: Request,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        rule_type: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            service = AutomationService(session_factory=sessions, config=app_config)
            result = service.list_executions(
                limit=limit,
                offset=offset,
                status=status,
                rule_type=rule_type,
            )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/automations/{rule_id}")
    def get_automation(
        request: Request,
        rule_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            service = AutomationService(session_factory=sessions, config=app_config)
            result = service.get_rule(rule_id=rule_id)
            if result is None:
                raise RuntimeError("automation rule not found")
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/automations/{rule_id}")
    def patch_automation(
        request: Request,
        rule_id: str,
        payload: AutomationRuleUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            service = AutomationService(session_factory=sessions, config=app_config)
            result = service.update_rule(
                rule_id=rule_id,
                payload=payload.model_dump(exclude_none=True),
                actor_id=payload.actor_id,
            )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/automations/{rule_id}")
    def delete_automation(
        request: Request,
        rule_id: str,
        actor_id: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            service = AutomationService(session_factory=sessions, config=app_config)
            result = service.delete_rule(rule_id=rule_id, actor_id=actor_id)
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/automations/{rule_id}/run")
    def run_automation(
        request: Request,
        rule_id: str,
        payload: AutomationRunRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            service = AutomationService(session_factory=sessions, config=app_config)
            result = service.run_rule(rule_id=rule_id, actor_id=payload.actor_id)
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/offers")
    def get_offers_overview(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = offer_overview(session, config=app_config, user_id=current_user.user_id)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/offers/sources")
    def get_offer_sources(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                items = list_offer_sources(session, user_id=current_user.user_id)
                result = _collection_result(
                    result={"count": len(items), "items": items},
                    alias_key="sources",
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/offers/sources")
    def post_offer_source(
        request: Request,
        payload: OfferSourceCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = create_offer_source(
                    session,
                    user_id=current_user.user_id,
                    merchant_name=payload.merchant_name,
                    merchant_url=payload.merchant_url,
                    display_name=payload.display_name,
                    country_code=payload.country_code,
                    notes=payload.notes,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/offers/sources/{source_id}")
    def patch_offer_source(
        request: Request,
        source_id: str,
        payload: OfferSourceUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = update_offer_source(
                    session,
                    user_id=current_user.user_id,
                    source_id=source_id,
                    payload=payload.model_dump(exclude_none=True),
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/offers/sources/{source_id}")
    def destroy_offer_source(
        request: Request,
        source_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = delete_offer_source(
                    session,
                    user_id=current_user.user_id,
                    source_id=source_id,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/offers/merchant-items")
    def get_offer_merchant_items(
        request: Request,
        merchant_name: str,
        limit: int = 100,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = list_offer_merchant_items(
                    session,
                    user_id=current_user.user_id,
                    merchant_name=merchant_name,
                    limit=limit,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/offers/refresh")
    def post_offer_refresh(
        request: Request,
        payload: OfferRefreshRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = run_offer_refresh(
                    session,
                    config=app_config,
                    source_ids=payload.source_ids or None,
                    requested_by_user_id=current_user.user_id,
                    trigger_kind="manual",
                    discovery_limit=payload.discovery_limit,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/offers/refresh-runs")
    def get_offer_refresh_runs(
        request: Request,
        limit: int = 20,
        offset: int = 0,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = list_offer_refresh_runs(
                    session,
                    user_id=current_user.user_id,
                    limit=limit,
                    offset=offset,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/offers/watchlists")
    def get_offer_watchlists(
        request: Request,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = list_offer_watchlists(
                    session,
                    user_id=current_user.user_id,
                    limit=limit,
                    offset=offset,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/offers/watchlists")
    def post_offer_watchlist(
        request: Request,
        payload: OfferWatchlistCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = create_offer_watchlist(
                    session,
                    user_id=current_user.user_id,
                    product_id=payload.product_id,
                    query_text=payload.query_text,
                    source_id=payload.source_id,
                    min_discount_percent=payload.min_discount_percent,
                    max_price_cents=payload.max_price_cents,
                    notes=payload.notes,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/offers/watchlists/{watchlist_id}")
    def patch_offer_watchlist(
        request: Request,
        watchlist_id: str,
        payload: OfferWatchlistUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = update_offer_watchlist(
                    session,
                    user_id=current_user.user_id,
                    watchlist_id=watchlist_id,
                    payload=payload.model_dump(exclude_none=True),
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/offers/watchlists/{watchlist_id}")
    def remove_offer_watchlist(
        request: Request,
        watchlist_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = delete_offer_watchlist(
                    session,
                    user_id=current_user.user_id,
                    watchlist_id=watchlist_id,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/offers/matches")
    def get_offer_matches(
        request: Request,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = list_offer_matches(
                    session,
                    user_id=current_user.user_id,
                    limit=limit,
                    offset=offset,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/offers/alerts")
    def get_offer_alerts(
        request: Request,
        unread_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = list_offer_alerts(
                    session,
                    user_id=current_user.user_id,
                    unread_only=unread_only,
                    limit=limit,
                    offset=offset,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/offers/alerts/{alert_id}")
    def patch_offer_alert(
        request: Request,
        alert_id: str,
        payload: OfferAlertReadRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(request=request, session=session, config=app_config)
                result = mark_offer_alert_read(
                    session,
                    user_id=current_user.user_id,
                    alert_id=alert_id,
                    read=payload.read,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills")
    def list_recurring_bills(
        request: Request,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.list_bills(
                user_id=current_user.user_id,
                visibility=visibility,
                include_inactive=include_inactive,
                limit=limit,
                offset=offset,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/recurring-bills")
    def create_recurring_bill(
        request: Request,
        payload: RecurringBillCreateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.create_bill(
                user_id=current_user.user_id,
                visibility=visibility,
                name=payload.name,
                merchant_canonical=payload.merchant_canonical,
                merchant_alias_pattern=payload.merchant_alias_pattern,
                category=payload.category,
                frequency=payload.frequency,
                interval_value=payload.interval_value,
                amount_cents=payload.amount_cents,
                amount_tolerance_pct=payload.amount_tolerance_pct,
                currency=payload.currency,
                anchor_date=payload.anchor_date,
                active=payload.active,
                notes=payload.notes,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills/analytics/overview")
    def get_recurring_overview(
        request: Request,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_overview(user_id=current_user.user_id, visibility=visibility)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills/analytics/calendar")
    def get_recurring_calendar(
        request: Request,
        year: int | None = None,
        month: int | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            now = datetime.now(tz=UTC)
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_calendar(
                user_id=current_user.user_id,
                visibility=visibility,
                year=year or now.year,
                month=month or now.month,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills/analytics/forecast")
    def get_recurring_forecast(
        request: Request,
        months: int = 6,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_forecast(
                user_id=current_user.user_id,
                visibility=visibility,
                months=months,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills/analytics/gaps")
    def get_recurring_gaps(
        request: Request,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_gaps(user_id=current_user.user_id, visibility=visibility)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/recurring-bills/occurrences/{occ_id}/status")
    def update_recurring_occurrence_status(
        request: Request,
        occ_id: str,
        payload: RecurringOccurrenceStatusUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.update_occurrence_status(
                user_id=current_user.user_id,
                visibility=visibility,
                occurrence_id=occ_id,
                status=payload.status,
                notes=payload.notes,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/recurring-bills/occurrences/{occ_id}/skip")
    def skip_recurring_occurrence(
        request: Request,
        occ_id: str,
        payload: RecurringOccurrenceSkipRequest | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.skip_occurrence(
                user_id=current_user.user_id,
                visibility=visibility,
                occurrence_id=occ_id,
                notes=payload.notes if payload is not None else None,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/recurring-bills/occurrences/{occ_id}/reconcile")
    def reconcile_recurring_occurrence(
        request: Request,
        occ_id: str,
        payload: RecurringOccurrenceReconcileRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, is_service_user = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.reconcile_occurrence(
                user_id=user_id,
                visibility=visibility,
                occurrence_id=occ_id,
                transaction_id=payload.transaction_id,
                include_unowned_transactions=is_service_user,
                match_confidence=payload.match_confidence,
                match_method=payload.match_method,
                notes=payload.notes,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills/{bill_id}/occurrences")
    def list_recurring_bill_occurrences(
        request: Request,
        bill_id: str,
        from_date: str | None = None,
        to_date: str | None = None,
        status: str | None = None,
        limit: int = 200,
        offset: int = 0,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.list_occurrences(
                user_id=current_user.user_id,
                visibility=visibility,
                bill_id=bill_id,
                from_date=_parse_optional_iso_date(from_date),
                to_date=_parse_optional_iso_date(to_date),
                status=status,
                limit=limit,
                offset=offset,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/recurring-bills/{bill_id}/occurrences/generate")
    def generate_recurring_bill_occurrences(
        request: Request,
        bill_id: str,
        payload: RecurringGenerateOccurrencesRequest | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.generate_occurrences(
                user_id=current_user.user_id,
                visibility=visibility,
                bill_id=bill_id,
                from_date=payload.from_date if payload is not None else None,
                to_date=payload.to_date if payload is not None else None,
                horizon_months=(payload.horizon_months if payload is not None else 6),
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/recurring-bills/{bill_id}/match")
    def run_recurring_bill_matching(
        request: Request,
        bill_id: str,
        payload: RecurringRunMatchingRequest | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, is_service_user = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.run_matching(
                user_id=user_id,
                visibility=visibility,
                bill_id=bill_id,
                include_unowned_transactions=is_service_user,
                auto_match_threshold=(
                    payload.auto_match_threshold if payload is not None else 0.9
                ),
                review_threshold=(payload.review_threshold if payload is not None else 0.7),
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills/{bill_id}")
    def get_recurring_bill(
        request: Request,
        bill_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_bill(
                user_id=current_user.user_id,
                visibility=visibility,
                bill_id=bill_id,
            )
            if result is None:
                raise RuntimeError("recurring bill not found")
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/recurring-bills/{bill_id}")
    def update_recurring_bill(
        request: Request,
        bill_id: str,
        payload: RecurringBillUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.update_bill(
                user_id=current_user.user_id,
                visibility=visibility,
                bill_id=bill_id,
                payload=payload.model_dump(exclude_unset=True),
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/recurring-bills/{bill_id}")
    def delete_recurring_bill(
        request: Request,
        bill_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
            service = RecurringBillsService(session_factory=sessions)
            result = service.delete_bill(
                user_id=current_user.user_id,
                visibility=visibility,
                bill_id=bill_id,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/dashboard/cards")
    def get_dashboard_cards(
        request: Request,
        year: int,
        month: int | None = None,
        source_ids: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = dashboard_totals(
                    session,
                    year=year,
                    month=month,
                    source_ids=_parse_source_ids(source_ids),
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/dashboard/years")
    def get_dashboard_years(
        request: Request,
        source_ids: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = dashboard_available_years(
                    session,
                    source_ids=_parse_source_ids(source_ids),
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/dashboard/summary")
    def get_dashboard_summary(
        request: Request,
        year: int | None = None,
        month: int | None = None,
        recent_limit: int = 5,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            now = datetime.now(tz=UTC)
            resolved_year = year if year is not None else now.year
            resolved_month = month if month is not None else now.month
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = _dashboard_summary_payload(
                    app,
                    session,
                    config=app_config,
                    user=current_user,
                    visibility=visibility,
                    year=resolved_year,
                    month=resolved_month,
                    recent_limit=recent_limit,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/dashboard/overview")
    def get_dashboard_overview(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        source_ids: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            resolved_from, resolved_to = _normalize_dashboard_window(from_date, to_date)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = _dashboard_overview_payload(
                    session,
                    user=current_user,
                    visibility=visibility,
                    from_dt=resolved_from,
                    to_dt=resolved_to,
                    source_ids=_parse_source_ids(source_ids),
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/dashboard/trends")
    def get_dashboard_trends(
        request: Request,
        year: int,
        months_back: int = 6,
        end_month: int = 12,
        source_ids: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = dashboard_trends(
                    session,
                    year=year,
                    months_back=months_back,
                    end_month=end_month,
                    source_ids=_parse_source_ids(source_ids),
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/dashboard/savings-breakdown")
    def get_dashboard_savings_breakdown(
        request: Request,
        year: int,
        month: int | None = None,
        view: str = "native",
        source_ids: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = dashboard_savings_breakdown(
                    session,
                    year=year,
                    month=month,
                    view=view,
                    source_ids=_parse_source_ids(source_ids),
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/dashboard/retailer-composition")
    def get_dashboard_retailer_composition(
        request: Request,
        year: int,
        month: int | None = None,
        source_ids: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = dashboard_retailer_composition(
                    session,
                    year=year,
                    month=month,
                    source_ids=_parse_source_ids(source_ids),
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/sources")
    def get_sources(
        request: Request,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = list_sources(
                    session,
                    config=app_config,
                    visibility=visibility,
                    include_sensitive_plugin_details=False,
                    include_operator_diagnostics=False,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/sources/status")
    def get_sources_status(
        request: Request,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                auth_service = _connector_auth_service(app, config=app_config)
                stmt = (
                    select(Source)
                    .where(ownership_filter(Source, visibility=visibility, include_service_unowned=True))
                    .order_by(Source.display_name.asc(), Source.id.asc())
                )
                items = [
                    _source_status_payload(
                        app,
                        session,
                        auth_service=auth_service,
                        config=app_config,
                        source=source,
                        include_sensitive_plugin_details=False,
                        include_auth_diagnostics=False,
                    )
                    for source in session.execute(stmt).scalars().all()
                ]
                result = _collection_result(
                    result={"count": len(items), "items": items},
                    alias_key="sources",
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/sources/{source_id}/status")
    def get_source_status(
        request: Request,
        source_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                auth_service = _connector_auth_service(app, config=app_config)
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                if not _source_is_visible(session=session, source_id=source_id, visibility=visibility):
                    raise RuntimeError("source not found")
                source = session.get(Source, source_id)
                if source is None:
                    raise RuntimeError("source not found")
                result = _source_status_payload(
                    app,
                    session,
                    auth_service=auth_service,
                    config=app_config,
                    source=source,
                    include_sensitive_plugin_details=False,
                    include_auth_diagnostics=False,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/sources/{source_id}/auth")
    def get_source_auth_status(
        request: Request,
        source_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                if not _source_is_visible(session=session, source_id=source_id, visibility=visibility):
                    raise RuntimeError("source not found")
                auth_service = _connector_auth_service(app, config=app_config)
                result = serialize_source_auth_status(
                    auth_service=auth_service,
                    source_id=source_id,
                    include_diagnostics=False,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/plugin-management")
    def get_plugin_management(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
                result = plugin_management_payload(
                    session,
                    config=app_config,
                    include_sensitive_details=True,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/connectors")
    def get_connectors(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request,
                    session=session,
                    config=app_config,
                )
                auth_service = _connector_auth_service(app, config=app_config)
                result = connector_discovery_payload(
                    app,
                    session,
                    auth_service=auth_service,
                    config=app_config,
                    viewer_is_admin=current_user.is_admin,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/rescan")
    def rescan_connectors(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                auth_context = _require_admin_auth_context(
                    request=request,
                    session=session,
                    config=app_config,
                )
                auth_service = _connector_auth_service(app, config=app_config)
                result = connector_discovery_payload(
                    app,
                    session,
                    auth_service=auth_service,
                    config=app_config,
                    viewer_is_admin=auth_context.user.is_admin,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/reload")
    def reload_connectors(
        request: Request,
    ) -> Any:
        return rescan_connectors(request=request)

    @app.post("/api/v1/connectors/{source_id}/install")
    def post_connector_install(
        request: Request,
        source_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
                result = install_connector(
                    session,
                    source_id=source_id,
                    config=app_config,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/{source_id}/enable")
    def post_connector_enable(
        request: Request,
        source_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
                result = set_connector_enabled(
                    session,
                    source_id=source_id,
                    enabled=True,
                    config=app_config,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/{source_id}/disable")
    def post_connector_disable(
        request: Request,
        source_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
                result = set_connector_enabled(
                    session,
                    source_id=source_id,
                    enabled=False,
                    config=app_config,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/{source_id}/uninstall")
    def post_connector_uninstall(
        request: Request,
        source_id: str,
        payload: ConnectorUninstallRequest | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
                result = uninstall_connector(
                    session,
                    source_id=source_id,
                    purge_config=bool(payload.purge_config) if payload is not None else False,
                    config=app_config,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/connectors/{source_id}/config")
    def get_connector_config(
        request: Request,
        source_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
                result = connector_lifecycle_record_payload(
                    session,
                    source_id=source_id,
                    config=app_config,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/{source_id}/config")
    def post_connector_config(
        request: Request,
        source_id: str,
        payload: ConnectorConfigUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
                result = update_connector_config(
                    session,
                    source_id=source_id,
                    config=app_config,
                    values=payload.values,
                    clear_secret_keys=list(payload.clear_secret_keys),
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/plugin-management/rescan")
    def rescan_plugin_management(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
                result = plugin_management_payload(
                    session,
                    config=app_config,
                    include_sensitive_details=True,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/cascade/start")
    def start_connector_cascade(
        request: Request,
        payload: ConnectorCascadeStartRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id

            source_ids = _normalize_cascade_source_ids(payload.source_ids)
            unsupported_sources = [
                source_id
                for source_id in source_ids
                if _connector_command(app_config, source_id=source_id, operation="bootstrap") is None
                or _connector_command(app_config, source_id=source_id, operation="sync") is None
            ]
            if unsupported_sources:
                unsupported = ", ".join(sorted(unsupported_sources))
                raise RuntimeError(f"unsupported source(s) for cascade: {unsupported}")

            cascade_sessions = get_connector_cascade_sessions(app)
            cascade_sessions_lock = get_connector_cascade_lock(app)
            with cascade_sessions_lock:
                existing = cascade_sessions.get(current_user_id)
                if existing is not None and _connector_cascade_is_active(existing):
                    return _response(
                        True,
                        result={"reused": True, "cascade": _serialize_connector_cascade(existing, request=request)},
                        warnings=warnings,
                        error=None,
                    )
                if any(
                    cascade.user_id != current_user_id
                    and _connector_cascade_is_active(cascade)
                    for cascade in cascade_sessions.values()
                ):
                    raise RuntimeError(
                        "another connector cascade is already running; wait or cancel it before starting a new cascade"
                    )

                bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
                sync_sessions = get_connector_command_sessions(app, kind="sync")
                auth_service = _connector_auth_service(app, config=app_config)
                if auth_service.any_bootstrap_running() or _connector_any_running(sync_sessions):
                    raise RuntimeError(
                        "another connector operation is already running; wait or cancel it before starting a cascade"
                    )

                cascade = _start_connector_cascade_session(
                    app,
                    user_id=current_user_id,
                    source_ids=source_ids,
                    full=payload.full,
                    config=app_config,
                    warnings=warnings,
                )

            result = {"reused": False, "cascade": _serialize_connector_cascade(cascade, request=request)}
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/cascade/retry")
    def retry_connector_cascade(
        request: Request,
        payload: ConnectorCascadeRetryRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id

            cascade_sessions = get_connector_cascade_sessions(app)
            cascade_sessions_lock = get_connector_cascade_lock(app)
            with cascade_sessions_lock:
                existing = cascade_sessions.get(current_user_id)
                if existing is None:
                    raise RuntimeError("connector cascade not found for current user")
                if _connector_cascade_is_active(existing):
                    return _response(
                        True,
                        result={"reused": True, "cascade": _serialize_connector_cascade(existing, request=request)},
                        warnings=warnings,
                        error=None,
                    )

                retry_states = _retryable_cascade_states(include_skipped=payload.include_skipped)
                retry_source_ids = [
                    source_id
                    for source_id in existing.source_ids
                    if existing.sources[source_id].state in retry_states
                ]
                if not retry_source_ids:
                    raise RuntimeError("missing retryable sources; no failed or remaining sources to retry")

                if any(
                    cascade.user_id != current_user_id
                    and _connector_cascade_is_active(cascade)
                    for cascade in cascade_sessions.values()
                ):
                    raise RuntimeError(
                        "another connector cascade is already running; wait or cancel it before retrying"
                    )

                bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
                sync_sessions = get_connector_command_sessions(app, kind="sync")
                auth_service = _connector_auth_service(app, config=app_config)
                if auth_service.any_bootstrap_running() or _connector_any_running(sync_sessions):
                    raise RuntimeError(
                        "another connector operation is already running; wait or cancel it before retrying cascade"
                    )

                full = existing.full if payload.full is None else payload.full
                cascade = _start_connector_cascade_session(
                    app,
                    user_id=current_user_id,
                    source_ids=retry_source_ids,
                    full=full,
                    config=app_config,
                    warnings=warnings,
                )
            result = {"reused": False, "cascade": _serialize_connector_cascade(cascade, request=request)}
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/connectors/cascade/status")
    def get_connector_cascade_status(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id

            cascade_sessions = get_connector_cascade_sessions(app)
            cascade = cascade_sessions.get(current_user_id)
            if cascade is None:
                result = _idle_connector_cascade_status()
            else:
                result = _serialize_connector_cascade(cascade, request=request)
                selected_source_ids = cast(list[str], result["source_ids"])
                if any(
                    _connector_is_preview_source(source_id, config=app_config)
                    for source_id in selected_source_ids
                ):
                    warnings.append(
                        "cascade includes preview connectors that are not fully live-validated yet"
                    )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/cascade/cancel")
    def cancel_connector_cascade(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id

            cascade_sessions = get_connector_cascade_sessions(app)
            cascade = cascade_sessions.get(current_user_id)
            if cascade is None:
                return _response(
                    True,
                    result={"canceled": False, "cascade": _idle_connector_cascade_status()},
                    warnings=warnings,
                    error=None,
                )

            already_terminal = False
            with cascade.lock:
                if cascade.status in {"completed", "partial_success", "failed", "canceled"}:
                    already_terminal = True
                else:
                    cascade.status = "canceling"
                    cascade.cancel_event.set()
            if already_terminal:
                result = _serialize_connector_cascade(cascade, request=request)
                return _response(
                    True,
                    result={"canceled": False, "cascade": result},
                    warnings=warnings,
                    error=None,
                )

            for source_state in cascade.sources.values():
                if (
                    source_state.bootstrap is not None
                    and _connector_bootstrap_is_running(source_state.bootstrap)
                ):
                    with suppress(Exception):
                        _terminate_connector_bootstrap(source_state.bootstrap)
                if source_state.sync is not None and _connector_bootstrap_is_running(source_state.sync):
                    with suppress(Exception):
                        _terminate_connector_bootstrap(source_state.sync)

            if cascade.worker_thread is not None and cascade.worker_thread.is_alive():
                cascade.worker_thread.join(timeout=1)

            bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
            sync_sessions = get_connector_command_sessions(app, kind="sync")
            auth_service = _connector_auth_service(app, config=app_config)
            if not auth_service.any_bootstrap_running() and not _connector_any_running(sync_sessions):
                _stop_vnc_runtime(app)

            result = _serialize_connector_cascade(cascade, request=request)
            return _response(
                True,
                result={"canceled": True, "cascade": result},
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/{source_id}/bootstrap/start")
    def start_connector_bootstrap(
        request: Request,
        source_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                assert_connector_operation_allowed(
                    session,
                    source_id=source_id,
                    operation="bootstrap",
                    config=app_config,
                )

            cascade_sessions = get_connector_cascade_sessions(app)
            if any(_connector_cascade_is_active(cascade) for cascade in cascade_sessions.values()):
                raise RuntimeError(
                    "connector cascade is already running; cancel or wait for completion before manual bootstrap"
                )

            service = _connector_auth_service(app, config=app_config)
            manifest = service.get_auth_status(source_id=source_id, validate_session=False).manifest
            capabilities = service.capabilities_for_source(source_id)
            uses_manual_browser_handoff = (
                manifest.runtime_kind == "builtin"
                and source_id == "lidl_plus_de"
                and capabilities.auth_kind == "oauth_pkce"
            )

            bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
            manual_bootstrap_sessions = service.session_registry.manual_oauth_sessions

            for existing_source, existing in bootstrap_sessions.items():
                if existing_source == source_id:
                    continue
                if _connector_bootstrap_is_running(existing):
                    raise RuntimeError(
                        f"connector bootstrap already running for source: {existing_source}"
                    )
            for existing_source, existing in manual_bootstrap_sessions.items():
                if existing_source == source_id:
                    continue
                if existing.finished_at is None and not existing.canceled:
                    raise RuntimeError(
                        f"connector bootstrap already running for source: {existing_source}"
                    )

            prev = bootstrap_sessions.get(source_id)
            existing_remote_url = _novnc_login_url(request)
            if prev is not None and _connector_bootstrap_is_running(prev):
                result = {
                    "source_id": source_id,
                    "reused": True,
                    "bootstrap": _serialize_connector_bootstrap(prev),
                    "remote_login_url": existing_remote_url,
                }
                if _connector_is_preview_source(source_id, config=app_config):
                    warnings.append(
                        _warning(
                            "preview connector bootstrap started; this connector is not live-validated yet",
                            code="connector_preview_bootstrap_started",
                    )
                    )
                return _response(True, result=result, warnings=warnings, error=None)
            manual_prev = manual_bootstrap_sessions.get(source_id)
            if manual_prev is not None and manual_prev.finished_at is None and not manual_prev.canceled:
                snapshot = service.get_bootstrap_status(source_id=source_id)
                result = {
                    "source_id": source_id,
                    "reused": True,
                    "bootstrap": _serialize_auth_bootstrap_snapshot(snapshot),
                    "remote_login_url": str(
                        service.get_auth_status(source_id=source_id, validate_session=False)
                        .metadata
                        .get("auth_start_url")
                        or existing_remote_url
                    ),
                }
                if _connector_is_preview_source(source_id, config=app_config):
                    warnings.append(
                        _warning(
                            "preview connector bootstrap started; this connector is not live-validated yet",
                            code="connector_preview_bootstrap_started",
                        )
                    )
                return _response(True, result=result, warnings=warnings, error=None)

            remote_login_url: str | None = None
            env: dict[str, str] | None = None
            if not uses_manual_browser_handoff:
                try:
                    _ensure_vnc_runtime(app)
                    remote_login_url = _novnc_login_url(request)
                    runtime = get_vnc_runtime(app)
                    if runtime is not None:
                        env = {
                            "DISPLAY": runtime.display,
                            "LIDLTOOL_AUTH_BROWSER_MODE": "remote_vnc",
                        }
                except Exception as exc:  # noqa: BLE001
                    warnings.append(
                        _warning(
                            f"remote browser session unavailable; falling back to local display ({exc})",
                            code="connector_remote_browser_session_unavailable",
                        )
                    )

            started = service.start_bootstrap(
                source_id=source_id,
                env=env,
            )
            if started.bootstrap is None:
                raise RuntimeError(f"failed to start connector bootstrap for source: {source_id}")
            bootstrap = bootstrap_sessions.get(source_id)

            result = {
                "source_id": source_id,
                "reused": started.status == "reused",
                "bootstrap": (
                    _serialize_connector_bootstrap(bootstrap)
                    if bootstrap is not None
                    else _serialize_auth_bootstrap_snapshot(started.bootstrap)
                ),
                "remote_login_url": remote_login_url or started.metadata.get("auth_start_url"),
            }
            if _connector_is_preview_source(
                manifest.source_id,
                config=app_config,
                manifest=manifest,
            ):
                warnings.append(
                    _warning(
                        "preview connector bootstrap started; this connector is not live-validated yet",
                        code="connector_preview_bootstrap_started",
                    )
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/connectors/{source_id}/bootstrap/status")
    def get_connector_bootstrap_status(
        request: Request,
        source_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)

            bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
            bootstrap = bootstrap_sessions.get(source_id)
            remote_login_url = _novnc_login_url(request)
            if bootstrap is None:
                service = _connector_auth_service(app, config=app_config)
                snapshot = service.get_bootstrap_status(source_id=source_id)
                result = _serialize_auth_bootstrap_snapshot(snapshot)
                result["remote_login_url"] = remote_login_url
                if snapshot.state == "running":
                    status = service.get_auth_status(source_id=source_id, validate_session=False)
                    manual_remote_login_url = str(status.metadata.get("auth_start_url") or "").strip()
                    if manual_remote_login_url:
                        result["remote_login_url"] = manual_remote_login_url
            else:
                result = dict(_serialize_connector_bootstrap(bootstrap))
                result["remote_login_url"] = remote_login_url
            if _connector_is_preview_source(source_id, config=app_config):
                warnings.append(
                    "preview connector status only; this connector is not live-validated yet"
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/{source_id}/bootstrap/cancel")
    def cancel_connector_bootstrap(
        request: Request,
        source_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)

            bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
            service = _connector_auth_service(app, config=app_config)
            canceled = service.cancel_bootstrap(source_id=source_id)
            result = {
                "source_id": source_id,
                "canceled": canceled.status == "canceled",
                "bootstrap": (
                    _serialize_auth_bootstrap_snapshot(canceled.bootstrap)
                    if canceled.bootstrap is not None
                    else None
                ),
            }
            if not service.any_bootstrap_running():
                _stop_vnc_runtime(app)
            if _connector_is_preview_source(source_id, config=app_config):
                warnings.append(
                    "preview connector cancellation only; this connector is not live-validated yet"
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/{source_id}/bootstrap/confirm")
    def confirm_connector_bootstrap(
        request: Request,
        source_id: str,
        payload: ConnectorBootstrapConfirmRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                assert_connector_operation_allowed(
                    session,
                    source_id=source_id,
                    operation="bootstrap",
                    config=app_config,
                )

            service = _connector_auth_service(app, config=app_config)
            confirmed = service.confirm_bootstrap(
                source_id=source_id,
                callback_url=payload.callback_url,
            )
            result = {
                "source_id": source_id,
                "confirmed": confirmed.ok,
                "auth_status": serialize_source_auth_status(
                    auth_service=service,
                    source_id=source_id,
                    validate_session=False,
                ),
            }
            if _connector_is_preview_source(source_id, config=app_config):
                warnings.append(
                    "preview connector confirmation only; this connector is not live-validated yet"
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/{source_id}/sync")
    def start_connector_sync(
        request: Request,
        source_id: str,
        full: bool = False,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                assert_connector_operation_allowed(
                    session,
                    source_id=source_id,
                    operation="sync",
                    config=app_config,
                )
                current_user_id = current_user.user_id
                current_username = current_user.username

            cascade_sessions = get_connector_cascade_sessions(app)
            if any(_connector_cascade_is_active(cascade) for cascade in cascade_sessions.values()):
                raise RuntimeError(
                    "connector cascade is already running; cancel or wait for completion before manual sync"
                )

            sync_extra_args: tuple[str, ...] = ()
            if current_username != SERVICE_USERNAME:
                sync_extra_args = (
                    "--option",
                    f"owner_user_id={current_user_id}",
                )

            command = _connector_command(
                app_config,
                source_id=source_id,
                operation="sync",
                full=full,
                extra_args=sync_extra_args,
            )
            if command is None:
                raise RuntimeError(f"sync not supported for source: {source_id}")

            sync_sessions = get_connector_command_sessions(app, kind="sync")
            existing = sync_sessions.get(source_id)
            if existing is not None and _connector_bootstrap_is_running(existing):
                return _response(
                    True,
                    result={
                        "source_id": source_id,
                        "reused": True,
                        "sync": _serialize_connector_bootstrap(existing),
                        "sync_status_url": f"/api/v1/sources/{source_id}/sync-status",
                    },
                    warnings=warnings,
                    error=None,
                )

            sync_session = _start_connector_command_session(
                app,
                source_id=source_id,
                command=command,
                config=app_config,
                session_kind="sync",
                thread_name=f"connector-sync-{source_id}",
            )

            if _connector_is_preview_source(source_id, config=app_config):
                warnings.append(
                    _warning(
                        "preview connector sync; this connector is not live-validated yet",
                        code="connector_preview_sync_started",
                    )
                )
            return _response(
                True,
                result={
                    "source_id": source_id,
                    "reused": False,
                    "sync": _serialize_connector_bootstrap(sync_session),
                    "sync_status_url": f"/api/v1/sources/{source_id}/sync-status",
                },
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    # Compatibility alias for older source-centric clients. Connector routes are canonical.
    @app.post("/api/v1/sources/{source_id}/sync")
    def start_source_sync_alias(
        request: Request,
        source_id: str,
        full: bool = False,
    ) -> Any:
        return start_connector_sync(
            request=request,
            source_id=source_id,
            full=full,
        )

    @app.get("/api/v1/connectors/{source_id}/sync/status")
    def get_connector_sync_status(
        request: Request,
        source_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)

            sync_sessions = get_connector_command_sessions(app, kind="sync")
            sync = sync_sessions.get(source_id)
            if sync is None:
                result: dict[str, Any] = {
                    "source_id": source_id,
                    "status": "idle",
                    "command": None,
                    "pid": None,
                    "started_at": None,
                    "finished_at": None,
                    "return_code": None,
                    "output_tail": [],
                    "can_cancel": False,
                }
            else:
                result = dict(_serialize_connector_bootstrap(sync))
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/sources/{source_id}/sync-status")
    def get_source_sync_status(
        request: Request,
        source_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                if not _source_is_visible(session=session, source_id=source_id, visibility=visibility):
                    raise RuntimeError("source not found")
                result = _serialize_source_sync_status(app, session, source_id=source_id)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/sources/{source_id}/workspace")
    def patch_source_workspace(
        request: Request,
        source_id: str,
        payload: SourceWorkspaceUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                source = session.get(Source, source_id)
                if source is None:
                    raise RuntimeError("source not found")
                can_manage = _owns_user_resource(
                    current_user,
                    resource_user_id=source.user_id,
                    resource_shared_group_id=source.shared_group_id,
                ) or resource_belongs_to_workspace(
                    visibility=visibility,
                    resource_user_id=source.user_id,
                    resource_shared_group_id=source.shared_group_id,
                )
                if not can_manage:
                    raise RuntimeError("source not found")
                target_shared_group_id: str | None = None
                if payload.workspace_kind == "shared_group":
                    target_shared_group_id = payload.shared_group_id or visibility.shared_group_id
                    if (
                        visibility.workspace_kind != "shared_group"
                        or visibility.shared_group_id is None
                        or target_shared_group_id != visibility.shared_group_id
                    ):
                        raise RuntimeError(
                            "shared workspace updates require the target workspace to be active"
                        )
                source.shared_group_id = target_shared_group_id
                source.updated_at = datetime.now(tz=UTC)
                session.flush()
                result = {
                    "source_id": source.id,
                    "user_id": source.user_id,
                    "shared_group_id": source.shared_group_id,
                    "workspace_kind": "shared_group" if source.shared_group_id else "personal",
                    "updated_at": source.updated_at.isoformat(),
                }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/transactions/{transaction_id}/workspace")
    def patch_transaction_workspace(
        request: Request,
        transaction_id: str,
        payload: TransactionWorkspaceUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                transaction = session.get(Transaction, transaction_id)
                if transaction is None:
                    raise RuntimeError("transaction not found")
                can_manage = _owns_user_resource(
                    current_user,
                    resource_user_id=transaction.user_id,
                    resource_shared_group_id=transaction.shared_group_id,
                ) or resource_belongs_to_workspace(
                    visibility=visibility,
                    resource_user_id=transaction.user_id,
                    resource_shared_group_id=transaction.shared_group_id,
                )
                if not can_manage:
                    raise RuntimeError("transaction not found")
                items = (
                    session.execute(
                        select(TransactionItem)
                        .where(TransactionItem.transaction_id == transaction.id)
                        .order_by(TransactionItem.line_no.asc(), TransactionItem.id.asc())
                    )
                    .scalars()
                    .all()
                )
                target_shared_group_id: str | None = None
                if payload.allocation_mode != "personal":
                    target_shared_group_id = payload.shared_group_id or visibility.shared_group_id
                    if (
                        visibility.workspace_kind != "shared_group"
                        or visibility.shared_group_id is None
                        or target_shared_group_id != visibility.shared_group_id
                    ):
                        raise RuntimeError(
                            "shared workspace allocations require the target workspace to be active"
                        )
                if payload.allocation_mode == "personal":
                    transaction.shared_group_id = None
                    for item in items:
                        item.shared_group_id = None
                elif payload.allocation_mode == "shared_receipt":
                    transaction.shared_group_id = target_shared_group_id
                    for item in items:
                        item.shared_group_id = target_shared_group_id
                else:
                    transaction.shared_group_id = None
                transaction.updated_at = datetime.now(tz=UTC)
                session.flush()
                allocation_mode = "personal"
                if transaction.shared_group_id:
                    allocation_mode = "shared_receipt"
                elif any(item.shared_group_id for item in items):
                    allocation_mode = "split_items"
                result = {
                    "transaction_id": transaction.id,
                    "user_id": transaction.user_id,
                    "shared_group_id": transaction.shared_group_id,
                    "source_id": transaction.source_id,
                    "allocation_mode": allocation_mode,
                    "updated_at": transaction.updated_at.isoformat(),
                }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/transactions/{transaction_id}/items/{item_id}/allocation")
    def patch_transaction_item_allocation(
        request: Request,
        transaction_id: str,
        item_id: str,
        payload: TransactionItemAllocationUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                transaction = session.get(Transaction, transaction_id)
                if transaction is None:
                    raise RuntimeError("transaction not found")
                can_manage = _owns_user_resource(
                    current_user,
                    resource_user_id=transaction.user_id,
                    resource_shared_group_id=transaction.shared_group_id,
                ) or resource_belongs_to_workspace(
                    visibility=visibility,
                    resource_user_id=transaction.user_id,
                    resource_shared_group_id=transaction.shared_group_id,
                )
                if not can_manage:
                    raise RuntimeError("transaction not found")
                if visibility.workspace_kind != "shared_group" or visibility.shared_group_id is None:
                    raise RuntimeError(
                        "item allocations can only be updated from an active shared workspace"
                    )
                item = session.get(TransactionItem, item_id)
                if item is None or item.transaction_id != transaction.id:
                    raise RuntimeError("transaction item not found")
                target_shared_group_id = visibility.shared_group_id
                if not payload.shared and transaction.shared_group_id == target_shared_group_id:
                    siblings = (
                        session.execute(
                            select(TransactionItem).where(
                                TransactionItem.transaction_id == transaction.id,
                                TransactionItem.id != item.id,
                            )
                        )
                        .scalars()
                        .all()
                    )
                    for sibling in siblings:
                        if sibling.shared_group_id is None:
                            sibling.shared_group_id = target_shared_group_id
                    transaction.shared_group_id = None
                item.shared_group_id = target_shared_group_id if payload.shared else None
                session.flush()
                result = {
                    "transaction_id": transaction.id,
                    "item_id": item.id,
                    "shared": item.shared_group_id is not None,
                    "shared_group_id": item.shared_group_id,
                }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/query/run")
    def post_query_run(
        request: Request,
        payload: QueryRunRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                payload_dict = payload.model_dump()
                visibility = _visibility_for_scope(current_user, payload_dict.get("scope"))
                result = run_workbench_query(
                    session,
                    payload_dict,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/query/dsl")
    def post_query_dsl(
        request: Request,
        payload: QueryDslRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            query_payload = parse_dsl_to_query(payload.dsl)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                query_payload["scope"] = visibility.scope
                result = run_workbench_query(session, query_payload, visibility=visibility)
            return _response(
                True,
                result={"query": query_payload, "result": result},
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/heatmap/weekday")
    def get_weekday_heatmap(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        value: str = "net",
        source_kind: str | None = None,
        tz_offset_minutes: int = 0,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            validated_tz_offset_minutes = _validate_tz_offset_minutes(tz_offset_minutes)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = weekday_heatmap(
                    session,
                    date_from=_parse_optional_iso_date(from_date),
                    date_to=_parse_optional_iso_date(to_date),
                    source_kinds=[source_kind] if source_kind else None,
                    value=value,
                    tz_offset_minutes=validated_tz_offset_minutes,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/heatmap/hour")
    def get_hour_heatmap(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        value: str = "net",
        source_kind: str | None = None,
        tz_offset_minutes: int = 0,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            validated_tz_offset_minutes = _validate_tz_offset_minutes(tz_offset_minutes)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = hour_heatmap(
                    session,
                    date_from=_parse_optional_iso_date(from_date),
                    date_to=_parse_optional_iso_date(to_date),
                    source_kind=source_kind,
                    value=value,
                    tz_offset_minutes=validated_tz_offset_minutes,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/heatmap/matrix")
    def get_timing_matrix(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        value: str = "net",
        source_kind: str | None = None,
        tz_offset_minutes: int = 0,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            validated_tz_offset_minutes = _validate_tz_offset_minutes(tz_offset_minutes)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = timing_matrix(
                    session,
                    date_from=_parse_optional_iso_date(from_date),
                    date_to=_parse_optional_iso_date(to_date),
                    source_kind=source_kind,
                    value=value,
                    tz_offset_minutes=validated_tz_offset_minutes,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/deposits")
    def get_deposit_analytics(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        source_ids: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = deposit_analytics(
                    session,
                    date_from=_parse_optional_iso_date(from_date),
                    date_to=_parse_optional_iso_date(to_date),
                    source_ids=_parse_source_ids(source_ids),
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/price-index")
    def get_price_index(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        grain: str = "month",
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = retailer_price_index(
                    session,
                    date_from=_parse_optional_iso_date(from_date),
                    date_to=_parse_optional_iso_date(to_date),
                    grain=grain,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/tools/exec")
    async def exec_python(
        request: Request,
    ) -> Any:
        """Execute arbitrary Python code with access to the lidltool database.

        The code runs in a subprocess using the same Python environment.
        The following variables are pre-available in the script's scope:
          - DB_PATH: str — absolute path to the SQLite database
          - conn: sqlite3.Connection — open read-only connection (use freely)
          - print(...) — output is captured and returned as 'output'

        Security: intended for Docker deployment where the container is the sandbox.
        On non-Docker installs, only admin/owner users should have access.
        """
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            if not app_config.http_tools_exec_enabled:
                raise HTTPException(status_code=404, detail="not found")
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)

            body = await request.json()
            code: str = body.get("code", "")
            timeout: int = min(int(body.get("timeout", 30)), 120)

            if not code or not code.strip():
                return _error_response(ValueError("code is required"))

            db_path = str(app_config.db_path)

            # Wrapper that pre-connects to the db and executes user code
            wrapper = f"""
import sqlite3, json, os, sys
from pathlib import Path

DB_PATH = {db_path!r}
conn = sqlite3.connect(f"file:{{DB_PATH}}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

try:
{chr(10).join("    " + line for line in code.splitlines())}
finally:
    conn.close()
"""
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", wrapper,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                return _error_response(TimeoutError(f"Code execution timed out after {timeout}s"))

            output = stdout.decode("utf-8", errors="replace").strip()
            error_output = stderr.decode("utf-8", errors="replace").strip()
            exit_code = proc.returncode

            return _response(
                exit_code == 0,
                result={
                    "output": output,
                    "stderr": error_output,
                    "exit_code": exit_code,
                },
                error=error_output if exit_code != 0 else None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/analytics/basket-compare")
    def post_basket_compare(
        request: Request,
        payload: BasketCompareRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = basket_compare(
                    session,
                    items=[item.model_dump() for item in payload.items],
                    net=payload.net,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/budget-rules")
    def get_budget_rules(
        request: Request,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = list_budget_rules(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/analytics/budget-rules")
    def post_budget_rule(
        request: Request,
        payload: BudgetRuleCreateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = create_budget_rule(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    scope_type=payload.scope_type,
                    scope_value=payload.scope_value,
                    period=payload.period,
                    amount_cents=payload.amount_cents,
                    currency=payload.currency,
                    active=payload.active,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/budget")
    def get_budget_utilization(
        request: Request,
        year: int | None = None,
        month: int | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = budget_utilization(
                    session,
                    year=year,
                    month=month,
                    visibility=visibility,
                    user_id=current_user.user_id,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/budget/months/{year}/{month}")
    def get_budget_month_view(
        request: Request,
        year: int,
        month: int,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = get_budget_month(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    year=year,
                    month=month,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.put("/api/v1/budget/months/{year}/{month}")
    def put_budget_month_view(
        request: Request,
        year: int,
        month: int,
        payload: BudgetMonthUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = upsert_budget_month(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    year=year,
                    month=month,
                    planned_income_cents=payload.planned_income_cents,
                    target_savings_cents=payload.target_savings_cents,
                    opening_balance_cents=payload.opening_balance_cents,
                    currency=payload.currency,
                    notes=payload.notes,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/budget/months/{year}/{month}/summary")
    def get_budget_month_summary(
        request: Request,
        year: int,
        month: int,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = monthly_budget_summary(
                    session,
                    user_id=current_user.user_id,
                    year=year,
                    month=month,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/cashflow-entries")
    def get_cashflow_entries(
        request: Request,
        year: int,
        month: int,
        direction: str | None = None,
        category: str | None = None,
        reconciled: bool | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = list_cashflow_entries(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    year=year,
                    month=month,
                    direction=direction,
                    category=category,
                    reconciled=reconciled,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/cashflow-entries")
    def post_cashflow_entry(
        request: Request,
        payload: CashflowEntryCreateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = create_cashflow_entry(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    effective_date=payload.effective_date,
                    direction=payload.direction,
                    category=payload.category,
                    amount_cents=payload.amount_cents,
                    currency=payload.currency,
                    description=payload.description,
                    source_type=payload.source_type,
                    linked_transaction_id=payload.linked_transaction_id,
                    linked_recurring_occurrence_id=payload.linked_recurring_occurrence_id,
                    notes=payload.notes,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/cashflow-entries/{entry_id}")
    def patch_cashflow_entry(
        request: Request,
        entry_id: str,
        payload: CashflowEntryUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = update_cashflow_entry(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    entry_id=entry_id,
                    payload=payload.model_dump(exclude_unset=True),
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/cashflow-entries/{entry_id}")
    def remove_cashflow_entry(
        request: Request,
        entry_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = delete_cashflow_entry(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    entry_id=entry_id,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/groceries/summary")
    def get_groceries_summary(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                from_dt, to_dt = _normalize_dashboard_window(from_date, to_date)
                result = grocery_workspace_summary(
                    session,
                    from_date=from_dt,
                    to_date=to_dt,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/merchants/summary")
    def get_merchants_summary(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        scope: str = "personal",
        search: str | None = None,
        limit: int = 40,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                from_dt, to_dt = _normalize_dashboard_window(from_date, to_date)
                result = merchant_workspace_summary(
                    session,
                    from_date=from_dt,
                    to_date=to_dt,
                    visibility=visibility,
                    search=search,
                    limit=max(1, min(limit, 100)),
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/reports/templates")
    def get_report_templates(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                from_dt, to_dt = _normalize_dashboard_window(from_date, to_date)
                result = build_report_templates(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    from_date=from_dt.date(),
                    to_date=to_dt.date(),
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/goals/summary")
    def get_goals_summary(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                from_dt, to_dt = _normalize_dashboard_window(from_date, to_date)
                result = goals_summary(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    from_date=from_dt.date(),
                    to_date=to_dt.date(),
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/goals")
    def get_goals(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        scope: str = "personal",
        include_inactive: bool = False,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                from_dt, to_dt = _normalize_dashboard_window(from_date, to_date)
                result = list_goals(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    from_date=from_dt.date(),
                    to_date=to_dt.date(),
                    include_inactive=include_inactive,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/goals")
    def post_goal(
        request: Request,
        payload: GoalCreateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = create_goal(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    name=payload.name,
                    goal_type=payload.goal_type,
                    target_amount_cents=payload.target_amount_cents,
                    currency=payload.currency,
                    period=payload.period,
                    category=payload.category,
                    merchant_name=payload.merchant_name,
                    recurring_bill_id=payload.recurring_bill_id,
                    target_date=payload.target_date,
                    notes=payload.notes,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/goals/{goal_id}")
    def patch_goal(
        request: Request,
        goal_id: str,
        payload: GoalUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = update_goal(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    goal_id=goal_id,
                    payload=payload.model_dump(exclude_unset=True),
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/goals/{goal_id}")
    def remove_goal(
        request: Request,
        goal_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = delete_goal(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    goal_id=goal_id,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/notifications")
    def get_notifications(
        request: Request,
        limit: int = 20,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = list_notifications(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    limit=max(1, min(limit, 50)),
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/notifications/{notification_id}")
    def patch_notification(
        request: Request,
        notification_id: str,
        payload: NotificationUpdateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = update_notification(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                    notification_id=notification_id,
                    unread=payload.unread,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/notifications/mark-all-read")
    def post_mark_all_notifications_read(
        request: Request,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = mark_all_notifications_read(
                    session,
                    user_id=current_user.user_id,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/patterns")
    def get_patterns_summary(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = patterns_summary(
                    session,
                    date_from=_parse_optional_iso_date(from_date),
                    date_to=_parse_optional_iso_date(to_date),
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/query/saved")
    def get_saved_queries(
        request: Request,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = list_saved_queries(session, visibility=visibility)
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/query/saved")
    def post_saved_query(
        request: Request,
        payload: SavedQueryCreateRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = create_saved_query(
                    session,
                    visibility=visibility,
                    user_id=current_user.user_id,
                    name=payload.name,
                    description=payload.description,
                    query_json=payload.query_json,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/query/saved/{query_id}")
    def get_saved_query_by_id(
        request: Request,
        query_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = get_saved_query(session, query_id=query_id, visibility=visibility)
            if result is None:
                raise RuntimeError("saved query not found")
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/query/saved/{query_id}")
    def delete_saved_query_by_id(
        request: Request,
        query_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                deleted = delete_saved_query(session, query_id=query_id, visibility=visibility)
            if not deleted:
                raise RuntimeError("saved query not found")
            return _response(True, result={"query_id": query_id, "deleted": True}, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/settings/ai")
    def get_ai_settings(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            oauth_connected = bool(
                app_config.ai_oauth_provider and get_ai_oauth_access_token(app_config)
            )
            api_credentials_ready = bool(
                app_config.ai_enabled
                and (app_config.ai_base_url or "").strip()
                and (app_config.ai_model or "").strip()
                and _resolve_ai_api_key_token(app_config)
            )
            local_runtime_enabled = (
                bool(app_config.local_text_model_enabled)
                if app_config.local_text_model_enabled is not None
                else bool(app_config.item_categorizer_enabled)
            )
            local_runtime_base_url = (
                (app_config.local_text_model_base_url or "").strip()
                or (app_config.item_categorizer_base_url or "").strip()
            )
            local_runtime_status = "not_configured"
            local_runtime_ready = False
            if local_runtime_enabled:
                from lidltool.ai.runtime import RuntimePolicyMode, RuntimeTask, resolve_runtime
                from urllib import request as urllib_request

                local_resolution = resolve_runtime(
                    app_config,
                    task=RuntimeTask.PI_AGENT,
                    policy_mode=RuntimePolicyMode.LOCAL_ONLY,
                )
                local_runtime_status = local_resolution.status_code
                if local_resolution.selected and local_runtime_base_url:
                    models_url = f"{local_runtime_base_url.rstrip('/')}/models"
                    try:
                        with urllib_request.urlopen(models_url, timeout=3.0) as response:
                            local_runtime_ready = response.status == 200
                        if not local_runtime_ready:
                            local_runtime_status = "unhealthy"
                    except Exception:  # noqa: BLE001
                        local_runtime_status = "unreachable"
            categorization_runtime_enabled = bool(app_config.item_categorizer_enabled)
            categorization_provider = _configured_categorization_provider(app_config)
            categorization_client = (
                resolve_item_categorizer_runtime_client(app_config)
                if categorization_runtime_enabled
                else None
            )
            categorization_health = categorization_client.health() if categorization_client is not None else None
            result = {
                "enabled": api_credentials_ready or oauth_connected or local_runtime_ready,
                "base_url": app_config.ai_base_url,
                "model": app_config.ai_model,
                "api_key_set": bool(app_config.ai_api_key_encrypted),
                "oauth_provider": app_config.ai_oauth_provider,
                "oauth_connected": oauth_connected,
                "oauth_model": _configured_oauth_chat_model(app_config),
                "remote_enabled": api_credentials_ready or oauth_connected,
                "local_runtime_enabled": local_runtime_enabled,
                "local_runtime_ready": local_runtime_ready,
                "local_runtime_status": local_runtime_status,
                "categorization_enabled": categorization_runtime_enabled,
                "categorization_provider": categorization_provider,
                "categorization_base_url": app_config.item_categorizer_base_url,
                "categorization_api_key_set": bool(app_config.item_categorizer_api_key_encrypted),
                "categorization_model": _configured_categorization_model(app_config),
                "categorization_runtime_ready": bool(categorization_health and categorization_health.status == "ready"),
                "categorization_runtime_status": categorization_health.status if categorization_health else "disabled",
            }
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/settings/ocr")
    def get_ocr_settings(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            result = {
                "default_provider": app_config.ocr_default_provider,
                "fallback_enabled": bool(app_config.ocr_fallback_enabled),
                "fallback_provider": app_config.ocr_fallback_provider,
                "glm_local_base_url": app_config.ocr_glm_local_base_url,
                "glm_local_api_mode": app_config.ocr_glm_local_api_mode,
                "glm_local_model": app_config.ocr_glm_local_model,
                "openai_base_url": app_config.ocr_openai_base_url or app_config.ai_base_url,
                "openai_model": app_config.ocr_openai_model or app_config.ai_model,
                "openai_credentials_ready": bool(
                    app_config.ocr_openai_api_key
                    or app_config.ai_api_key_encrypted
                    or get_ai_oauth_access_token(app_config)
                ),
            }
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/settings/ocr")
    def post_ocr_settings(
        request: Request,
        payload: OCRSettingsUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)

            app_config.ocr_default_provider = payload.default_provider
            app_config.ocr_fallback_enabled = bool(payload.fallback_enabled)
            app_config.ocr_fallback_provider = (
                payload.fallback_provider if payload.fallback_enabled else None
            )
            if (
                app_config.ocr_fallback_enabled
                and app_config.ocr_fallback_provider == app_config.ocr_default_provider
            ):
                return _response(
                    True,
                    result={"ok": False, "error": "fallback provider must differ from primary provider"},
                    error=None,
                )
            app_config.ocr_glm_local_base_url = (
                payload.glm_local_base_url.strip()
                if isinstance(payload.glm_local_base_url, str)
                and payload.glm_local_base_url.strip()
                else app_config.ocr_glm_local_base_url
            )
            if payload.glm_local_api_mode is not None:
                app_config.ocr_glm_local_api_mode = payload.glm_local_api_mode
            app_config.ocr_glm_local_model = (
                payload.glm_local_model.strip()
                if isinstance(payload.glm_local_model, str)
                and payload.glm_local_model.strip()
                else app_config.ocr_glm_local_model
            )
            if isinstance(payload.openai_base_url, str):
                app_config.ocr_openai_base_url = payload.openai_base_url.strip() or None
            if isinstance(payload.openai_model, str):
                app_config.ocr_openai_model = payload.openai_model.strip() or None

            if app_config.ocr_default_provider == "glm_ocr_local":
                if not (app_config.ocr_glm_local_base_url or "").strip():
                    return _response(
                        True,
                        result={"ok": False, "error": "GLM-OCR local base URL is required"},
                        error=None,
                    )
                if not (app_config.ocr_glm_local_model or "").strip():
                    return _response(
                        True,
                        result={"ok": False, "error": "GLM-OCR local model is required"},
                        error=None,
                    )
            if (
                app_config.ocr_fallback_enabled
                and app_config.ocr_fallback_provider == "openai_compatible"
                and not (
                    app_config.ocr_openai_api_key
                    or app_config.ai_api_key_encrypted
                    or get_ai_oauth_access_token(app_config)
                )
            ):
                return _response(
                    True,
                    result={
                        "ok": False,
                        "error": "OpenAI-compatible OCR fallback requires AI API credentials or OCR-specific API key",
                    },
                    error=None,
                )

            persist_ocr_settings(context.config_path, app_config)
            return _response(True, result={"ok": True, "error": None}, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/settings/ai")
    def post_ai_settings(
        request: Request,
        payload: AISettingsUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)

            base_url = (
                payload.base_url.strip()
                if isinstance(payload.base_url, str)
                else (app_config.ai_base_url or "").strip()
            )
            model = payload.model.strip()
            candidate_api_key = (
                payload.api_key.strip()
                if isinstance(payload.api_key, str) and payload.api_key.strip()
                else _resolve_ai_bearer_token(app_config, context.config_path)
            )

            if not base_url:
                return _response(
                    True,
                    result={"ok": False, "error": "base_url is required"},
                    error=None,
                )
            if not model:
                return _response(
                    True,
                    result={"ok": False, "error": "model is required"},
                    error=None,
                )
            if not candidate_api_key:
                return _response(
                    True,
                    result={"ok": False, "error": "api_key is required"},
                    error=None,
                )

            validated, validation_error = _validate_ai_completion(
                base_url=base_url,
                api_key=candidate_api_key,
                model=model,
            )
            if not validated:
                return _response(
                    True,
                    result={"ok": False, "error": validation_error or "provider validation failed"},
                    error=None,
                )

            app_config.ai_base_url = base_url
            app_config.ai_model = model
            app_config.ai_enabled = True
            if isinstance(payload.api_key, str) and payload.api_key.strip():
                set_ai_api_key(app_config, payload.api_key.strip())

            persist_ai_settings(context.config_path, app_config)
            app_config = _reload_request_context_config(context)
            return _response(
                True,
                result={"ok": True, "error": None},
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/settings/ai/chat")
    def post_ai_chat_settings(
        request: Request,
        payload: AIChatSettingsUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = _reload_request_context_config(context)
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)

            normalized_oauth_model = (payload.oauth_model or "").strip() or DEFAULT_CHATGPT_CHAT_MODEL
            app_config.ai_oauth_model = normalized_oauth_model
            persist_ai_settings(context.config_path, app_config)
            _reload_request_context_config(context)
            return _response(True, result={"ok": True, "error": None}, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/settings/ai/categorization")
    def post_ai_categorization_settings(
        request: Request,
        payload: AICategorizationSettingsUpdateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = _reload_request_context_config(context)
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)

            app_config.item_categorizer_enabled = bool(payload.enabled)
            app_config.item_categorizer_provider = payload.provider

            if not app_config.item_categorizer_enabled:
                persist_item_categorizer_settings(context.config_path, app_config)
                _reload_request_context_config(context)
                return _response(True, result={"ok": True, "error": None}, error=None)

            if payload.provider == "oauth_codex":
                if not _chatgpt_oauth_connected(app_config):
                    return _response(
                        True,
                        result={"ok": False, "error": "Connect ChatGPT Codex first to use subscription categorization"},
                        error=None,
                    )
                app_config.item_categorizer_base_url = None
                set_item_categorizer_api_key(app_config, None)
                app_config.item_categorizer_allow_remote = True
                app_config.item_categorizer_model = (
                    (payload.model or "").strip()
                    or _default_categorization_model(
                        provider="oauth_codex",
                        base_url=None,
                        fallback_model=app_config.item_categorizer_model,
                    )
                )
                persist_item_categorizer_settings(context.config_path, app_config)
                _reload_request_context_config(context)
                return _response(True, result={"ok": True, "error": None}, error=None)

            base_url = (
                payload.base_url.strip()
                if isinstance(payload.base_url, str) and payload.base_url.strip()
                else (app_config.item_categorizer_base_url or app_config.ai_base_url or "").strip()
            )
            model = (
                payload.model.strip()
                if isinstance(payload.model, str) and payload.model.strip()
                else _default_categorization_model(
                    provider="api_compatible",
                    base_url=base_url,
                    fallback_model=app_config.ai_model,
                )
            )
            candidate_api_key = (
                payload.api_key.strip()
                if isinstance(payload.api_key, str) and payload.api_key.strip()
                else get_item_categorizer_api_key(app_config)
                or get_ai_api_key(app_config)
            )
            if not base_url:
                return _response(
                    True,
                    result={"ok": False, "error": "base_url is required for API-compatible categorization"},
                    error=None,
                )
            if not candidate_api_key:
                return _response(
                    True,
                    result={"ok": False, "error": "api_key is required for API-compatible categorization"},
                    error=None,
                )
            validated, validation_error = _validate_ai_completion(
                base_url=base_url,
                api_key=candidate_api_key,
                model=model,
            )
            if not validated:
                return _response(
                    True,
                    result={"ok": False, "error": validation_error or "provider validation failed"},
                    error=None,
                )
            app_config.item_categorizer_base_url = base_url
            app_config.item_categorizer_model = model
            app_config.item_categorizer_allow_remote = True
            if isinstance(payload.api_key, str):
                set_item_categorizer_api_key(app_config, payload.api_key.strip() or None)
            persist_item_categorizer_settings(context.config_path, app_config)
            _reload_request_context_config(context)
            return _response(True, result={"ok": True, "error": None}, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/settings/ai/disconnect")
    def post_ai_disconnect(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = _reload_request_context_config(context)
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)

            app_config.ai_enabled = False
            app_config.ai_base_url = None
            app_config.ai_model = "grok-3-mini"
            set_ai_api_key(app_config, None)
            app_config.ai_oauth_provider = None
            set_ai_oauth_access_token(app_config, None)
            set_ai_oauth_refresh_token(app_config, None)
            app_config.ai_oauth_expires_at = None
            persist_ai_settings(context.config_path, app_config)
            if _configured_categorization_provider(app_config) == "oauth_codex":
                app_config.item_categorizer_enabled = False
                app_config.item_categorizer_allow_remote = False
                persist_item_categorizer_settings(context.config_path, app_config)
            _reload_request_context_config(context)

            return _response(True, result={"ok": True}, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/settings/ai/oauth/start")
    def post_ai_oauth_start(
        request: Request,
        payload: AIOAuthStartRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)

            if payload.provider != "openai-codex":
                raise RuntimeError(f"OAuth provider not supported yet: {payload.provider}")

            state = secrets.token_urlsafe(24)
            code_verifier = secrets.token_urlsafe(72)
            auth_url = _build_openai_codex_auth_url(
                state=state,
                code_challenge=_pkce_code_challenge(code_verifier),
            )
            _set_ai_oauth_state(
                app,
                status="pending",
                error=None,
                provider=payload.provider,
            )

            thread = threading.Thread(
                target=_run_openai_oauth_callback_server,
                kwargs={
                    "app": app,
                    "config": app_config,
                    "config_path": context.config_path,
                    "provider": payload.provider,
                    "expected_state": state,
                    "code_verifier": code_verifier,
                },
                daemon=True,
                name="ai-oauth-callback",
            )
            thread.start()

            return _response(
                True,
                result={
                    "auth_url": auth_url,
                    "expires_in": AI_OAUTH_EXPIRES_IN_SECONDS,
                },
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/settings/ai/oauth/status")
    def get_ai_oauth_status(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
            runtime_state = _get_ai_oauth_state(app)
            status = str(runtime_state.get("status") or "pending")
            error_message = runtime_state.get("error")
            if (
                status == "connected"
                or (
                    app_config.ai_oauth_provider
                    and bool(get_ai_oauth_access_token(app_config))
                )
            ):
                return _response(
                    True,
                    result={"status": "connected", "error": None},
                    error=None,
                )
            if status == "error":
                return _response(
                    True,
                    result={"status": "error", "error": str(error_message) if error_message else None},
                    error=None,
                )
            return _response(
                True,
                result={"status": "pending", "error": None},
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/settings/ai/agent-config")
    def get_ai_agent_config(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                auth_context = _require_user_session_auth_context(
                    request=request,
                    session=session,
                    config=app_config,
                )
                session_record = auth_context.session_record or create_user_session(
                    session,
                    user=auth_context.user,
                    metadata=_session_client_metadata(
                        request=request,
                        session_mode=SESSION_MODE_TOKEN,
                        device_label="stream-proxy",
                        client_name="chat-stream-proxy",
                        client_platform="server",
                    ),
                )
                auth_token = issue_session_token(
                    user=auth_context.user,
                    session_id=session_record.session_id,
                    config=app_config,
                )
            result = {
                "proxy_url": "",
                "auth_token": auth_token,
                "model": _preferred_chat_model(app_config),
                "default_model": _configured_local_chat_model(app_config),
                "local_model": _configured_local_chat_model(app_config),
                "preferred_model": _preferred_chat_model(app_config),
                "oauth_provider": app_config.ai_oauth_provider,
                "oauth_connected": _chatgpt_oauth_connected(app_config),
                "available_models": _available_chat_models(app_config),
            }
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    async def _chatgpt_codex_stream(*, payload: StreamProxyRequest, bearer_token: str) -> StreamingResponse:
        """Stream via the ChatGPT Codex Responses API (chatgpt.com/backend-api/codex/responses)."""
        import base64 as _b64

        # Extract chatgpt-account-id from JWT sub claim
        try:
            jwt_parts = bearer_token.split(".")
            jwt_payload = json.loads(_b64.urlsafe_b64decode(jwt_parts[1] + "=="))
            account_id = str(jwt_payload.get("sub") or "")
        except Exception:  # noqa: BLE001
            account_id = ""

        # Build input messages from pi-agent-core context.
        # pi-agent-core message roles: "user", "assistant", "toolResult"
        # assistant content items: {type: "text", text: "..."} or {type: "toolCall", id, name, arguments}
        # toolResult messages: {role: "toolResult", toolCallId, toolName, content: [{type:"text",text:"..."}]}
        input_messages: list[dict[str, Any]] = []
        system_prompt = payload.context.systemPrompt or ""
        for msg in payload.context.messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")

            if role == "toolResult":
                # Tool result → Responses API function_call_output
                call_id = str(msg.get("toolCallId", ""))
                content = msg.get("content", "")
                if isinstance(content, list):
                    output = " ".join(
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in content
                    ).strip()
                else:
                    output = str(content or "")
                input_messages.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": output,
                })
                continue

            content = msg.get("content", "")
            if role == "assistant":
                if isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        if part.get("type") == "text" and part.get("text", "").strip():
                            input_messages.append({"role": "assistant", "content": part["text"]})
                        elif part.get("type") == "toolCall":
                            # Assistant tool call → Responses API function_call item
                            import json as _json
                            args = part.get("arguments", {})
                            input_messages.append({
                                "type": "function_call",
                                "call_id": str(part.get("id", "")),
                                "name": str(part.get("name", "")),
                                "arguments": _json.dumps(args) if isinstance(args, dict) else str(args),
                            })
                elif isinstance(content, str) and content.strip():
                    input_messages.append({"role": "assistant", "content": content})

            elif role == "user":
                if isinstance(content, list):
                    text = " ".join(
                        p.get("text", "") if isinstance(p, dict) and p.get("type") == "text" else ""
                        for p in content
                    ).strip()
                else:
                    text = str(content or "")
                if text:
                    input_messages.append({"role": "user", "content": text})

        # Build tools — pi-agent-core sends tools in {name, description, parameters} format,
        # not OpenAI's {type: "function", function: {...}} format.
        codex_tools: list[dict[str, Any]] = []
        raw_tools = payload.context.tools or []
        for tool in raw_tools:
            if not isinstance(tool, dict):
                continue
            name = tool.get("name", "")
            description = tool.get("description", "")
            parameters = tool.get("parameters", {})
            if name:
                codex_tools.append({
                    "type": "function",
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                    "strict": False,
                })

        request_body: dict[str, Any] = {
            "model": payload.model.id,
            "instructions": system_prompt,
            "input": input_messages,
            "store": False,
            "stream": True,
        }
        if codex_tools:
            request_body["tools"] = codex_tools

        _sse_log = open("/tmp/codex_sse.log", "a")  # noqa: SIM115

        def _log_yield(data: dict[str, Any]) -> str:
            _sse_log.write("YIELD " + json.dumps(data) + "\n")
            _sse_log.flush()
            return _sse_data(data)

        async def event_stream() -> Any:
            active_tool_call: dict[str, Any] | None = None
            tool_content_index = 1  # contentIndex for the next tool call (increments per call)
            args_buffer = ""        # Accumulate function-call arg deltas in Python
            has_tool_calls = False

            yield _log_yield({"type": "start"})
            yield _log_yield({"type": "text_start", "contentIndex": 0})

            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    "https://chatgpt.com/backend-api/codex/responses",
                    headers={
                        "Authorization": f"Bearer {bearer_token}",
                        "OpenAI-Beta": "responses=experimental",
                        "originator": "codex_cli_rs",
                        "chatgpt-account-id": account_id,
                        "content-type": "application/json",
                    },
                    json=request_body,
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise RuntimeError(f"Codex API error {resp.status_code}: {body.decode()[:300]}")

                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        etype = event.get("type", "")
                        # Log every interesting Codex event
                        if etype and not etype.startswith("response.output_text"):
                            _sse_log.write("CODEX " + json.dumps(event) + "\n")
                            _sse_log.flush()

                        if etype == "response.output_text.delta":
                            delta = event.get("delta", "")
                            if delta:
                                yield _sse_data({"type": "text_delta", "contentIndex": 0, "delta": delta})

                        elif etype == "response.function_call_arguments.delta":
                            # Accumulate in Python; emit the complete JSON at output_item.done
                            delta = event.get("delta", "")
                            if delta:
                                args_buffer += delta

                        elif etype == "response.output_item.added":
                            item = event.get("item", {})
                            if item.get("type") == "function_call":
                                active_tool_call = item
                                args_buffer = ""
                                has_tool_calls = True
                                yield _log_yield({
                                    "type": "toolcall_start",
                                    "contentIndex": tool_content_index,
                                    "id": item.get("call_id", f"call_{tool_content_index}"),
                                    "toolName": item.get("name", ""),
                                })

                        elif etype == "response.output_item.done":
                            item = event.get("item", {})
                            if item.get("type") == "function_call" and active_tool_call is not None:
                                # Prefer the definitive args from the done event; fall back to buffer
                                complete_args = item.get("arguments", "") or args_buffer
                                _sse_log.write(f"ARGS complete_args={complete_args!r} args_buffer={args_buffer!r}\n")
                                _sse_log.flush()
                                if complete_args:
                                    yield _log_yield({
                                        "type": "toolcall_delta",
                                        "contentIndex": tool_content_index,
                                        "delta": complete_args,
                                    })
                                yield _log_yield({
                                    "type": "toolcall_end",
                                    "contentIndex": tool_content_index,
                                })
                                tool_content_index += 1
                                active_tool_call = None
                                args_buffer = ""

                        elif etype == "response.completed":
                            resp_obj = event.get("response", {})
                            usage = resp_obj.get("usage") or {}
                            yield _log_yield({"type": "text_end", "contentIndex": 0})
                            yield _log_yield({
                                "type": "done",
                                "reason": "toolUse" if has_tool_calls else "stop",
                                "usage": {
                                    "input": usage.get("input_tokens", 0),
                                    "output": usage.get("output_tokens", 0),
                                    "cacheRead": 0,
                                    "cacheWrite": 0,
                                    "totalTokens": usage.get("total_tokens", 0),
                                    "cost": None,
                                },
                            })
                            return

            # Fallback end if stream closed without response.completed
            yield _sse_data({"type": "text_end", "contentIndex": 0})
            yield _sse_data({"type": "done", "reason": "stop", "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0, "cost": None}})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @app.post("/api/stream")
    async def post_stream_proxy(
        request: Request,
        payload: StreamProxyRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions

            with session_scope(sessions) as session:
                _authorize_stream_proxy_request(request=request, session=session, config=app_config)

            selected_model_id = _resolve_selected_chat_model(
                app_config,
                payload.model.id if isinstance(payload.model.id, str) else None,
            )
            payload.model.id = selected_model_id

            if _should_route_stream_via_chatgpt(app_config, selected_model_id):
                oauth_token = _resolve_ai_oauth_bearer_token(app_config, context.config_path)
                if not oauth_token:
                    raise RuntimeError("AI provider credentials are not configured")
                return await _chatgpt_codex_stream(payload=payload, bearer_token=oauth_token)

            openai_messages = _to_openai_messages(
                system_prompt=payload.context.systemPrompt,
                messages=payload.context.messages,
            )
            openai_tools = _to_openai_tools(payload.context.tools)
            if not openai_messages:
                raise RuntimeError("at least one message is required")
            from lidltool.ai.runtime import RuntimeTask, StreamChatRequest

            runtime = _resolve_pi_agent_runtime_for_model(
                app_config,
                selected_model_id=selected_model_id,
            )
            if openai_tools and runtime.capabilities().local:
                LOGGER.info("pi_agent.local_runtime_tools_disabled provider=%s", runtime.provider_kind.value)
                openai_tools = []
            model_id = _runtime_model_name(
                runtime,
                explicit_model=selected_model_id,
                app_config=app_config,
            )

            async def event_stream() -> Any:
                async for event in runtime.stream_chat(
                    StreamChatRequest(
                        task=RuntimeTask.PI_AGENT,
                        model_name=model_id,
                        messages=openai_messages,
                        tools=openai_tools,
                        temperature=payload.options.temperature,
                        max_tokens=payload.options.maxTokens,
                    )
                ):
                    response_event = {"type": event.type}
                    if event.content_index is not None:
                        response_event["contentIndex"] = event.content_index
                    if event.delta is not None:
                        response_event["delta"] = event.delta
                    if event.tool_call_id is not None:
                        response_event["id"] = event.tool_call_id
                    if event.tool_name is not None:
                        response_event["toolName"] = event.tool_name
                    if event.reason is not None:
                        response_event["reason"] = event.reason
                    if event.usage:
                        response_event["usage"] = event.usage
                    yield _sse_data(response_event)

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/products")
    def get_products(
        request: Request,
        search: str | None = None,
        source_kind: str | None = None,
        category_id: str | None = None,
        limit: int = 50,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = search_products(
                    session,
                    search=search,
                    source_kind=source_kind,
                    category_id=category_id,
                    limit=limit,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/products/categories")
    def get_product_categories(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = list_product_categories(session)
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/products")
    def post_product(
        request: Request,
        payload: ProductCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = create_product(
                    session,
                    canonical_name=payload.canonical_name,
                    brand=payload.brand,
                    default_unit=payload.default_unit,
                    gtin_ean=payload.gtin_ean,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/products/seed")
    def post_product_seed(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = seed_products_from_items(session)
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/products/cluster")
    def post_product_cluster(
        request: Request,
        payload: ProductClusterRequest | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
            result = cluster_products_with_llm(
                sessions=sessions,
                config=app_config,
                force=payload.force if payload is not None else False,
            )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/products/cluster/{job_id}")
    def get_product_cluster_status(
        request: Request,
        job_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
            result = get_cluster_job_progress(job_id)
            if result is None:
                raise RuntimeError("cluster job not found")
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/products/{product_id}")
    def get_product(
        request: Request,
        product_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = get_product_detail(session, product_id=product_id)
            if result is None:
                raise RuntimeError("product not found")
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/products/{product_id}/merge")
    def post_product_merge(
        request: Request,
        product_id: str,
        payload: ProductMergeRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = merge_products(
                    session,
                    target_product_id=product_id,
                    source_product_ids=payload.source_product_ids,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/products/{product_id}/price-series")
    def get_product_price_series(
        request: Request,
        product_id: str,
        from_date: str | None = None,
        to_date: str | None = None,
        grain: str = "day",
        net: bool = True,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = product_price_series(
                    session,
                    product_id=product_id,
                    date_from=_parse_optional_iso_date(from_date),
                    date_to=_parse_optional_iso_date(to_date),
                    grain=grain,
                    net=net,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/products/{product_id}/purchases")
    def get_product_purchases(
        request: Request,
        product_id: str,
        from_date: str | None = None,
        to_date: str | None = None,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = product_purchases(
                    session,
                    product_id=product_id,
                    date_from=_parse_optional_iso_date(from_date),
                    date_to=_parse_optional_iso_date(to_date),
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/products/match")
    def post_manual_product_match(
        request: Request,
        payload: ManualProductMatchRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = manual_product_match(
                    session,
                    product_id=payload.product_id,
                    raw_name=payload.raw_name,
                    source_kind=payload.source_kind,
                    raw_sku=payload.raw_sku,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/compare/groups")
    def get_compare_groups(
        request: Request,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = list_comparison_groups(session)
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/compare/groups")
    def post_compare_group(
        request: Request,
        payload: ComparisonGroupCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = create_comparison_group(
                    session,
                    name=payload.name,
                    unit_standard=payload.unit_standard,
                    notes=payload.notes,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/compare/groups/{group_id}/series")
    def get_compare_group_series(
        request: Request,
        group_id: str,
        from_date: str | None = None,
        to_date: str | None = None,
        grain: str = "month",
        net: bool = True,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = comparison_group_series(
                    session,
                    group_id=group_id,
                    date_from=_parse_optional_iso_date(from_date),
                    date_to=_parse_optional_iso_date(to_date),
                    grain=grain,
                    net=net,
                    visibility=visibility,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/compare/groups/{group_id}/members")
    def post_compare_group_member(
        request: Request,
        group_id: str,
        payload: ComparisonGroupMemberCreateRequest,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)
                result = add_comparison_group_member(
                    session,
                    group_id=group_id,
                    product_id=payload.product_id,
                    weight=payload.weight,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/quality/recategorize")
    def post_quality_recategorize(
        request: Request,
        payload: QualityRecategorizeRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            from lidltool.analytics.scope import visible_transaction_ids_subquery

            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            normalized_source_id = (
                payload.source_id.strip() if isinstance(payload.source_id, str) and payload.source_id.strip() else None
            )
            include_suspect_model_items = bool(payload.include_suspect_model_items)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id
                visibility = _visibility_for_scope(current_user, scope)
                visible_ids = visible_transaction_ids_subquery(visibility)
                stmt = select(Transaction.id).where(Transaction.id.in_(visible_ids))
                if normalized_source_id:
                    stmt = stmt.where(Transaction.source_id == normalized_source_id)
                if payload.only_fallback_other or include_suspect_model_items:
                    normalized_category = func.lower(func.trim(func.coalesce(TransactionItem.category, "")))
                    normalized_method = func.lower(func.trim(func.coalesce(TransactionItem.category_method, "")))
                    raw_source_category = func.trim(func.coalesce(func.json_extract(TransactionItem.raw_payload, "$.category"), ""))
                    candidate_filters: list[ColumnElement[bool]] = []
                    if payload.only_fallback_other:
                        candidate_filters.append(
                            or_(normalized_category.in_(["", "other"]), normalized_method == "fallback_other")
                        )
                    if include_suspect_model_items:
                        candidate_filters.append(
                            or_(
                                normalized_method == "qwen_local",
                                (normalized_method == "source_native") & (raw_source_category == ""),
                            )
                        )
                    stmt = (
                        stmt.join(TransactionItem, TransactionItem.transaction_id == Transaction.id)
                        .where(TransactionItem.is_deposit.is_(False))
                        .where(normalized_method != "manual")
                        .where(or_(*candidate_filters))
                        .distinct()
                    )
                stmt = stmt.order_by(Transaction.purchased_at.desc(), Transaction.id.desc())
                if payload.max_transactions is not None:
                    stmt = stmt.limit(payload.max_transactions)
                transaction_ids = session.execute(stmt).scalars().all()
            job = _start_quality_recategorize_job(
                request.app,
                sessions=sessions,
                config=app_config,
                requested_by_user_id=current_user_id,
                transaction_ids=list(transaction_ids),
                source_id=normalized_source_id,
                only_fallback_other=bool(payload.only_fallback_other),
                include_suspect_model_items=include_suspect_model_items,
                max_transactions=payload.max_transactions,
            )
            return _response(
                True,
                result={"job": _serialize_quality_recategorize_job(job)},
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/quality/recategorize/status")
    def get_quality_recategorize_status(
        request: Request,
        job_id: str,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id
                current_user_is_admin = current_user.is_admin
            jobs = get_quality_recategorize_jobs(request.app)
            lock = get_quality_recategorize_lock(request.app)
            with lock:
                job = jobs.get(job_id)
                if job is None:
                    raise HTTPException(status_code=404, detail="quality recategorize job not found")
                if job.requested_by_user_id != current_user_id and not current_user_is_admin:
                    raise HTTPException(status_code=404, detail="quality recategorize job not found")
                result = _serialize_quality_recategorize_job(job)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/quality/unmatched-items")
    def get_quality_unmatched_items(
        request: Request,
        limit: int = 200,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = unmatched_items_quality(session, limit=limit, visibility=visibility)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/quality/low-confidence-ocr")
    def get_quality_low_confidence_ocr(
        request: Request,
        threshold: float = 0.85,
        limit: int = 200,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = low_confidence_ocr_quality(
                    session, threshold=threshold, limit=limit, visibility=visibility
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/reliability/slo")
    def get_reliability_slo(
        request: Request,
        window_hours: int = 24,
        sync_p95_target_ms: int = 2500,
        analytics_p95_target_ms: int = 2000,
        min_success_rate: float = 0.97,
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                _require_admin_auth_context(request=request, session=session, config=app_config)
                result = compute_endpoint_slo_summary(
                    session,
                    window_hours=window_hours,
                    sync_p95_target_ms=sync_p95_target_ms,
                    analytics_p95_target_ms=analytics_p95_target_ms,
                    min_success_rate=min_success_rate,
                ).as_dict()
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/review-queue/{document_id}")
    def get_review_queue_detail(
        request: Request,
        document_id: str,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = review_queue_detail(
                    session, document_id=document_id, visibility=visibility
                )
                if result is None:
                    raise RuntimeError("review item not found")
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/review-queue/{document_id}/approve")
    def approve_review_item(
        request: Request,
        document_id: str,
        payload: ReviewDecisionRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                details = review_queue_detail(
                    session, document_id=document_id, visibility=visibility
                )
                if details is None:
                    raise RuntimeError("review item not found")
                service = CorrectionService(session=session)
                result = service.approve_document(
                    document_id=document_id,
                    actor_id=payload.actor_id,
                    reason=payload.reason,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/review-queue/{document_id}/reject")
    def reject_review_item(
        request: Request,
        document_id: str,
        payload: ReviewDecisionRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                details = review_queue_detail(
                    session, document_id=document_id, visibility=visibility
                )
                if details is None:
                    raise RuntimeError("review item not found")
                service = CorrectionService(session=session)
                result = service.reject_document(
                    document_id=document_id,
                    actor_id=payload.actor_id,
                    reason=payload.reason,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/review-queue/{document_id}/transaction")
    def patch_review_transaction(
        request: Request,
        document_id: str,
        payload: ReviewCorrectionRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                details = review_queue_detail(
                    session, document_id=document_id, visibility=visibility
                )
                if details is None:
                    raise RuntimeError("review item not found")
                service = CorrectionService(session=session)
                result = service.correct_transaction(
                    document_id=document_id,
                    corrections=payload.corrections,
                    actor_id=payload.actor_id,
                    reason=payload.reason,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/review-queue/{document_id}/items/{item_id}")
    def patch_review_item(
        request: Request,
        document_id: str,
        item_id: str,
        payload: ReviewCorrectionRequest,
        scope: str = "personal",
    ) -> Any:
        try:
            context = _resolve_request_context(request)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                details = review_queue_detail(
                    session, document_id=document_id, visibility=visibility
                )
                if details is None:
                    raise RuntimeError("review item not found")
                service = CorrectionService(session=session)
                result = service.correct_item(
                    document_id=document_id,
                    item_id=item_id,
                    corrections=payload.corrections,
                    actor_id=payload.actor_id,
                    reason=payload.reason,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.websocket("/api/v1/connectors/vnc/ws")
    async def connector_vnc_ws(websocket: WebSocket) -> None:
        context = _resolve_request_context(websocket)  # type: ignore[arg-type]
        app_config = context.config
        sessions = context.sessions
        with session_scope(sessions) as session:
            try:
                _require_user_session_auth_context(
                    request=websocket,
                    session=session,
                    config=app_config,
                )
            except HTTPException as exc:
                close_code = 4401 if int(exc.status_code) == 401 else 4403
                reason = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                await websocket.close(code=close_code, reason=reason)
                return

        runtime = get_vnc_runtime(app)
        if not _vnc_runtime_is_healthy(runtime):
            await websocket.close(code=4404, reason="no active vnc session")
            return

        assert runtime is not None
        await websocket.accept()
        reader, writer = await asyncio.open_connection("127.0.0.1", runtime.vnc_port)

        async def relay_tcp_to_ws() -> None:
            try:
                while True:
                    chunk = await reader.read(65536)
                    if not chunk:
                        break
                    await websocket.send_bytes(chunk)
            except Exception:
                return

        relay_task = asyncio.create_task(relay_tcp_to_ws())
        try:
            while True:
                message = await websocket.receive()
                msg_type = message.get("type")
                if msg_type == "websocket.disconnect":
                    break
                if msg_type != "websocket.receive":
                    continue
                data_bytes = cast(bytes | None, message.get("bytes"))
                data_text = cast(str | None, message.get("text"))
                if data_bytes is not None:
                    writer.write(data_bytes)
                    await writer.drain()
                elif data_text is not None:
                    writer.write(data_text.encode("utf-8"))
                    await writer.drain()
        except WebSocketDisconnect:
            pass
        finally:
            relay_task.cancel()
            with suppress(Exception):
                await relay_task
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    novnc_dir = _novnc_static_dir()
    if novnc_dir is not None:
        app.mount("/vnc", StaticFiles(directory=novnc_dir, html=True), name="novnc")

    frontend_dist = _frontend_dist_dir()
    if frontend_dist.exists():
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")

    _register_runtime_route_auth_policy(
        RouteAuthPolicy("GET", "/api/v1/dashboard/years", "authenticated_principal")
    )
    _register_runtime_route_auth_policy(
        RouteAuthPolicy("POST", "/api/mobile-pair/v1/sessions", "authenticated_user_session")
    )
    _register_runtime_route_auth_policy(
        RouteAuthPolicy("POST", "/api/mobile-pair/v1/handshake", "public")
    )
    _register_runtime_route_auth_policy(
        RouteAuthPolicy("POST", "/api/mobile-captures/v1", "authenticated_principal")
    )
    _register_runtime_route_auth_policy(
        RouteAuthPolicy("GET", "/api/mobile-sync/v1/changes", "authenticated_principal")
    )
    _register_runtime_route_auth_policy(
        RouteAuthPolicy("POST", "/api/mobile-sync/v1/manual-transactions", "authenticated_principal")
    )
    _assert_route_auth_matrix_complete(app)
    return app


def main() -> None:
    os.environ.setdefault("LIDLTOOL_HTTP_BIND_HOST", "127.0.0.1")
    uvicorn.run("lidltool.api.http_server:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
