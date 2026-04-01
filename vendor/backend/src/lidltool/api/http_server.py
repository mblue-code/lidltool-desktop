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
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from lidltool.ai.clustering import cluster_products_with_llm, get_cluster_job_progress
from lidltool.ai.config import (
    get_ai_api_key,
    get_ai_oauth_access_token,
    persist_ai_settings,
    set_ai_api_key,
    set_ai_oauth_access_token,
    set_ai_oauth_refresh_token,
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
from lidltool.analytics.queries import (
    dashboard_retailer_composition,
    dashboard_savings_breakdown,
    dashboard_totals,
    dashboard_trends,
    export_receipts,
    review_queue,
    review_queue_detail,
    search_transactions,
    transaction_detail,
)
from lidltool.analytics.query_dsl import parse_dsl_to_query
from lidltool.analytics.scope import VisibilityContext, parse_scope
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
    _token_secret,
    clear_session_cookie,
    get_current_user,
    issue_session_token,
    set_session_cookie,
)
from lidltool.auth.agent_keys import create_user_agent_key
from lidltool.auth.user_auth import UserAuthError, decode_token, verify_password
from lidltool.auth.users import (
    SERVICE_USERNAME,
    create_local_user,
    ensure_service_user,
    get_user_by_username,
    human_user_count,
    set_user_password,
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
    serialize_connector_bootstrap,
    start_connector_command_session,
    terminate_connector_bootstrap,
)
from lidltool.connectors.discovery import connector_discovery_payload
from lidltool.connectors.lifecycle import (
    connector_lifecycle_record_payload,
    install_connector,
    set_connector_enabled,
    uninstall_connector,
    update_connector_config,
)
from lidltool.connectors.runtime.execution import ConnectorExecutionService
from lidltool.db.audit import list_transaction_history
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import (
    ChatMessage,
    ChatRun,
    ChatThread,
    Document,
    Source,
    Transaction,
    TransactionItem,
    User,
    UserApiKey,
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
from lidltool.ingest.overrides import OverrideService
from lidltool.ops import backup_database
from lidltool.recurring.service import RecurringBillsService
from lidltool.reliability.metrics import compute_endpoint_slo_summary, record_endpoint_metric
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
    *,
    db: str | None,
    config_path: str | None,
) -> tuple[AppConfig, sessionmaker[Session]]:
    config = build_config(
        config_path=Path(config_path).expanduser() if config_path else None,
        db_override=Path(db).expanduser() if db else None,
    )
    db_url = database_url(config)
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    return config, session_factory(engine)


@dataclass(slots=True)
class RequestContext:
    config: AppConfig
    sessions: sessionmaker[Session]
    config_path: Path
    db_override: str | None
    config_override: str | None


@dataclass(slots=True)
class ConnectorCascadeSourceState:
    source_id: str
    state: str = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    bootstrap: ConnectorBootstrapSession | None = None
    sync: ConnectorBootstrapSession | None = None


@dataclass(slots=True)
class ConnectorCascadeSession:
    user_id: str
    source_ids: list[str]
    full: bool
    status: str
    started_at: datetime
    lock: threading.Lock
    cancel_event: threading.Event
    sources: dict[str, ConnectorCascadeSourceState]
    current_source_id: str | None = None
    current_step: str | None = None
    finished_at: datetime | None = None
    worker_thread: threading.Thread | None = None


@dataclass(slots=True)
class VncRuntime:
    display: str
    vnc_port: int
    xvfb_process: subprocess.Popen[str]
    x11vnc_process: subprocess.Popen[str]


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


def _extract_optional_request_field(request: Request, field_name: str) -> str | None:
    query_value = request.query_params.get(field_name)
    if query_value:
        return query_value
    return None


def _parse_source_ids(source_ids: str | None) -> list[str] | None:
    if source_ids is None:
        return None
    values = [value.strip() for value in source_ids.split(",")]
    filtered = [value for value in values if value]
    return filtered or None


def _resolve_request_context(
    request: Request,
    *,
    db: str | None = None,
    config_path: str | None = None,
) -> RequestContext:
    resolved_db = db if db is not None else _extract_optional_request_field(request, "db")
    resolved_config = (
        config_path
        if config_path is not None
        else _extract_optional_request_field(request, "config")
    )
    resolved_config_path = (
        Path(resolved_config).expanduser().resolve()
        if resolved_config
        else default_config_file()
    )
    cached = getattr(request.state, "request_context", None)
    if (
        isinstance(cached, RequestContext)
        and cached.db_override == resolved_db
        and cached.config_override == resolved_config
    ):
        return cached
    app_config, sessions = _create_session_factory(db=resolved_db, config_path=resolved_config)
    context = RequestContext(
        config=app_config,
        sessions=sessions,
        config_path=resolved_config_path,
        db_override=resolved_db,
        config_override=resolved_config,
    )
    request.state.request_context = context
    return context


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
    mode = str(config.openclaw_auth_mode or "warn_only").lower()
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
        "invalid field value": "invalid_field_value",
        "invalid json payload": "invalid_json_payload",
        "invalid or expired session token": "invalid_or_expired_session_token",
        "invalid related resource reference": "invalid_related_resource_reference",
        "invalid request payload": "invalid_request_payload",
        "invalid source; register source before upload": "invalid_source_for_upload",
        "invalid username or password": "auth_invalid_credentials",
        "message content is required": "message_content_required",
        "missing required field": "missing_required_field",
        "missing retryable sources; no failed or remaining sources to retry": "connector_retryable_sources_missing",
        "missing token signing secret": "missing_token_signing_secret",
        "rate limit exceeded; retry after retry-after seconds": "rate_limited",
        "resource conflict": "resource_conflict",
        "service not ready": "service_not_ready",
        "session user not found": "session_user_not_found",
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
    api_key = _header_api_key(request)
    if api_key:
        digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
        return f"api_key:{digest}"
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
    buckets = cast(dict[str, list[float]], request.app.state.http_rate_limit_buckets)
    lock = cast(Any, request.app.state.http_rate_limit_lock)
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
    resolved = get_current_user(request=request, session=session, config=config, required=False)
    if resolved is not None:
        return resolved
    if human_user_count(session) == 0:
        return ensure_service_user(session)
    if required:
        raise HTTPException(status_code=401, detail="authentication required")
    return ensure_service_user(session)


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
    return VisibilityContext(
        user_id=user.user_id,
        is_service=(user.username == SERVICE_USERNAME),
        scope=parse_scope(scope),
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
    if visibility.is_service:
        return source.user_id in {None, visibility.user_id}
    return source.user_id == visibility.user_id


def _source_is_visible(
    *,
    session: Session,
    source_id: str,
    visibility: VisibilityContext,
) -> bool:
    source = session.get(Source, source_id)
    if source is None:
        return False
    if visibility.is_service:
        return source.user_id in {None, visibility.user_id}
    return source.user_id == visibility.user_id


def _owns_user_resource(user: User, *, resource_user_id: str | None) -> bool:
    if user.username == SERVICE_USERNAME:
        return resource_user_id in {None, user.user_id}
    return resource_user_id == user.user_id


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


def _load_owned_chat_thread(*, session: Session, user: User, thread_id: str) -> ChatThread:
    thread = session.get(ChatThread, thread_id)
    if thread is None or thread.archived_at is not None:
        raise RuntimeError("chat thread not found")
    if not _owns_user_resource(user, resource_user_id=thread.user_id):
        raise HTTPException(status_code=404, detail="chat thread not found")
    return thread


def _should_autotitle_thread(thread: ChatThread, first_user_message: str) -> bool:
    default_title = _default_chat_title_for_message(first_user_message)
    return thread.title in {"New chat", default_title}


def _schedule_chat_title_generation(
    *,
    db: str | None,
    config_path: str | None,
    thread_id: str,
) -> None:
    def _job() -> None:
        try:
            app_config, sessions = _create_session_factory(db=db, config_path=config_path)
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
                app_config,
                Path(config_path).expanduser().resolve() if config_path else None,
            )
            if not token:
                return
            base_url = (app_config.ai_base_url or "").strip()
            if not base_url:
                return
            model = (app_config.ai_model or "").strip() or "gpt-5.2-codex"

            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=token)
            completion = client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_tokens=24,
                messages=[
                    {
                        "role": "system",
                        "content": "Generate a concise conversation title with 5 words or fewer.",
                    },
                    {
                        "role": "user",
                        "content": (
                            "Summarize this conversation in 5 words or fewer.\n\n"
                            f"{transcript}"
                        ),
                    },
                ],
            )
            raw_title = None
            if completion.choices:
                raw_title = completion.choices[0].message.content
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
    started_at = getattr(app.state, "started_at", datetime.now(tz=UTC))
    if isinstance(started_at, datetime):
        uptime_seconds = max(int((datetime.now(tz=UTC) - started_at).total_seconds()), 0)
        started_at_iso = started_at.isoformat()
    else:
        uptime_seconds = 0
        started_at_iso = datetime.now(tz=UTC).isoformat()
    return {
        "service": "lidltool-http-api",
        "version": str(app.version),
        "build": str(getattr(app.state, "build", os.getenv("LIDLTOOL_BUILD", "dev"))),
        "started_at": started_at_iso,
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.now(tz=UTC).isoformat(),
    }


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
    scheduler = getattr(app.state, "automation_scheduler", None)
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
    runtime = cast(VncRuntime | None, getattr(app.state, "vnc_runtime", None))
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
    app.state.vnc_runtime = None


def _ensure_vnc_runtime(app: FastAPI) -> VncRuntime:
    existing = cast(VncRuntime | None, getattr(app.state, "vnc_runtime", None))
    if _vnc_runtime_is_healthy(existing):
        return cast(VncRuntime, existing)
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
    app.state.vnc_runtime = runtime
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
) -> list[str] | None:
    resolved = ConnectorExecutionService(config=config).build_command(
        source_id=source_id,
        operation=operation,
        extra_args=("--full",) if operation == "sync" and full else (),
    )
    if resolved is None:
        return None
    return list(resolved.command)


def _connector_auth_service(app: FastAPI, *, config: AppConfig) -> ConnectorAuthOrchestrationService:
    execution = ConnectorExecutionService(config=config)
    registry = cast(ConnectorAuthSessionRegistry, app.state.connector_auth_sessions)
    return ConnectorAuthOrchestrationService(
        config=config,
        session_registry=registry,
        connector_builder=execution.build_receipt_connector,
        repo_root=_repo_root(),
        process_factory=subprocess.Popen,
    )


def _connector_bootstrap_is_running(session: ConnectorBootstrapSession) -> bool:
    return connector_bootstrap_is_running(session)


def _serialize_connector_bootstrap(session: ConnectorBootstrapSession) -> dict[str, Any]:
    snapshot = serialize_connector_bootstrap(session)
    return {
        "source_id": snapshot.source_id,
        "status": snapshot.state,
        "command": " ".join(snapshot.command or ()),
        "pid": snapshot.pid,
        "started_at": snapshot.started_at.isoformat() if snapshot.started_at is not None else None,
        "finished_at": (
            snapshot.finished_at.isoformat() if snapshot.finished_at is not None else None
        ),
        "return_code": snapshot.return_code,
        "output_tail": list(snapshot.output_tail),
        "can_cancel": snapshot.can_cancel,
    }


def _terminate_connector_bootstrap(session: ConnectorBootstrapSession) -> None:
    terminate_connector_bootstrap(session)


def _connector_any_running(
    sessions: dict[str, ConnectorBootstrapSession],
) -> bool:
    return any_connector_bootstrap_running(sessions)


def _connector_process_env(app: FastAPI, *, config: AppConfig) -> dict[str, str]:
    env = os.environ.copy()
    env["LIDLTOOL_DB"] = str(config.db_path)
    env["LIDLTOOL_CONFIG_DIR"] = str(config.config_dir)
    if config.db_url:
        env["LIDLTOOL_DB_URL"] = config.db_url
    if config.credential_encryption_key:
        env["LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY"] = config.credential_encryption_key
    runtime = cast(VncRuntime | None, getattr(app.state, "vnc_runtime", None))
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
    sessions_attr: str,
    thread_name: str,
) -> ConnectorBootstrapSession:
    sessions = cast(dict[str, ConnectorBootstrapSession], getattr(app.state, sessions_attr))
    return start_connector_command_session(
        ConnectorAuthSessionRegistry(sessions),
        source_id=source_id,
        command=command,
        cwd=_repo_root(),
        env=_connector_process_env(app, config=config),
        process_factory=subprocess.Popen,
        thread_name=thread_name,
    )


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
    warnings: list[str],
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
    cascade_sessions = cast(dict[str, ConnectorCascadeSession], app.state.connector_cascade_sessions)
    cascade_sessions[user_id] = cascade
    worker.start()

    if any(source_id != "lidl_plus_de" for source_id in source_ids):
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
    sessions = cast(dict[str, ConnectorCascadeSession], app.state.connector_cascade_sessions)
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
                sessions_attr="connector_bootstrap_sessions",
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
                sessions_attr="connector_sync_sessions",
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


AI_OAUTH_CALLBACK_HOST = "127.0.0.1"
AI_OAUTH_CALLBACK_PORT = 1455
AI_OAUTH_CALLBACK_PATH = "/auth/callback"
AI_OAUTH_REDIRECT_URI = f"http://localhost:{AI_OAUTH_CALLBACK_PORT}{AI_OAUTH_CALLBACK_PATH}"
AI_OAUTH_EXPIRES_IN_SECONDS = 300
_OPENAI_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


def _set_ai_oauth_state(
    app: FastAPI,
    *,
    status: Literal["pending", "connected", "error"],
    error: str | None = None,
    provider: str | None = None,
) -> None:
    lock = cast(threading.Lock, app.state.ai_oauth_lock)
    with lock:
        app.state.ai_oauth_state = {
            "status": status,
            "error": error,
            "provider": provider,
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }


def _get_ai_oauth_state(app: FastAPI) -> dict[str, Any]:
    lock = cast(threading.Lock, app.state.ai_oauth_lock)
    with lock:
        raw = cast(dict[str, Any], app.state.ai_oauth_state)
        return dict(raw)


def _pkce_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _build_openai_codex_auth_url(*, state: str, code_challenge: str) -> str:
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


def _exchange_openai_oauth_code(*, code: str, code_verifier: str) -> dict[str, Any]:
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
            callback_state = (params.get("state") or [None])[0]
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

            oauth_error = (params.get("error") or [None])[0]
            if oauth_error:
                description = (params.get("error_description") or [""])[0]
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

            code = (params.get("code") or [None])[0]
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
                config.ai_enabled = True
                config.ai_base_url = "https://api.openai.com/v1"
                if config.ai_model not in {"gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.1-codex-max", "gpt-5.2", "gpt-5.1-codex-mini"}:
                    config.ai_model = "gpt-5.2-codex"
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
        server = ThreadingHTTPServer((AI_OAUTH_CALLBACK_HOST, AI_OAUTH_CALLBACK_PORT), CallbackHandler)
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


def _resolve_ai_bearer_token(
    config: AppConfig,
    config_path: Path | None = None,
    *,
    prefer_oauth: bool = True,
) -> str | None:
    oauth_token = get_ai_oauth_access_token(config) if prefer_oauth else None
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
    return get_ai_api_key(config)


def _authorize_stream_proxy_request(*, request: Request, session: Session, config: AppConfig) -> None:
    expected_api_key = (config.openclaw_api_key or "").strip()
    provided_api_key = _header_api_key(request)
    if expected_api_key and provided_api_key == expected_api_key:
        return
    if provided_api_key:
        try:
            claims = decode_token(token=provided_api_key, secret=_token_secret(config))
            user = session.get(User, claims["sub"])
            if user is not None:
                return
        except UserAuthError:
            pass
    if request.cookies.get(SESSION_COOKIE_NAME):
        user = get_current_user(request=request, session=session, config=config, required=False)
        if user is not None:
            return
    raise HTTPException(status_code=401, detail="authentication required")


def _normalize_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                chunks.append(text)
        return "\n".join(chunks).strip()
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
    return ""


def _to_openai_messages(
    *,
    system_prompt: str | None,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    if isinstance(system_prompt, str) and system_prompt.strip():
        converted.append({"role": "system", "content": system_prompt.strip()})
    for message in messages:
        role = str(message.get("role") or "user").strip().lower()
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"
        raw_content = message.get("content")
        if role == "assistant" and isinstance(raw_content, list):
            text_chunks: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            for item in raw_content:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "")
                if item_type == "text" and isinstance(item.get("text"), str):
                    text_chunks.append(str(item.get("text")))
                    continue
                if item_type != "toolCall":
                    continue
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                tool_call_id = str(item.get("id") or f"toolcall_{len(tool_calls)}")
                arguments = item.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                tool_calls.append(
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(arguments, separators=(",", ":")),
                        },
                    }
                )
            if tool_calls:
                converted_message: dict[str, Any] = {
                    "role": "assistant",
                    "tool_calls": tool_calls,
                }
                text_content = "\n".join(text_chunks).strip()
                if text_content:
                    converted_message["content"] = text_content
                converted.append(converted_message)
                continue
        content = _normalize_message_content(message.get("content"))
        if not content and role != "tool":
            continue
        converted_message: dict[str, Any] = {"role": role, "content": content}
        if role == "tool":
            tool_call_id = message.get("tool_call_id") or message.get("toolCallId")
            if isinstance(tool_call_id, str) and tool_call_id:
                converted_message["tool_call_id"] = tool_call_id
        converted.append(converted_message)
    return converted


def _to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools:
        name = str(tool.get("name") or "").strip()
        if not name:
            continue
        description = str(tool.get("description") or "").strip()
        parameters = tool.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {"type": "object", "properties": {}}
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )
    return converted


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


class ManualTransactionItemRequest(BaseModel):
    name: str
    line_total_cents: int
    qty: float = 1.0
    unit: str | None = None
    unit_price_cents: int | None = None
    category: str | None = None
    line_no: int | None = None
    source_item_id: str | None = None
    family_shared: bool = False
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
    family_share_mode: Literal["receipt", "items", "none", "inherit"] = "inherit"
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


DEFAULT_LOCAL_CHAT_MODEL = "Qwen/Qwen3.5-0.8B"
DEFAULT_CHATGPT_CHAT_MODEL = "gpt-5.2-codex"


def _configured_local_chat_model(app_config: AppConfig) -> str:
    model_id = (app_config.ai_model or "").strip()
    return model_id or DEFAULT_LOCAL_CHAT_MODEL


def _chatgpt_oauth_connected(app_config: AppConfig) -> bool:
    return bool(
        app_config.ai_oauth_provider == "openai-codex"
        and get_ai_oauth_access_token(app_config)
    )


def _preferred_chat_model(app_config: AppConfig) -> str:
    if _chatgpt_oauth_connected(app_config):
        return DEFAULT_CHATGPT_CHAT_MODEL
    return _configured_local_chat_model(app_config)


def _available_chat_models(app_config: AppConfig) -> list[dict[str, Any]]:
    local_model = _configured_local_chat_model(app_config)
    local_label = "Qwen" if "qwen" in local_model.lower() else "Local model"
    return [
        {
            "id": local_model,
            "label": local_label,
            "source": "local",
            "enabled": True,
        },
        {
            "id": DEFAULT_CHATGPT_CHAT_MODEL,
            "label": "ChatGPT",
            "source": "oauth",
            "enabled": _chatgpt_oauth_connected(app_config),
        },
    ]


def _should_route_stream_via_chatgpt(app_config: AppConfig, model_id: str) -> bool:
    return _chatgpt_oauth_connected(app_config) and model_id == DEFAULT_CHATGPT_CHAT_MODEL


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


class AuthSetupRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


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


class SourceSharingRequest(BaseModel):
    family_share_mode: Literal["all", "manual", "none"]


class ConnectorCascadeStartRequest(BaseModel):
    source_ids: list[str] = Field(min_length=1)
    full: bool = False


class ConnectorCascadeRetryRequest(BaseModel):
    full: bool | None = None
    include_skipped: bool = True


class ConnectorConfigUpdateRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    clear_secret_keys: list[str] = Field(default_factory=list)


class ConnectorUninstallRequest(BaseModel):
    purge_config: bool = False


class TransactionSharingRequest(BaseModel):
    family_share_mode: Literal["receipt", "items", "none", "inherit"]


class TransactionItemSharingRequest(BaseModel):
    family_shared: bool


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


def _manual_item_payload(items: list[ManualTransactionItemRequest]) -> list[ManualItemInput]:
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
                family_shared=item.family_shared,
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
        cascade_sessions = cast(
            dict[str, ConnectorCascadeSession],
            getattr(app.state, "connector_cascade_sessions", {}),
        )
        if any(_connector_cascade_is_active(cascade) for cascade in cascade_sessions.values()):
            logger.info("connector.live_sync.skipped (cascade active)")
            continue
        for source_id in source_ids:
            try:
                sync_sessions = cast(
                    dict[str, ConnectorBootstrapSession],
                    getattr(app.state, "connector_sync_sessions", {}),
                )
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
                    sessions_attr="connector_sync_sessions",
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


def create_app() -> FastAPI:
    base_config = build_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        config = base_config
        validate_config(config)
        db_url = database_url(config)
        migrate_db(db_url)
        engine = create_engine_for_url(db_url)
        sessions = session_factory(engine)
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
            bootstrap_sessions = cast(
                dict[str, ConnectorBootstrapSession],
                getattr(app.state, "connector_bootstrap_sessions", {}),
            )
            for session in bootstrap_sessions.values():
                try:
                    _terminate_connector_bootstrap(session)
                except Exception:  # noqa: BLE001
                    pass
            sync_sessions = cast(
                dict[str, ConnectorBootstrapSession],
                getattr(app.state, "connector_sync_sessions", {}),
            )
            for session in sync_sessions.values():
                try:
                    _terminate_connector_bootstrap(session)
                except Exception:  # noqa: BLE001
                    pass
            cascade_sessions = cast(
                dict[str, ConnectorCascadeSession],
                getattr(app.state, "connector_cascade_sessions", {}),
            )
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
            scheduler.stop()

    app = FastAPI(title="lidltool OCR API", version="1", lifespan=lifespan)
    app.state.started_at = datetime.now(tz=UTC)
    app.state.build = os.getenv("LIDLTOOL_BUILD", "dev")
    app.state.http_rate_limit_buckets = {}
    app.state.http_rate_limit_lock = threading.Lock()
    app.state.connector_bootstrap_sessions = {}
    app.state.connector_auth_sessions = ConnectorAuthSessionRegistry(
        app.state.connector_bootstrap_sessions
    )
    app.state.connector_sync_sessions = {}
    app.state.connector_cascade_sessions = {}
    app.state.connector_cascade_sessions_lock = threading.Lock()
    app.state.vnc_runtime = None
    app.state.ai_oauth_lock = threading.Lock()
    app.state.ai_oauth_state = {
        "status": "pending",
        "error": None,
        "provider": None,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }

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
                "checks": {"process": {"ok": True, "detail": "running"}},
                "meta": _service_metadata(app),
            },
            warnings=[],
            error=None,
        )

    @app.get("/api/v1/ready")
    def ready(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> JSONResponse:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            db_ok, db_detail = _readiness_db_check(context.sessions)
            storage_ok, storage_detail = _readiness_storage_check(context.config)
            scheduler_ok, scheduler_detail = _readiness_scheduler_check(app, context.config)
            checks = {
                "db": {"ok": db_ok, "detail": db_detail},
                "storage": {"ok": storage_ok, "detail": storage_detail},
                "scheduler": {"ok": scheduler_ok, "detail": scheduler_detail},
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
                        "meta": _service_metadata(app),
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                required = human_user_count(session) == 0
            return _response(True, result={"required": required}, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/auth/setup")
    def auth_setup(
        request: Request,
        payload: AuthSetupRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> JSONResponse:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                if human_user_count(session) > 0:
                    raise RuntimeError("setup already completed")
                user = create_local_user(
                    session,
                    username=payload.username,
                    password=payload.password,
                    display_name=payload.display_name,
                    is_admin=True,
                )
                token = issue_session_token(user=user, config=context.config)
                result = _serialize_current_user(user)
            response = JSONResponse(
                content=_response(True, result=result, warnings=[], error=None),
                status_code=200,
            )
            set_session_cookie(response, token=token)
            return response
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/auth/login")
    def auth_login(
        request: Request,
        payload: AuthLoginRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> JSONResponse:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                user = get_user_by_username(session, username=payload.username)
                if (
                    user is None
                    or user.username == SERVICE_USERNAME
                    or not verify_password(payload.password, user.password_hash)
                ):
                    raise HTTPException(status_code=401, detail="invalid username or password")
                token = issue_session_token(user=user, config=context.config)
                result = _serialize_current_user(user)
            response = JSONResponse(
                content=_response(True, result=result, warnings=[], error=None),
                status_code=200,
            )
            set_session_cookie(response, token=token)
            return response
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/auth/logout")
    def auth_logout() -> JSONResponse:
        response = JSONResponse(content=_response(True, result={"logged_out": True}))
        clear_session_cookie(response)
        return response

    @app.get("/api/v1/auth/me")
    def auth_me(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                user = get_current_user(
                    request=request,
                    session=session,
                    config=context.config,
                    required=True,
                )
                if user is None:
                    raise HTTPException(status_code=401, detail="authentication required")
                result = _serialize_current_user(user)
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/users/me/preferences")
    def patch_my_user_preferences(
        request: Request,
        payload: UserLocalePreferenceUpdateRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                current_user = get_current_user(
                    request=request,
                    session=session,
                    config=context.config,
                    required=True,
                )
                if current_user is None:
                    raise HTTPException(status_code=401, detail="authentication required")
                if current_user.username == SERVICE_USERNAME:
                    raise RuntimeError("service account cannot manage locale preference")
                current_user.preferred_locale = _normalize_supported_locale(payload.preferred_locale)
                current_user.updated_at = datetime.now(tz=UTC)
                session.flush()
                result = {"preferred_locale": _normalize_supported_locale(current_user.preferred_locale)}
            return _response(True, result=result, warnings=[], error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/auth/keys")
    def auth_list_keys(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=context.config
                )
                if current_user.username == SERVICE_USERNAME:
                    raise RuntimeError("service account cannot manage API keys")
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=context.config
                )
                if current_user.username == SERVICE_USERNAME:
                    raise RuntimeError("service account cannot manage API keys")
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=context.config
                )
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=context.config
                )
                _require_admin(current_user)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=context.config
                )
                _require_admin(current_user)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=context.config
                )
                _require_admin(current_user)
                user = session.get(User, user_id)
                if user is None or user.username == SERVICE_USERNAME:
                    raise RuntimeError("user not found")

                if payload.display_name is not None:
                    user.display_name = payload.display_name.strip() or None
                if payload.password is not None:
                    set_user_password(session, user=user, password=payload.password)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            with session_scope(context.sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=context.config
                )
                _require_admin(current_user)
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

    @app.post("/api/v1/system/backup")
    def run_system_backup(
        request: Request,
        payload: SystemBackupRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(context.sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                _require_admin(current_user)

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
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/documents/upload")
    async def upload_document(
        request: Request,
        file: UploadFormFile,
        db: str | None = Form(default=None),
        config: str | None = Form(default=None),
        source: str | None = Form(default=None),
        metadata_json: str | None = Form(default=None),
        legacy_api_key: str | None = Form(default=None, alias="api_key"),
    ) -> Any:
        try:
            _reject_legacy_form_api_key(legacy_api_key)
            context = _resolve_request_context(request, db=db, config_path=config)
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
                visibility = VisibilityContext(
                    user_id=current_user.user_id,
                    is_service=(current_user.username == SERVICE_USERNAME),
                    scope="personal",
                )
                validated_source = _validate_upload_source(session, source)
                if (
                    validated_source is not None
                    and session.get(Source, validated_source) is not None
                    and not _source_is_visible(
                        session=session, source_id=validated_source, visibility=visibility
                    )
                ):
                    raise RuntimeError("invalid source; register source before upload")
                document = Document(
                    transaction_id=None,
                    source_id=validated_source,
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
    def process_document(
        request: Request,
        document_id: str,
        scope: str = Form(default="personal"),
        db: str | None = Form(default=None),
        config: str | None = Form(default=None),
        caller_token: str | None = Form(default=None),
        legacy_api_key: str | None = Form(default=None, alias="api_key"),
    ) -> Any:
        try:
            _reject_legacy_form_api_key(legacy_api_key)
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = VisibilityContext(
                    user_id=current_user.user_id,
                    is_service=(current_user.username == SERVICE_USERNAME),
                    scope="personal",
                )
                document = session.get(Document, document_id)
                if document is None:
                    raise RuntimeError("document not found")
                if not _document_is_visible(
                    session=session, document=document, visibility=visibility
                ):
                    raise RuntimeError("document not found")
            jobs = JobService(session_factory=sessions, config=app_config)
            job, reused = jobs.create_ocr_job(
                document_id=document_id,
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
        db: str | None = None,
        config: str | None = None,
        job_id: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
        scope: str = "personal",
        limit: int = 50,
        offset: int = 0,
        status: str = "needs_review",
        threshold: float | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
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
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
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
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
        scope: str = "personal",
        query: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        source_id: str | None = None,
        group_by: str | None = None,
    ) -> Any:
        """Aggregate receipt line items: returns total spend, count, and optional breakdown.
        group_by can be 'source_id', 'month', 'year', or 'name'.
        """
        with open("/tmp/aggregate_items.log", "a") as _dbg:
            _dbg.write(f"aggregate_items called: query={query!r} from_date={from_date!r} to_date={to_date!r} source_id={source_id!r} group_by={group_by!r}\n")
        try:
            from lidltool.analytics.scope import visible_transaction_ids_subquery
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                visible_ids = visible_transaction_ids_subquery(visibility)

                base_filter = [Transaction.id.in_(visible_ids)]
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

                if group_by == "source_id":
                    group_col = Transaction.source_id
                elif group_by == "month":
                    group_col = func.strftime("%Y-%m", Transaction.purchased_at)
                elif group_by == "year":
                    group_col = func.strftime("%Y", Transaction.purchased_at)
                elif group_by == "name":
                    group_col = TransactionItem.name
                else:
                    group_col = None

                if group_col is not None:
                    stmt = (
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
                    )
                    rows = session.execute(stmt).all()
                    result = {
                        "groups": [
                            {
                                "group": r.group,
                                "total_cents": r.total_cents,
                                "item_count": r.item_count,
                                "total_qty": float(r.total_qty) if r.total_qty is not None else None,
                            }
                            for r in rows
                        ],
                        "grand_total_cents": sum(r.total_cents or 0 for r in rows),
                        "grand_item_count": sum(r.item_count or 0 for r in rows),
                        "grand_total_qty": sum(float(r.total_qty or 0) for r in rows),
                    }
                else:
                    stmt = (
                        select(
                            func.sum(TransactionItem.line_total_cents).label("total_cents"),
                            func.count(TransactionItem.id).label("item_count"),
                            func.sum(TransactionItem.qty).label("total_qty"),
                        )
                        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
                        .where(*base_filter)
                    )
                    row = session.execute(stmt).one()
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
                current_user_is_service = current_user.username == SERVICE_USERNAME
                visibility = VisibilityContext(
                    user_id=current_user_id,
                    is_service=current_user_is_service,
                    scope="personal",
                )
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
                currency=payload.currency.strip().upper(),
                discount_total_cents=payload.discount_total_cents,
                family_share_mode=payload.family_share_mode,
                confidence=payload.confidence,
                items=_manual_item_payload(payload.items),
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Response:
        context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
                personal_visibility = VisibilityContext(
                    user_id=current_user.user_id,
                    is_service=(current_user.username == SERVICE_USERNAME),
                    scope="personal",
                )
                details = transaction_detail(
                    session, transaction_id=transaction_id, visibility=personal_visibility
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            safe_limit = max(1, min(limit, 200))
            safe_offset = max(offset, 0)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                where_conditions = [ChatThread.user_id == current_user.user_id]
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                thread = _load_owned_chat_thread(session=session, user=current_user, thread_id=thread_id)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                thread = _load_owned_chat_thread(session=session, user=current_user, thread_id=thread_id)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                thread = _load_owned_chat_thread(session=session, user=current_user, thread_id=thread_id)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            safe_limit = max(1, min(limit, 500))
            safe_offset = max(offset, 0)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                _load_owned_chat_thread(session=session, user=current_user, thread_id=thread_id)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
                thread = session.get(ChatThread, thread_id)
                if thread is None:
                    thread = ChatThread(
                        thread_id=thread_id,
                        user_id=current_user.user_id,
                        title=_default_chat_title_for_message(content),
                        stream_status="idle",
                    )
                    session.add(thread)
                    session.flush()
                if not _owns_user_resource(current_user, resource_user_id=thread.user_id):
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
                    if not _owns_user_resource(current_user, resource_user_id=thread.user_id):
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
                    db=context.db_override,
                    config_path=str(context.config_path),
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            _apply_auth_guard(app_config, request=request)

            base_url = (app_config.ai_base_url or "").strip()
            if not base_url:
                raise RuntimeError("AI provider base_url is not configured")
            api_key = _resolve_ai_bearer_token(app_config, context.config_path)
            if not api_key:
                raise RuntimeError("AI provider credentials are not configured")
            model_id = (
                payload.model_id.strip()
                if isinstance(payload.model_id, str) and payload.model_id.strip()
                else (app_config.ai_model or "gpt-5.2-codex")
            )

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                thread = _load_owned_chat_thread(session=session, user=current_user, thread_id=thread_id)
                if thread.stream_status == "streaming":
                    raise HTTPException(status_code=409, detail="thread is already generating")
                stored_messages = session.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.thread_id == thread_id)
                    .order_by(ChatMessage.created_at.asc(), ChatMessage.message_id.asc())
                ).all()
                if not stored_messages:
                    raise RuntimeError("at least one message is required")
                openai_messages: list[dict[str, str]] = []
                for stored_message in stored_messages:
                    if stored_message.role not in {"system", "user", "assistant"}:
                        continue
                    text = _chat_text_from_content(stored_message.content_json)
                    if not text:
                        continue
                    openai_messages.append({"role": stored_message.role, "content": text})
                if not openai_messages:
                    raise RuntimeError("at least one text message is required")
                thread.stream_status = "streaming"
                thread.updated_at = datetime.now(tz=UTC)

            try:
                from openai import AsyncOpenAI
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"openai SDK is unavailable: {exc}") from exc

            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            start_time = time.perf_counter()

            async def event_stream() -> Any:
                text_chunks: list[str] = []
                input_tokens = 0
                output_tokens = 0
                total_tokens = 0
                finish_reason = "stop"
                stream_error: Exception | None = None

                yield _sse_data({"type": "start"})
                yield _sse_data({"type": "text_start", "contentIndex": 0})
                try:
                    stream = await client.chat.completions.create(
                        model=model_id,
                        messages=openai_messages,
                        temperature=0.7,
                        max_tokens=4096,
                        stream=True,
                        stream_options={"include_usage": True},
                    )
                    async for chunk in stream:
                        chunk_usage = getattr(chunk, "usage", None)
                        if chunk_usage is not None:
                            input_tokens = int(getattr(chunk_usage, "prompt_tokens", 0) or 0)
                            output_tokens = int(getattr(chunk_usage, "completion_tokens", 0) or 0)
                            total_tokens = int(getattr(chunk_usage, "total_tokens", 0) or 0)

                        choices = getattr(chunk, "choices", None) or []
                        if not choices:
                            continue
                        choice = choices[0]
                        if choice.finish_reason:
                            finish_reason = str(choice.finish_reason)
                        delta = choice.delta
                        content_delta = str(getattr(delta, "content", "") or "")
                        if content_delta:
                            text_chunks.append(content_delta)
                            yield _sse_data(
                                {
                                    "type": "text_delta",
                                    "contentIndex": 0,
                                    "delta": content_delta,
                                }
                            )
                except Exception as exc:  # noqa: BLE001
                    stream_error = exc
                finally:
                    close_method = getattr(client, "close", None)
                    if callable(close_method):
                        maybe_awaitable = close_method()
                        if asyncio.iscoroutine(maybe_awaitable):
                            with suppress(Exception):
                                await maybe_awaitable

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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)

            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                thread = _load_owned_chat_thread(session=session, user=current_user, thread_id=thread_id)

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
        db: str | None = None,
        config: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            service = AutomationService(session_factory=sessions)
            result = service.list_rules(limit=limit, offset=offset)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/automations")
    def create_automation(
        request: Request,
        payload: AutomationRuleCreateRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            service = AutomationService(session_factory=sessions)
            result = service.create_rule(
                name=payload.name,
                rule_type=payload.rule_type,
                enabled=payload.enabled,
                trigger_config=payload.trigger_config,
                action_config=payload.action_config,
                actor_id=payload.actor_id,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/automations/executions")
    def list_automation_executions(
        request: Request,
        db: str | None = None,
        config: str | None = None,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        rule_type: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            service = AutomationService(session_factory=sessions)
            result = service.list_executions(
                limit=limit,
                offset=offset,
                status=status,
                rule_type=rule_type,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/automations/{rule_id}")
    def get_automation(
        request: Request,
        rule_id: str,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            service = AutomationService(session_factory=sessions)
            result = service.get_rule(rule_id=rule_id)
            if result is None:
                raise RuntimeError("automation rule not found")
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/automations/{rule_id}")
    def patch_automation(
        request: Request,
        rule_id: str,
        payload: AutomationRuleUpdateRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            service = AutomationService(session_factory=sessions)
            result = service.update_rule(
                rule_id=rule_id,
                payload=payload.model_dump(exclude_none=True),
                actor_id=payload.actor_id,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/automations/{rule_id}")
    def delete_automation(
        request: Request,
        rule_id: str,
        actor_id: str | None = None,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            service = AutomationService(session_factory=sessions)
            result = service.delete_rule(rule_id=rule_id, actor_id=actor_id)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/automations/{rule_id}/run")
    def run_automation(
        request: Request,
        rule_id: str,
        payload: AutomationRunRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            service = AutomationService(session_factory=sessions)
            result = service.run_rule(rule_id=rule_id, actor_id=payload.actor_id)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills")
    def list_recurring_bills(
        request: Request,
        db: str | None = None,
        config: str | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.list_bills(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.create_bill(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_overview(user_id=user_id)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills/analytics/calendar")
    def get_recurring_calendar(
        request: Request,
        year: int | None = None,
        month: int | None = None,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            now = datetime.now(tz=UTC)
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_calendar(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_forecast(user_id=user_id, months=months)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/recurring-bills/analytics/gaps")
    def get_recurring_gaps(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_gaps(user_id=user_id)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/recurring-bills/occurrences/{occ_id}/status")
    def update_recurring_occurrence_status(
        request: Request,
        occ_id: str,
        payload: RecurringOccurrenceStatusUpdateRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.update_occurrence_status(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.skip_occurrence(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, is_service_user = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.reconcile_occurrence(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.list_occurrences(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.generate_occurrences(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, is_service_user = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.run_matching(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.get_bill(user_id=user_id, bill_id=bill_id)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.update_bill(
                user_id=user_id,
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            user_id, _ = _resolve_request_user_identity(
                request=request,
                app_config=app_config,
                sessions=sessions,
            )
            service = RecurringBillsService(session_factory=sessions)
            result = service.delete_bill(user_id=user_id, bill_id=bill_id)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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

    @app.get("/api/v1/dashboard/trends")
    def get_dashboard_trends(
        request: Request,
        year: int,
        months_back: int = 6,
        end_month: int = 12,
        source_ids: str | None = None,
        scope: str = "personal",
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = VisibilityContext(
                    user_id=current_user.user_id,
                    is_service=(current_user.username == SERVICE_USERNAME),
                    scope="personal",
                )
                result = list_sources(session, config=app_config, visibility=visibility)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/connectors")
    def get_connectors(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                _require_admin(current_user)
                auth_service = _connector_auth_service(app, config=app_config)
                result = connector_discovery_payload(
                    app,
                    session,
                    auth_service=auth_service,
                    config=app_config,
                    viewer_is_admin=current_user.is_admin,
                )
            return _response(True, result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/reload")
    def reload_connectors(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        return rescan_connectors(request=request, db=db, config=config)

    @app.post("/api/v1/connectors/{source_id}/install")
    def post_connector_install(
        request: Request,
        source_id: str,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                _require_admin(current_user)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                _require_admin(current_user)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                _require_admin(current_user)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                _require_admin(current_user)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                _require_admin(current_user)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                _require_admin(current_user)
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

    @app.post("/api/v1/connectors/cascade/start")
    def start_connector_cascade(
        request: Request,
        payload: ConnectorCascadeStartRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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

            cascade_sessions = cast(
                dict[str, ConnectorCascadeSession], app.state.connector_cascade_sessions
            )
            cascade_sessions_lock = cast(
                threading.Lock, app.state.connector_cascade_sessions_lock
            )
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

                bootstrap_sessions = cast(
                    dict[str, ConnectorBootstrapSession], app.state.connector_bootstrap_sessions
                )
                sync_sessions = cast(
                    dict[str, ConnectorBootstrapSession], app.state.connector_sync_sessions
                )
                if _connector_any_running(bootstrap_sessions) or _connector_any_running(sync_sessions):
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id

            cascade_sessions = cast(
                dict[str, ConnectorCascadeSession], app.state.connector_cascade_sessions
            )
            cascade_sessions_lock = cast(
                threading.Lock, app.state.connector_cascade_sessions_lock
            )
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

                bootstrap_sessions = cast(
                    dict[str, ConnectorBootstrapSession], app.state.connector_bootstrap_sessions
                )
                sync_sessions = cast(
                    dict[str, ConnectorBootstrapSession], app.state.connector_sync_sessions
                )
                if _connector_any_running(bootstrap_sessions) or _connector_any_running(sync_sessions):
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id

            cascade_sessions = cast(
                dict[str, ConnectorCascadeSession], app.state.connector_cascade_sessions
            )
            cascade = cascade_sessions.get(current_user_id)
            if cascade is None:
                result = _idle_connector_cascade_status()
            else:
                result = _serialize_connector_cascade(cascade, request=request)
                selected_source_ids = cast(list[str], result["source_ids"])
                if any(source_id != "lidl_plus_de" for source_id in selected_source_ids):
                    warnings.append(
                        "cascade includes preview connectors that are not fully live-validated yet"
                    )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/cascade/cancel")
    def cancel_connector_cascade(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                current_user_id = current_user.user_id

            cascade_sessions = cast(
                dict[str, ConnectorCascadeSession], app.state.connector_cascade_sessions
            )
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

            bootstrap_sessions = cast(
                dict[str, ConnectorBootstrapSession], app.state.connector_bootstrap_sessions
            )
            sync_sessions = cast(
                dict[str, ConnectorBootstrapSession], app.state.connector_sync_sessions
            )
            if not _connector_any_running(bootstrap_sessions) and not _connector_any_running(sync_sessions):
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)

            cascade_sessions = cast(
                dict[str, ConnectorCascadeSession], app.state.connector_cascade_sessions
            )
            if any(_connector_cascade_is_active(cascade) for cascade in cascade_sessions.values()):
                raise RuntimeError(
                    "connector cascade is already running; cancel or wait for completion before manual bootstrap"
                )

            service = _connector_auth_service(app, config=app_config)
            manifest = service.get_auth_status(source_id=source_id, validate_session=False).manifest

            bootstrap_sessions = cast(
                dict[str, ConnectorBootstrapSession], app.state.connector_bootstrap_sessions
            )

            for existing_source, existing in bootstrap_sessions.items():
                if existing_source == source_id:
                    continue
                if _connector_bootstrap_is_running(existing):
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
                if source_id != "lidl_plus_de":
                    warnings.append(
                        _warning(
                            "preview connector bootstrap started; this connector is not live-validated yet",
                            code="connector_preview_bootstrap_started",
                        )
                    )
                return _response(True, result=result, warnings=warnings, error=None)

            remote_login_url: str | None = None
            env: dict[str, str] | None = None
            try:
                _ensure_vnc_runtime(app)
                remote_login_url = _novnc_login_url(request)
                runtime = cast(VncRuntime | None, app.state.vnc_runtime)
                if runtime is not None:
                    env = {"DISPLAY": runtime.display}
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
            if bootstrap is None:
                raise RuntimeError(f"connector bootstrap session missing after start: {source_id}")

            result = {
                "source_id": source_id,
                "reused": started.status == "reused",
                "bootstrap": _serialize_connector_bootstrap(bootstrap),
                "remote_login_url": remote_login_url,
            }
            if manifest.source_id != "lidl_plus_de":
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)

            bootstrap_sessions = cast(
                dict[str, ConnectorBootstrapSession], app.state.connector_bootstrap_sessions
            )
            bootstrap = bootstrap_sessions.get(source_id)
            remote_login_url = _novnc_login_url(request)
            if bootstrap is None:
                service = _connector_auth_service(app, config=app_config)
                snapshot = service.get_bootstrap_status(source_id=source_id)
                result: dict[str, Any] = {
                    "source_id": snapshot.source_id,
                    "status": snapshot.state,
                    "command": None,
                    "pid": None,
                    "started_at": None,
                    "finished_at": None,
                    "return_code": None,
                    "output_tail": [],
                    "can_cancel": False,
                    "remote_login_url": remote_login_url,
                }
            else:
                result = _serialize_connector_bootstrap(bootstrap)
                result["remote_login_url"] = remote_login_url
            if source_id != "lidl_plus_de":
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)

            bootstrap_sessions = cast(
                dict[str, ConnectorBootstrapSession], app.state.connector_bootstrap_sessions
            )
            bootstrap = bootstrap_sessions.get(source_id)
            if bootstrap is None:
                result = {"source_id": source_id, "canceled": False, "bootstrap": None}
            else:
                service = _connector_auth_service(app, config=app_config)
                service.cancel_bootstrap(source_id=source_id)
                result = {
                    "source_id": source_id,
                    "canceled": True,
                    "bootstrap": _serialize_connector_bootstrap(bootstrap),
                }
            if not _connector_any_running(bootstrap_sessions):
                _stop_vnc_runtime(app)
            if source_id != "lidl_plus_de":
                warnings.append(
                    "preview connector cancellation only; this connector is not live-validated yet"
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/connectors/{source_id}/sync")
    def start_connector_sync(
        request: Request,
        source_id: str,
        full: bool = False,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)

            cascade_sessions = cast(
                dict[str, ConnectorCascadeSession], app.state.connector_cascade_sessions
            )
            if any(_connector_cascade_is_active(cascade) for cascade in cascade_sessions.values()):
                raise RuntimeError(
                    "connector cascade is already running; cancel or wait for completion before manual sync"
                )

            command = _connector_command(
                app_config,
                source_id=source_id,
                operation="sync",
                full=full,
            )
            if command is None:
                raise RuntimeError(f"sync not supported for source: {source_id}")

            sync_sessions = cast(
                dict[str, ConnectorBootstrapSession], app.state.connector_sync_sessions
            )
            existing = sync_sessions.get(source_id)
            if existing is not None and _connector_bootstrap_is_running(existing):
                return _response(
                    True,
                    result={"source_id": source_id, "reused": True, "sync": _serialize_connector_bootstrap(existing)},
                    warnings=warnings,
                    error=None,
                )

            sync_session = _start_connector_command_session(
                app,
                source_id=source_id,
                command=command,
                config=app_config,
                sessions_attr="connector_sync_sessions",
                thread_name=f"connector-sync-{source_id}",
            )

            if source_id != "lidl_plus_de":
                warnings.append(
                    _warning(
                        "preview connector sync; this connector is not live-validated yet",
                        code="connector_preview_sync_started",
                    )
                )
            return _response(
                True,
                result={"source_id": source_id, "reused": False, "sync": _serialize_connector_bootstrap(sync_session)},
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/sources/{source_id}/sync")
    def start_source_sync(
        request: Request,
        source_id: str,
        full: bool = False,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        return start_connector_sync(
            request=request,
            source_id=source_id,
            full=full,
            db=db,
            config=config,
        )

    @app.get("/api/v1/connectors/{source_id}/sync/status")
    def get_connector_sync_status(
        request: Request,
        source_id: str,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                _resolve_request_user(request=request, session=session, config=app_config)

            sync_sessions = cast(
                dict[str, ConnectorBootstrapSession], app.state.connector_sync_sessions
            )
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
                result = _serialize_connector_bootstrap(sync)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/sources/{source_id}/sync/status")
    def get_source_sync_status(
        request: Request,
        source_id: str,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        return get_connector_sync_status(
            request=request,
            source_id=source_id,
            db=db,
            config=config,
        )

    @app.patch("/api/v1/sources/{source_id}/sharing")
    def patch_source_sharing(
        request: Request,
        source_id: str,
        payload: SourceSharingRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                source = session.get(Source, source_id)
                if source is None or not _owns_user_resource(
                    current_user, resource_user_id=source.user_id
                ):
                    raise RuntimeError("source not found")
                source.family_share_mode = payload.family_share_mode
                source.updated_at = datetime.now(tz=UTC)
                session.flush()
                result = {
                    "source_id": source.id,
                    "user_id": source.user_id,
                    "family_share_mode": source.family_share_mode,
                    "updated_at": source.updated_at.isoformat(),
                }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/transactions/{transaction_id}/sharing")
    def patch_transaction_sharing(
        request: Request,
        transaction_id: str,
        payload: TransactionSharingRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                transaction = session.get(Transaction, transaction_id)
                if transaction is None or not _owns_user_resource(
                    current_user, resource_user_id=transaction.user_id
                ):
                    raise RuntimeError("transaction not found")
                transaction.family_share_mode = payload.family_share_mode
                transaction.updated_at = datetime.now(tz=UTC)
                session.flush()
                result = {
                    "transaction_id": transaction.id,
                    "user_id": transaction.user_id,
                    "source_id": transaction.source_id,
                    "family_share_mode": transaction.family_share_mode,
                    "source_family_share_mode": (
                        transaction.source.family_share_mode
                        if transaction.source is not None
                        else None
                    ),
                    "updated_at": transaction.updated_at.isoformat(),
                }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.patch("/api/v1/transactions/{transaction_id}/items/{item_id}/sharing")
    def patch_transaction_item_sharing(
        request: Request,
        transaction_id: str,
        item_id: str,
        payload: TransactionItemSharingRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                transaction = session.get(Transaction, transaction_id)
                if transaction is None or not _owns_user_resource(
                    current_user, resource_user_id=transaction.user_id
                ):
                    raise RuntimeError("transaction not found")
                item = session.get(TransactionItem, item_id)
                if item is None or item.transaction_id != transaction.id:
                    raise RuntimeError("transaction item not found")
                item.family_shared = payload.family_shared
                session.flush()
                result = {
                    "transaction_id": transaction.id,
                    "item_id": item.id,
                    "family_shared": item.family_shared,
                }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/query/run")
    def post_query_run(
        request: Request,
        payload: QueryRunRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        scope: str = "personal",
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
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
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)

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
                warnings=warnings,
                error=error_output if exit_code != 0 else None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/analytics/basket-compare")
    def post_basket_compare(
        request: Request,
        payload: BasketCompareRequest,
        scope: str = "personal",
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = list_budget_rules(session)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/analytics/budget-rules")
    def post_budget_rule(
        request: Request,
        payload: BudgetRuleCreateRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = create_budget_rule(
                    session,
                    scope_type=payload.scope_type,
                    scope_value=payload.scope_value,
                    period=payload.period,
                    amount_cents=payload.amount_cents,
                    currency=payload.currency,
                    active=payload.active,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/budget")
    def get_budget_utilization(
        request: Request,
        year: int | None = None,
        month: int | None = None,
        scope: str = "personal",
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = _visibility_for_scope(current_user, scope)
                result = budget_utilization(session, year=year, month=month, visibility=visibility)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/analytics/patterns")
    def get_patterns_summary(
        request: Request,
        from_date: str | None = None,
        to_date: str | None = None,
        scope: str = "personal",
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = list_saved_queries(session)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/query/saved")
    def post_saved_query(
        request: Request,
        payload: SavedQueryCreateRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = create_saved_query(
                    session,
                    name=payload.name,
                    description=payload.description,
                    query_json=payload.query_json,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/query/saved/{query_id}")
    def get_saved_query_by_id(
        request: Request,
        query_id: str,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = get_saved_query(session, query_id=query_id)
            if result is None:
                raise RuntimeError("saved query not found")
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.delete("/api/v1/query/saved/{query_id}")
    def delete_saved_query_by_id(
        request: Request,
        query_id: str,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                deleted = delete_saved_query(session, query_id=query_id)
            if not deleted:
                raise RuntimeError("saved query not found")
            return _response(
                True, result={"query_id": query_id, "deleted": True}, warnings=warnings, error=None
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/settings/ai")
    def get_ai_settings(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)
            oauth_connected = bool(
                app_config.ai_oauth_provider and get_ai_oauth_access_token(app_config)
            )
            result = {
                "enabled": bool(app_config.ai_enabled),
                "base_url": app_config.ai_base_url,
                "model": app_config.ai_model,
                "api_key_set": bool(app_config.ai_api_key_encrypted),
                "oauth_provider": app_config.ai_oauth_provider,
                "oauth_connected": oauth_connected,
            }
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/settings/ai")
    def post_ai_settings(
        request: Request,
        payload: AISettingsUpdateRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)

            base_url = (
                payload.base_url.strip()
                if isinstance(payload.base_url, str)
                else (app_config.ai_base_url or "").strip()
            )
            model = payload.model.strip()
            candidate_api_key = (
                payload.api_key.strip()
                if isinstance(payload.api_key, str) and payload.api_key.strip()
                else get_ai_api_key(app_config)
            )

            if not base_url:
                return _response(
                    True,
                    result={"ok": False, "error": "base_url is required"},
                    warnings=warnings,
                    error=None,
                )
            if not model:
                return _response(
                    True,
                    result={"ok": False, "error": "model is required"},
                    warnings=warnings,
                    error=None,
                )
            if not candidate_api_key:
                return _response(
                    True,
                    result={"ok": False, "error": "api_key is required"},
                    warnings=warnings,
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
                    warnings=warnings,
                    error=None,
                )

            app_config.ai_base_url = base_url
            app_config.ai_model = model
            app_config.ai_enabled = True
            if isinstance(payload.api_key, str) and payload.api_key.strip():
                set_ai_api_key(app_config, payload.api_key.strip())

            persist_ai_settings(context.config_path, app_config)
            return _response(
                True,
                result={"ok": True, "error": None},
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/settings/ai/disconnect")
    def post_ai_disconnect(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)

            app_config.ai_enabled = False
            app_config.ai_base_url = None
            app_config.ai_model = "grok-3-mini"
            set_ai_api_key(app_config, None)
            app_config.ai_oauth_provider = None
            set_ai_oauth_access_token(app_config, None)
            set_ai_oauth_refresh_token(app_config, None)
            app_config.ai_oauth_expires_at = None
            persist_ai_settings(context.config_path, app_config)

            return _response(True, result={"ok": True}, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/settings/ai/oauth/start")
    def post_ai_oauth_start(
        request: Request,
        payload: AIOAuthStartRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)

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
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/settings/ai/oauth/status")
    def get_ai_oauth_status(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)
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
                    warnings=warnings,
                    error=None,
                )
            if status == "error":
                return _response(
                    True,
                    result={"status": "error", "error": str(error_message) if error_message else None},
                    warnings=warnings,
                    error=None,
                )
            return _response(
                True,
                result={"status": "pending", "error": None},
                warnings=warnings,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/settings/ai/agent-config")
    def get_ai_agent_config(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request,
                    session=session,
                    config=app_config,
                    required=True,
                )
                auth_token = issue_session_token(user=current_user, config=app_config)
            local_model = _configured_local_chat_model(app_config)
            preferred_model = _preferred_chat_model(app_config)
            result = {
                "proxy_url": "",
                "auth_token": auth_token,
                "model": preferred_model,
                "default_model": local_model,
                "local_model": local_model,
                "preferred_model": preferred_model,
                "oauth_provider": app_config.ai_oauth_provider,
                "oauth_connected": _chatgpt_oauth_connected(app_config),
                "available_models": _available_chat_models(app_config),
            }
            return _response(True, result=result, warnings=warnings, error=None)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions

            with session_scope(sessions) as session:
                _authorize_stream_proxy_request(request=request, session=session, config=app_config)

            selected_model_id = (payload.model.id or "").strip() or _preferred_chat_model(app_config)

            # When the selected model is the ChatGPT option, route to the Codex Responses API.
            if _should_route_stream_via_chatgpt(app_config, selected_model_id):
                api_key = _resolve_ai_bearer_token(
                    app_config, context.config_path, prefer_oauth=True
                )
                if not api_key:
                    raise RuntimeError("AI provider credentials are not configured")
                return await _chatgpt_codex_stream(payload=payload, bearer_token=api_key)

            base_url = (app_config.ai_base_url or "").strip()
            if not base_url:
                raise RuntimeError("AI provider base_url is not configured")
            api_key = _resolve_ai_bearer_token(
                app_config, context.config_path, prefer_oauth=False
            )
            if not api_key:
                raise RuntimeError("AI provider credentials are not configured")

            openai_messages = _to_openai_messages(
                system_prompt=payload.context.systemPrompt,
                messages=payload.context.messages,
            )
            openai_tools = _to_openai_tools(payload.context.tools)
            if not openai_messages:
                raise RuntimeError("at least one message is required")

            try:
                from openai import AsyncOpenAI
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"openai SDK is unavailable: {exc}") from exc

            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            stream = await client.chat.completions.create(
                model=payload.model.id,
                messages=openai_messages,
                temperature=payload.options.temperature,
                max_tokens=payload.options.maxTokens,
                tools=openai_tools or None,
                tool_choice="auto" if openai_tools else None,
                stream=True,
                stream_options={"include_usage": True},
            )

            async def event_stream() -> Any:
                input_tokens = 0
                output_tokens = 0
                total_tokens = 0
                finish_reason = "stop"
                active_tool_indexes: set[int] = set()

                yield _sse_data({"type": "start"})
                yield _sse_data({"type": "text_start", "contentIndex": 0})
                try:
                    async for chunk in stream:
                        chunk_usage = getattr(chunk, "usage", None)
                        if chunk_usage is not None:
                            input_tokens = int(getattr(chunk_usage, "prompt_tokens", 0) or 0)
                            output_tokens = int(getattr(chunk_usage, "completion_tokens", 0) or 0)
                            total_tokens = int(getattr(chunk_usage, "total_tokens", 0) or 0)

                        choices = getattr(chunk, "choices", None) or []
                        if not choices:
                            continue
                        choice = choices[0]
                        if choice.finish_reason:
                            finish_reason = str(choice.finish_reason)
                        delta = choice.delta
                        if getattr(delta, "content", None):
                            yield _sse_data(
                                {
                                    "type": "text_delta",
                                    "contentIndex": 0,
                                    "delta": str(delta.content),
                                }
                            )

                        tool_calls = getattr(delta, "tool_calls", None) or []
                        for tool_call in tool_calls:
                            index = int(getattr(tool_call, "index", 0) or 0)
                            content_index = 1 + index
                            tool_call_id = str(getattr(tool_call, "id", "") or f"toolcall_{index}")
                            function_obj = getattr(tool_call, "function", None)
                            function_name = (
                                str(getattr(function_obj, "name", "") or "") if function_obj else ""
                            )
                            arguments_delta = (
                                str(getattr(function_obj, "arguments", "") or "")
                                if function_obj
                                else ""
                            )

                            if index not in active_tool_indexes:
                                active_tool_indexes.add(index)
                                yield _sse_data(
                                    {
                                        "type": "toolcall_start",
                                        "contentIndex": content_index,
                                        "id": tool_call_id,
                                        "toolName": function_name,
                                    }
                                )

                            if arguments_delta:
                                yield _sse_data(
                                    {
                                        "type": "toolcall_delta",
                                        "contentIndex": content_index,
                                        "delta": arguments_delta,
                                    }
                                )

                        if choice.finish_reason == "tool_calls":
                            for index in sorted(active_tool_indexes):
                                yield _sse_data(
                                    {
                                        "type": "toolcall_end",
                                        "contentIndex": 1 + index,
                                    }
                                )
                            active_tool_indexes.clear()
                finally:
                    for index in sorted(active_tool_indexes):
                        yield _sse_data(
                            {
                                "type": "toolcall_end",
                                "contentIndex": 1 + index,
                            }
                        )
                    yield _sse_data({"type": "text_end", "contentIndex": 0})
                    normalized_total = total_tokens or (input_tokens + output_tokens)
                    normalized_reason = (
                        "toolUse"
                        if finish_reason == "tool_calls"
                        else "length"
                        if finish_reason == "length"
                        else "stop"
                    )
                    yield _sse_data(
                        {
                            "type": "done",
                            "reason": normalized_reason,
                            "usage": {
                                "input": input_tokens,
                                "output": output_tokens,
                                "cacheRead": 0,
                                "cacheWrite": 0,
                                "totalTokens": normalized_total,
                                "cost": None,
                            },
                        }
                    )
                    close_method = getattr(client, "close", None)
                    if callable(close_method):
                        maybe_awaitable = close_method()
                        if asyncio.iscoroutine(maybe_awaitable):
                            with suppress(Exception):
                                await maybe_awaitable

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
        limit: int = 50,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = search_products(
                    session,
                    search=search,
                    source_kind=source_kind,
                    limit=limit,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/products")
    def post_product(
        request: Request,
        payload: ProductCreateRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = create_product(
                    session,
                    canonical_name=payload.canonical_name,
                    brand=payload.brand,
                    default_unit=payload.default_unit,
                    gtin_ean=payload.gtin_ean,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/products/seed")
    def post_product_seed(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = seed_products_from_items(session)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/products/cluster")
    def post_product_cluster(
        request: Request,
        payload: ProductClusterRequest | None = None,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            result = cluster_products_with_llm(
                sessions=sessions,
                config=app_config,
                force=payload.force if payload is not None else False,
            )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/products/cluster/{job_id}")
    def get_product_cluster_status(
        request: Request,
        job_id: str,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            warnings = _apply_auth_guard(app_config, request=request)
            result = get_cluster_job_progress(job_id)
            if result is None:
                raise RuntimeError("cluster job not found")
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/products/{product_id}")
    def get_product(
        request: Request,
        product_id: str,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = get_product_detail(session, product_id=product_id)
            if result is None:
                raise RuntimeError("product not found")
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/products/{product_id}/merge")
    def post_product_merge(
        request: Request,
        product_id: str,
        payload: ProductMergeRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = merge_products(
                    session,
                    target_product_id=product_id,
                    source_product_ids=payload.source_product_ids,
                )
            return _response(True, result=result, warnings=warnings, error=None)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = manual_product_match(
                    session,
                    product_id=payload.product_id,
                    raw_name=payload.raw_name,
                    source_kind=payload.source_kind,
                    raw_sku=payload.raw_sku,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/compare/groups")
    def get_compare_groups(
        request: Request,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = list_comparison_groups(session)
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.post("/api/v1/compare/groups")
    def post_compare_group(
        request: Request,
        payload: ComparisonGroupCreateRequest,
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = create_comparison_group(
                    session,
                    name=payload.name,
                    unit_standard=payload.unit_standard,
                    notes=payload.notes,
                )
            return _response(True, result=result, warnings=warnings, error=None)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = add_comparison_group_member(
                    session,
                    group_id=group_id,
                    product_id=payload.product_id,
                    weight=payload.weight,
                )
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/quality/unmatched-items")
    def get_quality_unmatched_items(
        request: Request,
        limit: int = 200,
        scope: str = "personal",
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
        window_hours: int = 24,
        sync_p95_target_ms: int = 2500,
        analytics_p95_target_ms: int = 2000,
        min_success_rate: float = 0.97,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                result = compute_endpoint_slo_summary(
                    session,
                    window_hours=window_hours,
                    sync_p95_target_ms=sync_p95_target_ms,
                    analytics_p95_target_ms=analytics_p95_target_ms,
                    min_success_rate=min_success_rate,
                ).as_dict()
            return _response(True, result=result, warnings=warnings, error=None)
        except Exception as exc:  # noqa: BLE001
            return _error_response(exc)

    @app.get("/api/v1/review-queue/{document_id}")
    def get_review_queue_detail(
        request: Request,
        document_id: str,
        scope: str = "personal",
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = VisibilityContext(
                    user_id=current_user.user_id,
                    is_service=(current_user.username == SERVICE_USERNAME),
                    scope="personal",
                )
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = VisibilityContext(
                    user_id=current_user.user_id,
                    is_service=(current_user.username == SERVICE_USERNAME),
                    scope="personal",
                )
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = VisibilityContext(
                    user_id=current_user.user_id,
                    is_service=(current_user.username == SERVICE_USERNAME),
                    scope="personal",
                )
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
        db: str | None = None,
        config: str | None = None,
    ) -> Any:
        try:
            context = _resolve_request_context(request, db=db, config_path=config)
            app_config = context.config
            sessions = context.sessions
            warnings = _apply_auth_guard(app_config, request=request)
            with session_scope(sessions) as session:
                current_user = _resolve_request_user(
                    request=request, session=session, config=app_config
                )
                visibility = VisibilityContext(
                    user_id=current_user.user_id,
                    is_service=(current_user.username == SERVICE_USERNAME),
                    scope="personal",
                )
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
        runtime = cast(VncRuntime | None, getattr(app.state, "vnc_runtime", None))
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

    return app


def main() -> None:
    uvicorn.run("lidltool.api.http_server:create_app", factory=True, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
