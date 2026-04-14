from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.amazon.client_playwright import AmazonClientError, AmazonPlaywrightClient
from lidltool.amazon.profiles import get_country_profile, is_amazon_source_id
from lidltool.amazon.importer import AmazonImportService
from lidltool.amazon.session import default_amazon_state_file
from lidltool.analytics.queries import export_receipts, month_stats
from lidltool.auth.users import (
    SERVICE_USERNAME,
    create_local_user,
    get_user_by_username,
    human_user_count,
    set_user_password,
)
from lidltool.config import (
    AppConfig,
    build_config,
    database_url,
    default_config_file,
    validate_config,
)
from lidltool.connectors.auth.auth_orchestration import ConnectorAuthOrchestrationService
from lidltool.connectors.runtime.errors import ConnectorRuntimeError
from lidltool.connectors.runtime.execution import ConnectorExecutionService
from lidltool.deployment_policy import evaluate_deployment_policy
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import Source, Transaction, User
from lidltool.ingest.sync import SyncProgress, SyncService
from lidltool.logging import configure_logging

app = typer.Typer(help="Lidl Plus receipts CLI")
auth_app = typer.Typer(help="Authentication commands")
connectors_app = typer.Typer(help="Connector platform commands")
connectors_auth_app = typer.Typer(help="Connector authentication commands")
stats_app = typer.Typer(help="Analytics commands")
amazon_app = typer.Typer(help="Amazon connector commands")
users_app = typer.Typer(help="User management commands")
app.add_typer(auth_app, name="auth")
app.add_typer(connectors_app, name="connectors")
connectors_app.add_typer(connectors_auth_app, name="auth")
app.add_typer(stats_app, name="stats")
app.add_typer(amazon_app, name="amazon")
app.add_typer(users_app, name="users")
console = Console()
LOGGER = logging.getLogger(__name__)
DEFAULT_HAR_OUT = Path("/tmp/lidl_auth_capture.har")


@dataclass(slots=True)
class RuntimeContext:
    config: AppConfig
    config_path: Path | None
    db_override: Path | None
    json_output: bool


def _emit(payload: Any, *, json_output: bool) -> None:
    if json_output:
        typer.echo(json.dumps(payload, default=str))
    else:
        if isinstance(payload, str):
            console.print(payload)
        else:
            console.print(payload)


@app.callback()
def global_options(
    ctx: typer.Context,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Path to SQLite database file"),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to config TOML"),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Machine readable output")] = False,
    log_level: Annotated[str | None, typer.Option("--log-level", help="Log level")] = None,
) -> None:
    app_config = build_config(config_path=config, db_override=db)
    if log_level:
        app_config.log_level = log_level
    configure_logging(level=app_config.log_level)
    ctx.obj = RuntimeContext(
        config=app_config,
        config_path=config.expanduser().resolve() if config is not None else None,
        db_override=db.expanduser().resolve() if db is not None else None,
        json_output=json_output,
    )


def _ctx(ctx: typer.Context) -> RuntimeContext:
    runtime = ctx.obj
    if not isinstance(runtime, RuntimeContext):
        raise typer.BadParameter("runtime context was not initialized")
    return runtime


def _create_session_factory(config: AppConfig) -> sessionmaker[Session]:
    db_url = database_url(config)
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    return session_factory(engine)


def _resolve_amazon_state_file(
    path: Path | None,
    config: AppConfig,
    *,
    source_id: str = "amazon_de",
) -> Path:
    target = path or default_amazon_state_file(config, source_id=source_id)
    return target.expanduser().resolve()


def _connector_execution_service(config: AppConfig) -> ConnectorExecutionService:
    return ConnectorExecutionService(config=config)


def _connector_auth_service(config: AppConfig) -> ConnectorAuthOrchestrationService:
    execution = _connector_execution_service(config)
    return ConnectorAuthOrchestrationService(
        config=config,
        connector_builder=execution.build_receipt_connector,
    )


def _connector_error_exit_code(exc: Exception) -> int:
    if "auth token missing" in str(exc).lower():
        return 2
    return 1


def _json_error_payload(exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": str(exc),
        "exception_type": type(exc).__name__,
    }
    if isinstance(exc, ConnectorRuntimeError):
        payload.update(
            {
                "failure_class": "connector_runtime",
                "code": exc.code,
                "retryable": exc.retryable,
                "diagnostics": exc.diagnostics.model_dump(mode="python"),
            }
        )
    else:
        payload["failure_class"] = "command_execution"
    return payload


def _parse_connector_options(entries: list[str]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for entry in entries:
        key, separator, raw_value = entry.partition("=")
        if separator != "=":
            raise typer.BadParameter(
                "connector options must use key=value format",
                param_hint="--option",
            )
        normalized_key = key.strip().replace("-", "_")
        if not normalized_key:
            raise typer.BadParameter(
                "connector option keys must be non-empty",
                param_hint="--option",
            )
        if normalized_key in options:
            raise typer.BadParameter(
                f"duplicate connector option: {normalized_key}",
                param_hint="--option",
            )
        options[normalized_key] = raw_value.strip()
    return options


def _sync_result_payload(
    *,
    result: Any,
    source_id: str,
    display_name: str,
    runtime_identity: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "ok": result.ok,
        "source_id": source_id,
        "display_name": display_name,
        "full": result.full,
        "pages": result.pages,
        "receipts_seen": result.receipts_seen,
        "new_receipts": result.new_receipts,
        "new_items": result.new_items,
        "skipped_existing": result.skipped_existing,
        "cutoff_hit": result.cutoff_hit,
        "warnings": result.warnings,
        "validation": result.validation,
        "runtime": runtime_identity,
    }
    if is_amazon_source_id(source_id):
        payload["records_seen"] = result.receipts_seen
        payload["orders_fetched"] = result.receipts_seen
    payload.update(metadata)
    return payload


def _render_sync_result_table(
    *,
    title: str,
    payload: dict[str, Any],
) -> None:
    table = Table(title=title)
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Pages", str(payload["pages"]))
    if is_amazon_source_id(str(payload["source_id"])):
        table.add_row("Orders fetched", str(payload["receipts_seen"]))
        table.add_row("Records seen", str(payload["receipts_seen"]))
    else:
        table.add_row("Receipts seen", str(payload["receipts_seen"]))
    table.add_row("New receipts", str(payload["new_receipts"]))
    table.add_row("New items", str(payload["new_items"]))
    table.add_row("Skipped existing", str(payload["skipped_existing"]))
    table.add_row("Cutoff reached", str(payload["cutoff_hit"]))
    state_file = payload.get("state_file")
    if state_file:
        table.add_row("State file", str(state_file))
    dump_html = payload.get("dump_html")
    if dump_html:
        table.add_row("HTML dump dir", str(dump_html))
    warnings = payload.get("warnings")
    if isinstance(warnings, list) and warnings:
        table.add_row("Warnings", "; ".join(str(item) for item in warnings))
    console.print(table)


def _sync_progress_description(state: SyncProgress) -> str:
    if state.stage == "authenticating":
        return "stage=authenticating detail=checking_saved_session"
    if state.stage == "refreshing_auth":
        return "stage=refreshing_auth detail=refreshing_receipt_session"
    if state.stage == "healthcheck":
        return "stage=healthcheck detail=validating_connector_access"
    if state.stage == "discovering":
        if state.pages == 0 and state.discovered_receipts == 0:
            return "stage=discovering detail=looking_for_receipts"
        pages = str(state.pages)
        if state.pages_total:
            pages = f"{pages}/{state.pages_total}"
        return f"stage=discovering pages={pages} queued={state.discovered_receipts}"
    if state.stage == "processing":
        if state.receipts_seen == 0 and state.discovered_receipts > 0:
            return f"stage=processing detail=preparing_import total={state.discovered_receipts}"
        current = f" current={state.current_record_ref}" if state.current_record_ref else ""
        return (
            f"stage=processing seen={state.receipts_seen}/{state.discovered_receipts or '?'} "
            f"new={state.new_receipts} items={state.new_items} skipped={state.skipped_existing}{current}"
        )
    if state.stage == "finalizing":
        return (
            f"stage=finalizing seen={state.receipts_seen} new={state.new_receipts} "
            f"skipped={state.skipped_existing}"
        )
    return (
        f"stage={state.stage} pages={state.pages} queued={state.discovered_receipts} "
        f"seen={state.receipts_seen} new={state.new_receipts}"
    )


def _run_connector_sync_command(
    ctx: typer.Context,
    *,
    source_id: str,
    full: bool,
    connector_options: dict[str, Any] | None = None,
    tracking_source_id: str | None = None,
) -> None:
    runtime = _ctx(ctx)
    service = _connector_execution_service(runtime.config)
    sync_options = dict(connector_options or {})
    owner_user_id_raw = sync_options.pop("owner_user_id", None)
    owner_user_id = str(owner_user_id_raw).strip() if owner_user_id_raw is not None else None
    if owner_user_id == "":
        owner_user_id = None
    try:
        resolved = service.build_receipt_connector(
            source_id=source_id,
            connector_options=sync_options or None,
            tracking_source_id=tracking_source_id,
        )
        db_sessions = _create_session_factory(runtime.config)
        sync_service = SyncService(
            client=resolved.client,
            session_factory=db_sessions,
            config=resolved.source_config,
            connector=resolved.connector,
            owner_user_id=owner_user_id,
        )
        if runtime.json_output:
            result = sync_service.sync(full=full)
        elif sys.stdout.isatty():
            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
            ) as progress:
                task = progress.add_task(
                    f"Syncing {resolved.manifest.display_name} receipts...",
                    total=None,
                )

                def on_progress(state: SyncProgress) -> None:
                    progress.update(
                        task,
                        description=_sync_progress_description(state),
                    )

                result = sync_service.sync(full=full, progress_cb=on_progress)
        else:
            last_emitted = ""
            last_emit_at = 0.0

            def on_progress(state: SyncProgress) -> None:
                nonlocal last_emitted, last_emit_at
                description = _sync_progress_description(state)
                now = time.monotonic()
                if (
                    description == last_emitted
                    and state.stage == "processing"
                    and state.receipts_seen % 10 != 0
                    and now - last_emit_at < 5.0
                ):
                    return
                typer.echo(description)
                last_emitted = description
                last_emit_at = now

            result = sync_service.sync(full=full, progress_cb=on_progress)
    except Exception as exc:  # noqa: BLE001
        if runtime.json_output:
            _emit(_json_error_payload(exc), json_output=True)
            raise typer.Exit(code=_connector_error_exit_code(exc)) from exc
        raise typer.BadParameter(str(exc)) from exc

    payload = _sync_result_payload(
        result=result,
        source_id=resolved.manifest.source_id,
        display_name=resolved.manifest.display_name,
        runtime_identity=resolved.connector.runtime_identity(),
        metadata=resolved.metadata,
    )
    if runtime.json_output:
        _emit(payload, json_output=True)
        if not result.ok:
            raise typer.Exit(code=1)
        return
    _render_sync_result_table(title=f"{resolved.manifest.display_name} Sync Result", payload=payload)


def _run_connector_bootstrap_command(
    ctx: typer.Context,
    *,
    source_id: str,
    options: dict[str, Any] | None = None,
) -> None:
    runtime = _ctx(ctx)
    service = _connector_auth_service(runtime.config)
    try:
        resolved = service.run_bootstrap(source_id=source_id, options=options)
    except Exception as exc:  # noqa: BLE001
        if runtime.json_output:
            _emit(_json_error_payload(exc), json_output=True)
            raise typer.Exit(code=_connector_error_exit_code(exc)) from exc
        raise typer.BadParameter(str(exc)) from exc

    payload = {
        "ok": resolved.ok,
        "source_id": resolved.source_id,
        "display_name": resolved.manifest.display_name,
        "auth_state": resolved.state,
        "detail": resolved.detail,
        "runtime": {
            "plugin_id": resolved.manifest.plugin_id,
            "source_id": resolved.manifest.source_id,
            "runtime_kind": resolved.manifest.runtime_kind,
        },
        "diagnostics": resolved.diagnostics,
        **resolved.metadata,
    }
    if runtime.json_output:
        _emit(payload, json_output=True)
        raise typer.Exit(code=0 if resolved.ok else 1)
    if not resolved.ok:
        raise typer.BadParameter(
            f"{resolved.manifest.display_name} login/session capture failed. "
            "Re-run and complete login before pressing Enter."
        )
    state_file = resolved.metadata.get("state_file")
    if state_file:
        console.print(f"{resolved.manifest.display_name} session stored at {state_file}")
    else:
        console.print("ok")


@auth_app.command("bootstrap")
def auth_bootstrap(
    ctx: typer.Context,
    refresh_token: Annotated[
        str | None,
        typer.Option("--refresh-token", help="Refresh token to store"),
    ] = None,
    headful: Annotated[
        bool,
        typer.Option("--headful/--no-headful", help="Launch headful browser helper"),
    ] = True,
    har_out: Annotated[
        Path,
        typer.Option("--har-out", help="HAR output path for manual exploration"),
    ] = DEFAULT_HAR_OUT,
) -> None:
    runtime = _ctx(ctx)
    service = _connector_auth_service(runtime.config)
    token_value = refresh_token
    if not token_value and not headful:
        if not sys.stdin.isatty():
            typer.echo("No token captured and no terminal available for manual entry.", err=True)
            raise typer.Exit(code=1)
        token_value = typer.prompt("Paste refresh token", hide_input=True).strip()
    try:
        result = service.run_bootstrap(
            source_id=runtime.config.source,
            options={
                "refresh_token": token_value,
                "headful": headful,
                "har_out": har_out,
            },
        )
    except Exception as exc:  # noqa: BLE001
        if runtime.json_output:
            _emit(_json_error_payload(exc), json_output=True)
            raise typer.Exit(code=_connector_error_exit_code(exc)) from exc
        raise typer.BadParameter(str(exc)) from exc

    if runtime.json_output:
        _emit(
            {
                "ok": result.ok,
                "source_id": result.source_id,
                "auth_state": result.state,
                **result.metadata,
            },
            json_output=True,
        )
        raise typer.Exit(code=0 if result.ok else 1)
    _emit("ok", json_output=False)


@auth_app.command("status")
def auth_status(ctx: typer.Context) -> None:
    """Show the normalized auth/session state for the configured source."""
    runtime = _ctx(ctx)
    _emit_auth_status(
        service=_connector_auth_service(runtime.config),
        source_id=runtime.config.source,
        connector_options=None,
        json_output=runtime.json_output,
    )


def _emit_auth_status(
    *,
    service: ConnectorAuthOrchestrationService,
    source_id: str,
    connector_options: dict[str, Any] | None,
    json_output: bool,
) -> None:
    snapshot = service.get_auth_status(source_id=source_id, connector_options=connector_options)

    if json_output:
        payload: dict[str, Any] = {
            "source_id": snapshot.manifest.source_id,
            "display_name": snapshot.manifest.display_name,
            "auth_kind": snapshot.capabilities.auth_kind,
            "state": snapshot.state,
            "detail": snapshot.detail,
            "available_actions": list(snapshot.available_actions),
            "implemented_actions": list(snapshot.implemented_actions),
            "compatibility_actions": list(snapshot.compatibility_actions),
            "reserved_actions": list(snapshot.reserved_actions),
            "metadata": snapshot.metadata,
            "diagnostics": snapshot.diagnostics,
        }
        if snapshot.bootstrap is not None:
            payload["bootstrap"] = {
                "state": snapshot.bootstrap.state,
                "started_at": (
                    snapshot.bootstrap.started_at.isoformat()
                    if snapshot.bootstrap.started_at is not None
                    else None
                ),
                "finished_at": (
                    snapshot.bootstrap.finished_at.isoformat()
                    if snapshot.bootstrap.finished_at is not None
                    else None
                ),
                "return_code": snapshot.bootstrap.return_code,
                "output_tail": list(snapshot.bootstrap.output_tail),
                "can_cancel": snapshot.bootstrap.can_cancel,
            }
        _emit(payload, json_output=True)
        return

    table = Table(title="Auth Status")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Source", snapshot.manifest.display_name)
    table.add_row("Auth kind", snapshot.capabilities.auth_kind)
    table.add_row("State", snapshot.state)
    table.add_row("Detail", snapshot.detail or "-")
    table.add_row(
        "Available actions",
        ", ".join(snapshot.available_actions) if snapshot.available_actions else "-",
    )
    if snapshot.compatibility_actions:
        table.add_row("Compatibility actions", ", ".join(snapshot.compatibility_actions))
    if snapshot.bootstrap is not None:
        table.add_row("Bootstrap", snapshot.bootstrap.state)
    console.print(table)


@connectors_auth_app.command("bootstrap")
def connector_auth_bootstrap(
    ctx: typer.Context,
    source_id: Annotated[
        str,
        typer.Option("--source-id", help="Connector source ID to bootstrap"),
    ],
    options: Annotated[
        list[str] | None,
        typer.Option(
            "--option",
            help="Connector bootstrap option as key=value; repeat for multiple options",
        ),
    ] = None,
) -> None:
    parsed_options = _parse_connector_options(list(options or ()))
    _run_connector_bootstrap_command(
        ctx,
        source_id=source_id,
        options=parsed_options or None,
    )


@connectors_auth_app.command("status")
def connector_auth_status(
    ctx: typer.Context,
    source_id: Annotated[
        str,
        typer.Option("--source-id", help="Connector source ID to inspect"),
    ],
    options: Annotated[
        list[str] | None,
        typer.Option(
            "--option",
            help="Connector auth-status option as key=value; repeat for multiple options",
        ),
    ] = None,
) -> None:
    runtime = _ctx(ctx)
    _emit_auth_status(
        service=_connector_auth_service(runtime.config),
        source_id=source_id,
        connector_options=_parse_connector_options(list(options or ())) or None,
        json_output=runtime.json_output,
    )


@connectors_app.command("sync")
def connector_sync_command(
    ctx: typer.Context,
    source_id: Annotated[
        str,
        typer.Option("--source-id", help="Connector source ID to sync"),
    ],
    full: Annotated[
        bool,
        typer.Option("--full", help="Fetch historical receipts until stop condition"),
    ] = False,
    tracking_source_id: Annotated[
        str | None,
        typer.Option(
            "--tracking-source-id",
            help="Logical source ID to persist on imported records",
        ),
    ] = None,
    options: Annotated[
        list[str] | None,
        typer.Option(
            "--option",
            help="Connector sync option as key=value; repeat for multiple options",
        ),
    ] = None,
) -> None:
    parsed_options = _parse_connector_options(list(options or ()))
    _run_connector_sync_command(
        ctx,
        source_id=source_id,
        full=full,
        connector_options=parsed_options or None,
        tracking_source_id=tracking_source_id,
    )


def _prompt_password(prompt: str = "Password") -> str:
    password = str(typer.prompt(prompt, hide_input=True, confirmation_prompt=True)).strip()
    if not password:
        raise typer.BadParameter("password must not be empty")
    return password


@users_app.command("list")
def users_list_command(
    ctx: typer.Context,
    include_service: Annotated[
        bool,
        typer.Option("--include-service", help="Include internal service account"),
    ] = False,
) -> None:
    runtime = _ctx(ctx)
    db_sessions = _create_session_factory(runtime.config)
    with session_scope(db_sessions) as session:
        users = session.execute(select(User).order_by(User.username.asc())).scalars().all()
        rows = [
            {
                "user_id": user.user_id,
                "username": user.username,
                "display_name": user.display_name,
                "is_admin": user.is_admin,
                "is_service": user.username == SERVICE_USERNAME,
            }
            for user in users
            if include_service or user.username != SERVICE_USERNAME
        ]

    if runtime.json_output:
        _emit({"ok": True, "result": {"users": rows}}, json_output=True)
        return

    table = Table(title="Users")
    table.add_column("Username")
    table.add_column("Display name")
    table.add_column("Admin")
    for row in rows:
        table.add_row(
            str(row["username"]),
            str(row["display_name"] or ""),
            "yes" if row["is_admin"] else "",
        )
    console.print(table)


@users_app.command("add")
def users_add_command(
    ctx: typer.Context,
    username: Annotated[str, typer.Option("--username", help="Username to create")],
    display_name: Annotated[
        str | None,
        typer.Option("--display-name", help="Optional display name"),
    ] = None,
    admin: Annotated[bool, typer.Option("--admin", help="Grant admin permissions")] = False,
    password: Annotated[
        str | None,
        typer.Option("--password", help="Password (omit to prompt securely)"),
    ] = None,
) -> None:
    runtime = _ctx(ctx)
    raw_password = password if password is not None else _prompt_password()
    db_sessions = _create_session_factory(runtime.config)
    with session_scope(db_sessions) as session:
        user = create_local_user(
            session,
            username=username,
            password=raw_password,
            display_name=display_name,
            is_admin=admin,
        )
        row = {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
        }

    if runtime.json_output:
        _emit({"ok": True, "result": row}, json_output=True)
        return
    console.print(f"Created user {row['username']}")


@users_app.command("passwd")
def users_passwd_command(
    ctx: typer.Context,
    username: str,
    password: Annotated[
        str | None,
        typer.Option("--password", help="New password (omit to prompt securely)"),
    ] = None,
) -> None:
    runtime = _ctx(ctx)
    raw_password = password if password is not None else _prompt_password("New password")
    db_sessions = _create_session_factory(runtime.config)
    with session_scope(db_sessions) as session:
        user = get_user_by_username(session, username=username)
        if user is None:
            raise typer.BadParameter(f"user not found: {username}")
        if user.username == SERVICE_USERNAME:
            raise typer.BadParameter("service account password cannot be changed")
        set_user_password(session, user=user, password=raw_password)

    if runtime.json_output:
        _emit({"ok": True, "result": {"username": username}}, json_output=True)
        return
    console.print(f"Password updated for {username}")


@users_app.command("remove")
def users_remove_command(
    ctx: typer.Context,
    username: str,
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation prompt")] = False,
) -> None:
    runtime = _ctx(ctx)
    db_sessions = _create_session_factory(runtime.config)
    with session_scope(db_sessions) as session:
        user = get_user_by_username(session, username=username)
        if user is None:
            raise typer.BadParameter(f"user not found: {username}")
        if user.username == SERVICE_USERNAME:
            raise typer.BadParameter("service account cannot be removed")
        owns_sources = (
            session.execute(select(Source.id).where(Source.user_id == user.user_id).limit(1))
            .scalar_one_or_none()
            is not None
        )
        owns_transactions = (
            session.execute(
                select(Transaction.id).where(Transaction.user_id == user.user_id).limit(1)
            ).scalar_one_or_none()
            is not None
        )
        if owns_sources or owns_transactions:
            raise typer.BadParameter("cannot remove user with owned sources or transactions")
        if not yes and not runtime.json_output:
            typer.confirm(f"Remove user {user.username}?", abort=True)
        session.delete(user)

    if runtime.json_output:
        _emit({"ok": True, "result": {"username": username}}, json_output=True)
        return
    console.print(f"Removed user {username}")


@app.command("sync")
def sync_command(
    ctx: typer.Context,
    full: Annotated[
        bool,
        typer.Option("--full", help="Fetch historical receipts until stop condition"),
    ] = False,
) -> None:
    _run_connector_sync_command(ctx, source_id=_ctx(ctx).config.source, full=full)


@app.command("serve")
def serve_command(
    ctx: typer.Context,
    host: Annotated[str, typer.Option("--host", help="HTTP bind host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="HTTP bind port")] = 8000,
    workers: Annotated[int, typer.Option("--workers", help="Uvicorn worker processes")] = 1,
) -> None:
    runtime = _ctx(ctx)
    if workers < 1:
        raise typer.BadParameter("--workers must be >= 1")
    os.environ["LIDLTOOL_HTTP_BIND_HOST"] = host
    os.environ["LIDLTOOL_CONFIG"] = str(
        runtime.config_path or default_config_file(runtime.config.config_dir)
    )
    os.environ["LIDLTOOL_DB"] = str(runtime.db_override or runtime.config.db_path)
    validate_config(runtime.config, bind_host=host)
    db_url = database_url(runtime.config)
    migrate_db(db_url)
    sessions = session_factory(create_engine_for_url(db_url))
    with session_scope(sessions) as session:
        evaluate_deployment_policy(
            runtime.config,
            bind_host=host,
            has_human_users=human_user_count(session) > 0,
        )
    uvicorn.run(
        "lidltool.api.http_server:create_app",
        factory=True,
        host=host,
        port=port,
        workers=workers,
    )


@stats_app.command("month")
def stats_month(
    ctx: typer.Context,
    year: Annotated[int, typer.Option("--year", help="Calendar year, e.g. 2026")],
    month: Annotated[int | None, typer.Option("--month", help="Optional month 1..12")] = None,
) -> None:
    runtime = _ctx(ctx)
    db_sessions = _create_session_factory(runtime.config)

    with session_scope(db_sessions) as session:
        result = month_stats(session, year=year, month=month)

    if runtime.json_output:
        _emit({"ok": True, "result": result}, json_output=True)
        return

    totals = result["totals"]
    console.print(f"Total spend: {totals['total_currency']} EUR")
    console.print(f"Receipts: {totals['receipt_count']}")

    store_table = Table(title="Top stores")
    store_table.add_column("Store")
    store_table.add_column("Spend")
    store_table.add_column("Receipts")
    for row in result["stores"]:
        store_table.add_row(row["store_name"], f"{row['total_currency']} EUR", str(row["receipts"]))
    console.print(store_table)

    cat_table = Table(title="Category breakdown")
    cat_table.add_column("Category")
    cat_table.add_column("Spend")
    for row in result["categories"][:10]:
        cat_table.add_row(row["category"], f"{row['total_currency']} EUR")
    console.print(cat_table)


@app.command("export")
def export_command(
    ctx: typer.Context,
    out: Annotated[Path, typer.Option("--out", help="Output file path")],
    format_name: Annotated[str, typer.Option("--format", help="Export format: json")] = "json",
) -> None:
    runtime = _ctx(ctx)
    if format_name.lower() != "json":
        raise typer.BadParameter("Only --format json is currently supported")

    db_sessions = _create_session_factory(runtime.config)
    with session_scope(db_sessions) as session:
        payload = export_receipts(session)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    if runtime.json_output:
        _emit({"ok": True, "out": str(out), "records": len(payload)}, json_output=True)
    else:
        console.print(f"Exported {len(payload)} receipts to {out}")


@amazon_app.command("import")
def amazon_import_command(
    ctx: typer.Context,
    input_file: Annotated[
        Path,
        typer.Option("--in", help="Path to Amazon order export JSON"),
    ],
    source: Annotated[
        str,
        typer.Option("--source", help="Logical source ID to track imports"),
    ] = "amazon_de",
    store_name: Annotated[
        str,
        typer.Option("--store-name", help="Store name to persist for imported orders"),
    ] = "Amazon",
) -> None:
    runtime = _ctx(ctx)
    db_sessions = _create_session_factory(runtime.config)
    service = AmazonImportService(
        session_factory=db_sessions,
        source=source,
        store_name=store_name,
    )
    result = service.import_file(input_file)

    payload = {
        "ok": result.ok,
        "records_seen": result.records_seen,
        "new_receipts": result.new_receipts,
        "new_items": result.new_items,
        "skipped_existing": result.skipped_existing,
        "warnings": result.warnings,
    }
    if runtime.json_output:
        _emit(payload, json_output=True)
        return

    table = Table(title="Amazon Import Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Records seen", str(result.records_seen))
    table.add_row("New receipts", str(result.new_receipts))
    table.add_row("New items", str(result.new_items))
    table.add_row("Skipped existing", str(result.skipped_existing))
    if result.warnings:
        table.add_row("Warnings", "; ".join(result.warnings))
    console.print(table)


@amazon_app.command("scrape")
def amazon_scrape_command(
    ctx: typer.Context,
    source_id: Annotated[
        str,
        typer.Option("--source-id", help="Amazon source id, e.g. amazon_de, amazon_fr, or amazon_gb"),
    ] = "amazon_de",
    years: Annotated[
        int,
        typer.Option("--years", help="How many recent years to scan"),
    ] = 2,
    max_pages_per_year: Annotated[
        int,
        typer.Option("--max-pages-per-year", help="Pagination limit per year"),
    ] = 8,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for Amazon session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="Amazon domain override, e.g. amazon.fr"),
    ] = "",
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser headless while scraping"),
    ] = True,
    dump_html: Annotated[
        Path | None,
        typer.Option("--dump-html", help="Save raw HTML pages to this directory"),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Write scraped orders JSON to this file"),
    ] = None,
) -> None:
    runtime = _ctx(ctx)
    profile = get_country_profile(source_id=source_id, domain=domain or None)
    target_state = _resolve_amazon_state_file(state_file, runtime.config, source_id=profile.source_id)
    client = AmazonPlaywrightClient(
        state_file=target_state,
        source_id=profile.source_id,
        domain=domain or None,
        headless=headless,
        dump_html_dir=dump_html,
    )

    try:
        orders = client.fetch_orders(years=years, max_pages_per_year=max_pages_per_year)
    except AmazonClientError as exc:
        if runtime.json_output:
            _emit({"ok": False, "error": str(exc)}, json_output=True)
            raise typer.Exit(code=1) from exc
        raise typer.BadParameter(str(exc)) from exc

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(orders, ensure_ascii=False, indent=2), encoding="utf-8")

    orders_with_items = 0
    total_items = 0
    items_without_price = 0
    for raw_order in orders:
        if not isinstance(raw_order, dict):
            continue
        order_items = raw_order.get("items")
        items = order_items if isinstance(order_items, list) else []
        if items:
            orders_with_items += 1
        total_items += len(items)
        for item in items:
            if not isinstance(item, dict):
                continue
            if float(item.get("price") or 0) <= 0:
                items_without_price += 1

    payload = {
        "ok": True,
        "orders_fetched": len(orders),
        "orders_with_items": orders_with_items,
        "total_items": total_items,
        "items_without_price": items_without_price,
        "state_file": str(target_state),
        "out": str(out) if out is not None else None,
    }
    if runtime.json_output:
        _emit(payload, json_output=True)
        return

    table = Table(title="Amazon Scrape Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Orders fetched", str(len(orders)))
    table.add_row("Orders with items", str(orders_with_items))
    table.add_row("Items total", str(total_items))
    table.add_row("Items without price", str(items_without_price))
    table.add_row("State file", str(target_state))
    if out is not None:
        table.add_row("JSON output", str(out))
    console.print(table)


@amazon_app.command("cron-example")
def amazon_cron_example_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for Amazon session"),
    ] = None,
) -> None:
    runtime = _ctx(ctx)
    target = _resolve_amazon_state_file(state_file, runtime.config, source_id="amazon_de")
    command = (
        "0 7 * * * /usr/bin/env lidltool connectors sync "
        f"--source-id amazon_de --full --option state_file={target} --db {runtime.config.db_path}"
        " >> ~/.local/share/lidltool/cron.log 2>&1"
    )
    if runtime.json_output:
        _emit({"ok": True, "cron": command}, json_output=True)
        return
    console.print(command)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
