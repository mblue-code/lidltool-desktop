from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TypedDict, cast

from fastapi import FastAPI

from lidltool.automations.scheduler import AutomationScheduler
from lidltool.connectors.auth.auth_orchestration import (
    ConnectorAuthSessionRegistry,
    ConnectorBootstrapSession,
)


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


class AIOAuthState(TypedDict):
    status: Literal["pending", "connected", "error"]
    error: str | None
    provider: str | None
    updated_at: str


@dataclass(slots=True)
class QualityRecategorizeJobState:
    job_id: str
    status: str
    requested_by_user_id: str
    requested_at: datetime
    source_id: str | None
    only_fallback_other: bool
    include_suspect_model_items: bool
    max_transactions: int | None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    transaction_count: int = 0
    candidate_item_count: int = 0
    updated_transaction_count: int = 0
    updated_item_count: int = 0
    skipped_transaction_count: int = 0
    method_counts: dict[str, int] | None = None
    error: str | None = None


def initialize_http_api_state(app: FastAPI) -> None:
    app.state.started_at = datetime.now(tz=UTC)
    app.state.build = os.getenv("LIDLTOOL_BUILD", "dev")
    app.state.http_rate_limit_buckets = {}
    app.state.http_rate_limit_lock = threading.Lock()

    bootstrap_sessions: dict[str, ConnectorBootstrapSession] = {}
    app.state.connector_bootstrap_sessions = bootstrap_sessions
    app.state.connector_auth_sessions = ConnectorAuthSessionRegistry(bootstrap_sessions)
    app.state.connector_sync_sessions = {}
    app.state.connector_cascade_sessions = {}
    app.state.connector_cascade_sessions_lock = threading.Lock()
    app.state.quality_recategorize_jobs = {}
    app.state.quality_recategorize_jobs_lock = threading.Lock()

    app.state.vnc_runtime = None
    app.state.ai_oauth_lock = threading.Lock()
    app.state.ai_oauth_state = AIOAuthState(
        status="pending",
        error=None,
        provider=None,
        updated_at=datetime.now(tz=UTC).isoformat(),
    )


def get_started_at(app: FastAPI) -> datetime | None:
    started_at = getattr(app.state, "started_at", None)
    if isinstance(started_at, datetime):
        return started_at
    return None


def get_build(app: FastAPI) -> str:
    build = getattr(app.state, "build", os.getenv("LIDLTOOL_BUILD", "dev"))
    return str(build)


def get_http_rate_limit_buckets(app: FastAPI) -> dict[str, list[float]]:
    return cast(dict[str, list[float]], app.state.http_rate_limit_buckets)


def get_http_rate_limit_lock(app: FastAPI) -> threading.Lock:
    return cast(threading.Lock, app.state.http_rate_limit_lock)


def get_connector_auth_registry(app: FastAPI) -> ConnectorAuthSessionRegistry:
    return cast(ConnectorAuthSessionRegistry, app.state.connector_auth_sessions)


def get_connector_command_sessions(
    app: FastAPI,
    *,
    kind: Literal["bootstrap", "sync"],
) -> dict[str, ConnectorBootstrapSession]:
    attr_name = "connector_bootstrap_sessions" if kind == "bootstrap" else "connector_sync_sessions"
    return cast(dict[str, ConnectorBootstrapSession], getattr(app.state, attr_name))


def get_connector_cascade_sessions(app: FastAPI) -> dict[str, ConnectorCascadeSession]:
    return cast(dict[str, ConnectorCascadeSession], app.state.connector_cascade_sessions)


def get_connector_cascade_lock(app: FastAPI) -> threading.Lock:
    return cast(threading.Lock, app.state.connector_cascade_sessions_lock)


def get_vnc_runtime(app: FastAPI) -> VncRuntime | None:
    return cast(VncRuntime | None, getattr(app.state, "vnc_runtime", None))


def set_vnc_runtime(app: FastAPI, runtime: VncRuntime | None) -> None:
    app.state.vnc_runtime = runtime


def get_ai_oauth_lock(app: FastAPI) -> threading.Lock:
    return cast(threading.Lock, app.state.ai_oauth_lock)


def get_ai_oauth_state(app: FastAPI) -> AIOAuthState:
    return cast(AIOAuthState, app.state.ai_oauth_state)


def set_ai_oauth_state(app: FastAPI, state: AIOAuthState) -> None:
    app.state.ai_oauth_state = state


def get_quality_recategorize_jobs(app: FastAPI) -> dict[str, QualityRecategorizeJobState]:
    return cast(dict[str, QualityRecategorizeJobState], app.state.quality_recategorize_jobs)


def get_quality_recategorize_lock(app: FastAPI) -> threading.Lock:
    return cast(threading.Lock, app.state.quality_recategorize_jobs_lock)


def get_automation_scheduler(app: FastAPI) -> AutomationScheduler | None:
    scheduler = getattr(app.state, "automation_scheduler", None)
    if isinstance(scheduler, AutomationScheduler):
        return scheduler
    return None
