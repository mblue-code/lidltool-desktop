from __future__ import annotations

import json
import logging
import sys
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
from lidltool.amazon.importer import AmazonImportService
from lidltool.amazon.session import default_amazon_state_file
from lidltool.analytics.queries import export_receipts, month_stats
from lidltool.auth.users import (
    SERVICE_USERNAME,
    create_local_user,
    get_user_by_username,
    set_user_password,
)
from lidltool.config import AppConfig, build_config, database_url, validate_config
from lidltool.connectors.auth.auth_orchestration import ConnectorAuthOrchestrationService
from lidltool.connectors.runtime.execution import ConnectorExecutionService
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import Source, Transaction, User
from lidltool.dm.client_playwright import DmClientError, DmPlaywrightClient
from lidltool.dm.session import default_dm_state_file
from lidltool.ingest.sync import SyncProgress, SyncService
from lidltool.kaufland.session import default_kaufland_state_file
from lidltool.logging import configure_logging
from lidltool.rossmann.session import default_rossmann_state_file

app = typer.Typer(help="Lidl Plus receipts CLI")
auth_app = typer.Typer(help="Authentication commands")
stats_app = typer.Typer(help="Analytics commands")
amazon_app = typer.Typer(help="Amazon connector commands")
amazon_auth_app = typer.Typer(help="Amazon authentication commands")
rewe_app = typer.Typer(help="REWE connector commands")
rewe_auth_app = typer.Typer(help="REWE authentication commands")
kaufland_app = typer.Typer(help="Kaufland connector commands")
kaufland_auth_app = typer.Typer(help="Kaufland authentication commands")
dm_app = typer.Typer(help="dm connector commands")
dm_auth_app = typer.Typer(help="dm authentication commands")
rossmann_app = typer.Typer(help="Rossmann connector commands")
rossmann_auth_app = typer.Typer(help="Rossmann authentication commands")
users_app = typer.Typer(help="User management commands")
app.add_typer(auth_app, name="auth")
app.add_typer(stats_app, name="stats")
app.add_typer(amazon_app, name="amazon")
amazon_app.add_typer(amazon_auth_app, name="auth")
app.add_typer(rewe_app, name="rewe")
rewe_app.add_typer(rewe_auth_app, name="auth")
app.add_typer(kaufland_app, name="kaufland")
kaufland_app.add_typer(kaufland_auth_app, name="auth")
app.add_typer(dm_app, name="dm")
dm_app.add_typer(dm_auth_app, name="auth")
app.add_typer(rossmann_app, name="rossmann")
rossmann_app.add_typer(rossmann_auth_app, name="auth")
app.add_typer(users_app, name="users")
console = Console()
LOGGER = logging.getLogger(__name__)
DEFAULT_HAR_OUT = Path("/tmp/lidl_auth_capture.har")


@dataclass(slots=True)
class RuntimeContext:
    config: AppConfig
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
    ctx.obj = RuntimeContext(config=app_config, json_output=json_output)


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


def _resolve_amazon_state_file(path: Path | None, config: AppConfig) -> Path:
    target = path or default_amazon_state_file(config)
    return target.expanduser().resolve()


def _resolve_rewe_state_file(path: Path | None, config: AppConfig) -> Path:
    from lidltool.rewe.session import default_rewe_state_file

    target = path or default_rewe_state_file(config)
    return target.expanduser().resolve()


def _resolve_kaufland_state_file(path: Path | None, config: AppConfig) -> Path:
    target = path or default_kaufland_state_file(config)
    return target.expanduser().resolve()


def _resolve_dm_state_file(path: Path | None, config: AppConfig) -> Path:
    target = path or default_dm_state_file(config)
    return target.expanduser().resolve()


def _resolve_rossmann_state_file(path: Path | None, config: AppConfig) -> Path:
    target = path or default_rossmann_state_file(config)
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
        "runtime": runtime_identity,
    }
    if source_id == "amazon_de":
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
    if payload["source_id"] == "amazon_de":
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
    try:
        resolved = service.build_receipt_connector(
            source_id=source_id,
            connector_options=connector_options,
            tracking_source_id=tracking_source_id,
        )
        db_sessions = _create_session_factory(runtime.config)
        sync_service = SyncService(
            client=resolved.client,
            session_factory=db_sessions,
            config=resolved.source_config,
            connector=resolved.connector,
        )
        if runtime.json_output:
            result = sync_service.sync(full=full)
        else:
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
                        description=(
                            f"pages={state.pages} seen={state.receipts_seen} "
                            f"new={state.new_receipts} items={state.new_items}"
                        ),
                    )

                result = sync_service.sync(full=full, progress_cb=on_progress)
    except Exception as exc:  # noqa: BLE001
        if runtime.json_output:
            _emit({"ok": False, "error": str(exc)}, json_output=True)
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
            _emit({"ok": False, "error": str(exc)}, json_output=True)
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
            _emit({"ok": False, "error": str(exc)}, json_output=True)
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
    service = _connector_auth_service(runtime.config)
    snapshot = service.get_auth_status(source_id=runtime.config.source)

    if runtime.json_output:
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
    if snapshot.bootstrap is not None:
        table.add_row("Bootstrap", snapshot.bootstrap.state)
    console.print(table)


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
    host: Annotated[str, typer.Option("--host", help="HTTP bind host")] = "0.0.0.0",
    port: Annotated[int, typer.Option("--port", help="HTTP bind port")] = 8000,
    workers: Annotated[int, typer.Option("--workers", help="Uvicorn worker processes")] = 1,
) -> None:
    runtime = _ctx(ctx)
    if workers < 1:
        raise typer.BadParameter("--workers must be >= 1")
    validate_config(runtime.config)
    db_url = database_url(runtime.config)
    migrate_db(db_url)
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


@amazon_auth_app.command("bootstrap")
def amazon_auth_bootstrap_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for Amazon session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="Amazon domain, e.g. amazon.de"),
    ] = "amazon.de",
) -> None:
    _run_connector_bootstrap_command(
        ctx,
        source_id="amazon_de",
        options={"state_file": state_file, "domain": domain},
    )


@amazon_app.command("sync")
def amazon_sync_command(
    ctx: typer.Context,
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
        typer.Option("--domain", help="Amazon domain, e.g. amazon.de"),
    ] = "amazon.de",
    source: Annotated[
        str,
        typer.Option("--source", help="Logical source ID to track imports"),
    ] = "amazon_de",
    store_name: Annotated[
        str,
        typer.Option("--store-name", help="Store name to persist for imported orders"),
    ] = "Amazon",
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser headless during sync"),
    ] = True,
    dump_html: Annotated[
        Path | None,
        typer.Option("--dump-html", help="Save raw HTML pages to this directory for fixture capture"),
    ] = None,
) -> None:
    _run_connector_sync_command(
        ctx,
        source_id="amazon_de",
        full=True,
        connector_options={
            "state_file": state_file,
            "domain": domain,
            "headless": headless,
            "dump_html": dump_html,
            "years": years,
            "max_pages_per_year": max_pages_per_year,
            "store_name": store_name,
        },
        tracking_source_id=source,
    )


@amazon_app.command("scrape")
def amazon_scrape_command(
    ctx: typer.Context,
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
        typer.Option("--domain", help="Amazon domain, e.g. amazon.de"),
    ] = "amazon.de",
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
    target_state = _resolve_amazon_state_file(state_file, runtime.config)
    client = AmazonPlaywrightClient(
        state_file=target_state,
        domain=domain,
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
    target = _resolve_amazon_state_file(state_file, runtime.config)
    command = (
        "0 7 * * * /usr/bin/env lidltool amazon sync "
        f"--state-file {target} --db {runtime.config.db_path}"
        " >> ~/.local/share/lidltool/cron.log 2>&1"
    )
    if runtime.json_output:
        _emit({"ok": True, "cron": command}, json_output=True)
        return
    console.print(command)


@rewe_auth_app.command("bootstrap")
def rewe_auth_bootstrap_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for REWE session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="REWE domain, e.g. shop.rewe.de"),
    ] = "shop.rewe.de",
) -> None:
    _run_connector_bootstrap_command(
        ctx,
        source_id="rewe_de",
        options={"state_file": state_file, "domain": domain},
    )


@rewe_app.command("sync")
def rewe_sync_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for REWE session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="REWE domain, e.g. shop.rewe.de"),
    ] = "shop.rewe.de",
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", help="Maximum order-history pages to scan"),
    ] = 10,
    source: Annotated[
        str,
        typer.Option("--source", help="Logical source ID to track sync"),
    ] = "rewe_de",
    store_name: Annotated[
        str,
        typer.Option("--store-name", help="Store name to persist for synced orders"),
    ] = "REWE",
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser headless during sync"),
    ] = True,
) -> None:
    _run_connector_sync_command(
        ctx,
        source_id="rewe_de",
        full=True,
        connector_options={
            "state_file": state_file,
            "domain": domain,
            "headless": headless,
            "max_pages": max_pages,
            "store_name": store_name,
        },
        tracking_source_id=source,
    )


@kaufland_auth_app.command("bootstrap")
def kaufland_auth_bootstrap_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for Kaufland session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="Kaufland domain, e.g. www.kaufland.de"),
    ] = "www.kaufland.de",
) -> None:
    _run_connector_bootstrap_command(
        ctx,
        source_id="kaufland_de",
        options={"state_file": state_file, "domain": domain},
    )


@kaufland_app.command("sync")
def kaufland_sync_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for Kaufland session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="Kaufland domain, e.g. www.kaufland.de"),
    ] = "www.kaufland.de",
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", help="Maximum order-history pages to scan"),
    ] = 10,
    source: Annotated[
        str,
        typer.Option("--source", help="Logical source ID to track sync"),
    ] = "kaufland_de",
    store_name: Annotated[
        str,
        typer.Option("--store-name", help="Store name to persist for synced orders"),
    ] = "Kaufland",
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser headless during sync"),
    ] = True,
) -> None:
    _run_connector_sync_command(
        ctx,
        source_id="kaufland_de",
        full=True,
        connector_options={
            "state_file": state_file,
            "domain": domain,
            "headless": headless,
            "max_pages": max_pages,
            "store_name": store_name,
        },
        tracking_source_id=source,
    )


@dm_auth_app.command("bootstrap")
def dm_auth_bootstrap_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for dm session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="dm domain, e.g. www.dm.de"),
    ] = "www.dm.de",
) -> None:
    _run_connector_bootstrap_command(
        ctx,
        source_id="dm_de",
        options={"state_file": state_file, "domain": domain},
    )


@dm_app.command("sync")
def dm_sync_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for dm session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="dm domain, e.g. www.dm.de"),
    ] = "www.dm.de",
    max_pages: Annotated[
        int,
        typer.Option(
            "--max-pages",
            help="Maximum purchases load-more cycles to scan (<=0 means unlimited)",
        ),
    ] = 120,
    detail_fetch_limit: Annotated[
        int,
        typer.Option("--detail-fetch-limit", help="How many detail receipts to parse (-1 means all)"),
    ] = -1,
    detail_retry_count: Annotated[
        int,
        typer.Option("--detail-retry-count", help="Retries per detail receipt when parsing fails"),
    ] = 2,
    detail_retry_backoff_ms: Annotated[
        int,
        typer.Option("--detail-retry-backoff-ms", help="Backoff in ms between detail retries"),
    ] = 800,
    detail_pause_ms: Annotated[
        int,
        typer.Option("--detail-pause-ms", help="Pause in ms between detail receipts"),
    ] = 120,
    detail_batch_size: Annotated[
        int,
        typer.Option("--detail-batch-size", help="Detail receipts per batch before a longer pause"),
    ] = 40,
    detail_batch_pause_ms: Annotated[
        int,
        typer.Option("--detail-batch-pause-ms", help="Pause in ms after each detail batch"),
    ] = 1200,
    max_consecutive_detail_failures: Annotated[
        int,
        typer.Option(
            "--max-consecutive-detail-failures",
            help="Abort after this many consecutive detail failures (<=0 disables)",
        ),
    ] = 25,
    persist_state: Annotated[
        bool,
        typer.Option(
            "--persist-state/--no-persist-state",
            help="Persist refreshed dm session state after successful runs",
        ),
    ] = True,
    state_persist_interval: Annotated[
        int,
        typer.Option(
            "--state-persist-interval",
            help="Persist refreshed session state every N detail receipts",
        ),
    ] = 25,
    session_keepalive_every: Annotated[
        int,
        typer.Option(
            "--session-keepalive-every",
            help="Run account keepalive every N detail receipts (<=0 disables)",
        ),
    ] = 30,
    dump_html: Annotated[
        Path | None,
        typer.Option("--dump-html", help="Dump visited HTML pages for parser discovery"),
    ] = None,
    source: Annotated[
        str,
        typer.Option("--source", help="Logical source ID to track sync"),
    ] = "dm_de",
    store_name: Annotated[
        str,
        typer.Option("--store-name", help="Store name to persist for synced orders"),
    ] = "dm-drogerie markt",
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser headless during sync"),
    ] = True,
) -> None:
    _run_connector_sync_command(
        ctx,
        source_id="dm_de",
        full=True,
        connector_options={
            "state_file": state_file,
            "domain": domain,
            "headless": headless,
            "max_pages": max_pages,
            "detail_fetch_limit": detail_fetch_limit,
            "detail_retry_count": detail_retry_count,
            "detail_retry_backoff_ms": detail_retry_backoff_ms,
            "detail_pause_ms": detail_pause_ms,
            "detail_batch_size": detail_batch_size,
            "detail_batch_pause_ms": detail_batch_pause_ms,
            "max_consecutive_detail_failures": max_consecutive_detail_failures,
            "persist_state": persist_state,
            "state_persist_interval": state_persist_interval,
            "session_keepalive_every": session_keepalive_every,
            "dump_html": dump_html,
            "store_name": store_name,
        },
        tracking_source_id=source,
    )


@dm_app.command("scrape")
def dm_scrape_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for dm session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="dm domain, e.g. www.dm.de"),
    ] = "www.dm.de",
    max_pages: Annotated[
        int,
        typer.Option(
            "--max-pages",
            help="Maximum purchases load-more cycles to scan (<=0 means unlimited)",
        ),
    ] = 120,
    detail_fetch_limit: Annotated[
        int,
        typer.Option("--detail-fetch-limit", help="How many detail receipts to parse (-1 means all)"),
    ] = -1,
    detail_retry_count: Annotated[
        int,
        typer.Option("--detail-retry-count", help="Retries per detail receipt when parsing fails"),
    ] = 2,
    detail_retry_backoff_ms: Annotated[
        int,
        typer.Option("--detail-retry-backoff-ms", help="Backoff in ms between detail retries"),
    ] = 800,
    detail_pause_ms: Annotated[
        int,
        typer.Option("--detail-pause-ms", help="Pause in ms between detail receipts"),
    ] = 120,
    detail_batch_size: Annotated[
        int,
        typer.Option("--detail-batch-size", help="Detail receipts per batch before a longer pause"),
    ] = 40,
    detail_batch_pause_ms: Annotated[
        int,
        typer.Option("--detail-batch-pause-ms", help="Pause in ms after each detail batch"),
    ] = 1200,
    max_consecutive_detail_failures: Annotated[
        int,
        typer.Option(
            "--max-consecutive-detail-failures",
            help="Abort after this many consecutive detail failures (<=0 disables)",
        ),
    ] = 25,
    persist_state: Annotated[
        bool,
        typer.Option(
            "--persist-state/--no-persist-state",
            help="Persist refreshed dm session state after successful runs",
        ),
    ] = True,
    state_persist_interval: Annotated[
        int,
        typer.Option(
            "--state-persist-interval",
            help="Persist refreshed session state every N detail receipts",
        ),
    ] = 25,
    session_keepalive_every: Annotated[
        int,
        typer.Option(
            "--session-keepalive-every",
            help="Run account keepalive every N detail receipts (<=0 disables)",
        ),
    ] = 30,
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser headless during scrape"),
    ] = True,
    dump_html: Annotated[
        Path | None,
        typer.Option("--dump-html", help="Dump visited HTML pages for parser discovery"),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Optional path to write scraped JSON"),
    ] = None,
) -> None:
    runtime = _ctx(ctx)
    target_state = _resolve_dm_state_file(state_file, runtime.config)
    client = DmPlaywrightClient(
        state_file=target_state,
        domain=domain,
        headless=headless,
        max_pages=max_pages,
        detail_fetch_limit=detail_fetch_limit,
        detail_retry_count=detail_retry_count,
        detail_retry_backoff_ms=detail_retry_backoff_ms,
        detail_pause_ms=detail_pause_ms,
        detail_batch_size=detail_batch_size,
        detail_batch_pause_ms=detail_batch_pause_ms,
        max_consecutive_detail_failures=max_consecutive_detail_failures,
        persist_state_on_success=persist_state,
        state_persist_interval=state_persist_interval,
        session_keepalive_every=session_keepalive_every,
        dump_html_dir=dump_html,
    )

    try:
        orders = client.fetch_receipts()
    except DmClientError as exc:
        if runtime.json_output:
            _emit({"ok": False, "error": str(exc)}, json_output=True)
            raise typer.Exit(code=1) from exc
        raise typer.BadParameter(str(exc)) from exc

    payload = {
        "ok": True,
        "orders_fetched": len(orders),
        "state_file": str(target_state),
        "dump_html": str(dump_html) if dump_html is not None else None,
        "orders": orders,
    }
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if runtime.json_output:
        _emit(payload, json_output=True)
        return

    table = Table(title="dm Scrape Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Orders fetched", str(len(orders)))
    table.add_row("State file", str(target_state))
    if dump_html is not None:
        table.add_row("HTML dump dir", str(dump_html))
    if out is not None:
        table.add_row("Output file", str(out))
    console.print(table)


@rossmann_auth_app.command("bootstrap")
def rossmann_auth_bootstrap_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for Rossmann session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="Rossmann domain, e.g. www.rossmann.de"),
    ] = "www.rossmann.de",
) -> None:
    _run_connector_bootstrap_command(
        ctx,
        source_id="rossmann_de",
        options={"state_file": state_file, "domain": domain},
    )


@rossmann_app.command("sync")
def rossmann_sync_command(
    ctx: typer.Context,
    state_file: Annotated[
        Path | None,
        typer.Option("--state-file", help="Playwright storage-state file for Rossmann session"),
    ] = None,
    domain: Annotated[
        str,
        typer.Option("--domain", help="Rossmann domain, e.g. www.rossmann.de"),
    ] = "www.rossmann.de",
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", help="Maximum order-history pages to scan"),
    ] = 10,
    source: Annotated[
        str,
        typer.Option("--source", help="Logical source ID to track sync"),
    ] = "rossmann_de",
    store_name: Annotated[
        str,
        typer.Option("--store-name", help="Store name to persist for synced orders"),
    ] = "Rossmann",
    headless: Annotated[
        bool,
        typer.Option("--headless/--no-headless", help="Run browser headless during sync"),
    ] = True,
) -> None:
    _run_connector_sync_command(
        ctx,
        source_id="rossmann_de",
        full=True,
        connector_options={
            "state_file": state_file,
            "domain": domain,
            "headless": headless,
            "max_pages": max_pages,
            "store_name": store_name,
        },
        tracking_source_id=source,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
