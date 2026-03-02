from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
import uvicorn
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.amazon.bootstrap_playwright import run_amazon_headful_bootstrap
from lidltool.amazon.client_playwright import AmazonClientError, AmazonPlaywrightClient
from lidltool.amazon.importer import AmazonImportService
from lidltool.amazon.session import default_amazon_state_file
from lidltool.analytics.queries import export_receipts, month_stats
from lidltool.auth.bootstrap_playwright import run_headful_bootstrap
from lidltool.auth.token_store import TokenStore
from lidltool.auth.users import (
    SERVICE_USERNAME,
    create_local_user,
    get_user_by_username,
    set_user_password,
)
from lidltool.config import AppConfig, build_config, database_url, validate_config
from lidltool.connectors.amazon_adapter import AmazonConnectorAdapter
from lidltool.connectors.dm_adapter import DmConnectorAdapter
from lidltool.connectors.kaufland_adapter import KauflandConnectorAdapter
from lidltool.connectors.rewe_adapter import ReweConnectorAdapter
from lidltool.connectors.rossmann_adapter import RossmannConnectorAdapter
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import Source, Transaction, User
from lidltool.dm.bootstrap_playwright import run_dm_headful_bootstrap
from lidltool.dm.client_playwright import DmClientError, DmPlaywrightClient
from lidltool.dm.session import default_dm_state_file
from lidltool.ingest.sync import SyncProgress, SyncService
from lidltool.kaufland.bootstrap_playwright import run_kaufland_headful_bootstrap
from lidltool.kaufland.client_playwright import KauflandClientError, KauflandPlaywrightClient
from lidltool.kaufland.session import default_kaufland_state_file
from lidltool.lidl.client import LidlClientError, create_lidl_client
from lidltool.logging import configure_logging
from lidltool.rewe.bootstrap_playwright import run_rewe_headful_bootstrap
from lidltool.rewe.client_playwright import ReweClientError, RewePlaywrightClient
from lidltool.rossmann.bootstrap_playwright import run_rossmann_headful_bootstrap
from lidltool.rossmann.client_playwright import RossmannClientError, RossmannPlaywrightClient
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
    token_store = TokenStore.from_config(runtime.config)

    token_value = refresh_token
    if not token_value and headful:
        source_suffix = runtime.config.source.rsplit("_", 1)[-1]  # "lidl_plus_de" -> "de"
        token_value = run_headful_bootstrap(
            har_out, country=source_suffix.upper(), language=source_suffix.lower()
        )
    if not token_value:
        if not sys.stdin.isatty():
            typer.echo("No token captured and no terminal available for manual entry.", err=True)
            raise typer.Exit(code=1)
        token_value = typer.prompt("Paste refresh token", hide_input=True).strip()
    if not token_value:
        raise typer.Exit(code=2)

    token_store.set_refresh_token(token_value)
    _emit("ok", json_output=runtime.json_output)


@auth_app.command("status")
def auth_status(ctx: typer.Context) -> None:
    """Show the current token state and time until the access token expires."""
    runtime = _ctx(ctx)
    token_store = TokenStore.from_config(runtime.config)

    refresh_token = token_store.get_refresh_token()
    reauth = token_store.is_reauth_required()
    cached = token_store.get_access_cache()

    if runtime.json_output:
        payload: dict[str, Any] = {
            "refresh_token_set": refresh_token is not None,
            "reauth_required": reauth,
            "access_token_cached": cached is not None,
            "access_token_expires_at": cached[1].isoformat() if cached else None,
        }
        _emit(payload, json_output=True)
        return

    table = Table(title="Auth Status")
    table.add_column("Field")
    table.add_column("Value")

    table.add_row("Token file", str(runtime.config.token_file))
    table.add_row("Refresh token", "SET" if refresh_token else "[red]NOT SET[/red]")
    table.add_row("Reauth required", "[red]YES — run auth bootstrap[/red]" if reauth else "No")

    if cached:
        _, expires_at = cached
        now = datetime.now(UTC)
        delta = expires_at - now
        total_s = int(delta.total_seconds())
        if total_s <= 0:
            status = "[yellow]EXPIRED[/yellow]"
        else:
            h, rem = divmod(total_s, 3600)
            m, s = divmod(rem, 60)
            status = f"expires in {h}h {m}m {s}s  ({expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')})"
        table.add_row("Access token", status)
    else:
        table.add_row("Access token", "not cached (will fetch on next sync)")

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
    runtime = _ctx(ctx)
    token_store = TokenStore.from_config(runtime.config)
    refresh_token = token_store.get_refresh_token()
    if not refresh_token:
        message = "Auth token missing. Run 'lidltool auth bootstrap' first."
        if runtime.json_output:
            _emit({"ok": False, "error": message}, json_output=True)
            raise typer.Exit(code=2)
        raise typer.BadParameter(message)

    db_sessions = _create_session_factory(runtime.config)

    try:
        client = create_lidl_client(runtime.config, refresh_token, token_store=token_store)
    except LidlClientError as exc:
        LOGGER.error("Unable to initialize Lidl client: %s", exc)
        raise typer.Exit(code=1) from exc

    service = SyncService(client=client, session_factory=db_sessions, config=runtime.config)

    if runtime.json_output:
        result = service.sync(full=full)
    else:
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
        ) as p:
            task = p.add_task("Syncing receipts...", total=None)

            def on_progress(state: SyncProgress) -> None:
                p.update(
                    task,
                    description=(
                        f"pages={state.pages} seen={state.receipts_seen} "
                        f"new={state.new_receipts} items={state.new_items}"
                    ),
                )

            result = service.sync(full=full, progress_cb=on_progress)

    payload = {
        "ok": result.ok,
        "full": result.full,
        "pages": result.pages,
        "receipts_seen": result.receipts_seen,
        "new_receipts": result.new_receipts,
        "new_items": result.new_items,
        "skipped_existing": result.skipped_existing,
        "cutoff_hit": result.cutoff_hit,
        "warnings": result.warnings,
    }

    if runtime.json_output:
        _emit(payload, json_output=True)
        raise typer.Exit(code=0 if result.ok else 1)

    table = Table(title="Sync Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Full sync", str(result.full))
    table.add_row("Pages", str(result.pages))
    table.add_row("Receipts seen", str(result.receipts_seen))
    table.add_row("New receipts", str(result.new_receipts))
    table.add_row("New items", str(result.new_items))
    table.add_row("Skipped existing", str(result.skipped_existing))
    table.add_row("Cutoff reached", str(result.cutoff_hit))
    if result.warnings:
        table.add_row("Warnings", "; ".join(result.warnings))
    console.print(table)


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
    runtime = _ctx(ctx)
    target = _resolve_amazon_state_file(state_file, runtime.config)
    ok = run_amazon_headful_bootstrap(target, domain=domain)
    if runtime.json_output:
        _emit(
            {
                "ok": ok,
                "state_file": str(target),
                "domain": domain,
                "error": None if ok else "login/session capture failed",
            },
            json_output=True,
        )
        raise typer.Exit(code=0 if ok else 1)
    if not ok:
        raise typer.BadParameter(
            "Amazon login/session capture failed. Re-run and complete login + MFA before pressing Enter."
        )
    console.print(f"Amazon session stored at {target}")


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
    runtime = _ctx(ctx)
    target_state = _resolve_amazon_state_file(state_file, runtime.config)
    client = AmazonPlaywrightClient(
        state_file=target_state,
        domain=domain,
        headless=headless,
        dump_html_dir=dump_html,
    )
    db_sessions = _create_session_factory(runtime.config)
    connector = AmazonConnectorAdapter(
        client=client,
        source=source,
        store_name=store_name,
        years=years,
        max_pages_per_year=max_pages_per_year,
    )
    source_config = runtime.config.model_copy(update={"source": source})
    service = SyncService(
        client=None,
        session_factory=db_sessions,
        config=source_config,
        connector=connector,
    )

    try:
        result = service.sync(full=True)
    except AmazonClientError as exc:
        if runtime.json_output:
            _emit({"ok": False, "error": str(exc)}, json_output=True)
            raise typer.Exit(code=1) from exc
        raise typer.BadParameter(str(exc)) from exc

    payload = {
        "ok": result.ok,
        "full": result.full,
        "pages": result.pages,
        "receipts_seen": result.receipts_seen,
        "records_seen": result.receipts_seen,
        "new_receipts": result.new_receipts,
        "new_items": result.new_items,
        "skipped_existing": result.skipped_existing,
        "cutoff_hit": result.cutoff_hit,
        "warnings": result.warnings,
        "orders_fetched": result.receipts_seen,
        "state_file": str(target_state),
    }
    if runtime.json_output:
        _emit(payload, json_output=True)
        return

    table = Table(title="Amazon Sync Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Pages", str(result.pages))
    table.add_row("Orders fetched", str(result.receipts_seen))
    table.add_row("Records seen", str(result.receipts_seen))
    table.add_row("New receipts", str(result.new_receipts))
    table.add_row("New items", str(result.new_items))
    table.add_row("Skipped existing", str(result.skipped_existing))
    table.add_row("Cutoff reached", str(result.cutoff_hit))
    table.add_row("State file", str(target_state))
    if result.warnings:
        table.add_row("Warnings", "; ".join(result.warnings))
    console.print(table)


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
    runtime = _ctx(ctx)
    target = _resolve_rewe_state_file(state_file, runtime.config)
    ok = run_rewe_headful_bootstrap(target, domain=domain)
    if runtime.json_output:
        _emit(
            {
                "ok": ok,
                "state_file": str(target),
                "domain": domain,
                "error": None if ok else "login/session capture failed",
            },
            json_output=True,
        )
        raise typer.Exit(code=0 if ok else 1)
    if not ok:
        raise typer.BadParameter(
            "REWE login/session capture failed. Re-run and complete login before pressing Enter."
        )
    console.print(f"REWE session stored at {target}")


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
    runtime = _ctx(ctx)
    target_state = _resolve_rewe_state_file(state_file, runtime.config)
    client = RewePlaywrightClient(
        state_file=target_state,
        domain=domain,
        headless=headless,
        max_pages=max_pages,
    )
    db_sessions = _create_session_factory(runtime.config)
    connector = ReweConnectorAdapter(client=client, source=source, store_name=store_name)
    source_config = runtime.config.model_copy(update={"source": source})
    service = SyncService(
        client=None,
        session_factory=db_sessions,
        config=source_config,
        connector=connector,
    )
    try:
        result = service.sync(full=True)
    except ReweClientError as exc:
        if runtime.json_output:
            _emit({"ok": False, "error": str(exc)}, json_output=True)
            raise typer.Exit(code=1) from exc
        raise typer.BadParameter(str(exc)) from exc

    payload = {
        "ok": result.ok,
        "full": result.full,
        "pages": result.pages,
        "receipts_seen": result.receipts_seen,
        "new_receipts": result.new_receipts,
        "new_items": result.new_items,
        "skipped_existing": result.skipped_existing,
        "cutoff_hit": result.cutoff_hit,
        "warnings": result.warnings,
        "state_file": str(target_state),
    }
    if runtime.json_output:
        _emit(payload, json_output=True)
        return

    table = Table(title="REWE Sync Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Pages", str(result.pages))
    table.add_row("Receipts seen", str(result.receipts_seen))
    table.add_row("New receipts", str(result.new_receipts))
    table.add_row("New items", str(result.new_items))
    table.add_row("Skipped existing", str(result.skipped_existing))
    table.add_row("State file", str(target_state))
    if result.warnings:
        table.add_row("Warnings", "; ".join(result.warnings))
    console.print(table)


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
    runtime = _ctx(ctx)
    target = _resolve_kaufland_state_file(state_file, runtime.config)
    ok = run_kaufland_headful_bootstrap(target, domain=domain)
    if runtime.json_output:
        _emit(
            {
                "ok": ok,
                "state_file": str(target),
                "domain": domain,
                "error": None if ok else "login/session capture failed",
            },
            json_output=True,
        )
        raise typer.Exit(code=0 if ok else 1)
    if not ok:
        raise typer.BadParameter(
            "Kaufland login/session capture failed. Re-run and complete login before pressing Enter."
        )
    console.print(f"Kaufland session stored at {target}")


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
    runtime = _ctx(ctx)
    target_state = _resolve_kaufland_state_file(state_file, runtime.config)
    client = KauflandPlaywrightClient(
        state_file=target_state,
        domain=domain,
        headless=headless,
        max_pages=max_pages,
    )
    db_sessions = _create_session_factory(runtime.config)
    connector = KauflandConnectorAdapter(client=client, source=source, store_name=store_name)
    source_config = runtime.config.model_copy(update={"source": source})
    service = SyncService(
        client=None,
        session_factory=db_sessions,
        config=source_config,
        connector=connector,
    )
    try:
        result = service.sync(full=True)
    except KauflandClientError as exc:
        if runtime.json_output:
            _emit({"ok": False, "error": str(exc)}, json_output=True)
            raise typer.Exit(code=1) from exc
        raise typer.BadParameter(str(exc)) from exc

    payload = {
        "ok": result.ok,
        "full": result.full,
        "pages": result.pages,
        "receipts_seen": result.receipts_seen,
        "new_receipts": result.new_receipts,
        "new_items": result.new_items,
        "skipped_existing": result.skipped_existing,
        "cutoff_hit": result.cutoff_hit,
        "warnings": result.warnings,
        "state_file": str(target_state),
    }
    if runtime.json_output:
        _emit(payload, json_output=True)
        return

    table = Table(title="Kaufland Sync Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Pages", str(result.pages))
    table.add_row("Receipts seen", str(result.receipts_seen))
    table.add_row("New receipts", str(result.new_receipts))
    table.add_row("New items", str(result.new_items))
    table.add_row("Skipped existing", str(result.skipped_existing))
    table.add_row("State file", str(target_state))
    if result.warnings:
        table.add_row("Warnings", "; ".join(result.warnings))
    console.print(table)


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
    runtime = _ctx(ctx)
    target = _resolve_dm_state_file(state_file, runtime.config)
    ok = run_dm_headful_bootstrap(target, domain=domain)
    if runtime.json_output:
        _emit(
            {
                "ok": ok,
                "state_file": str(target),
                "domain": domain,
                "error": None if ok else "login/session capture failed",
            },
            json_output=True,
        )
        raise typer.Exit(code=0 if ok else 1)
    if not ok:
        raise typer.BadParameter(
            "dm login/session capture failed. Re-run and complete login before pressing Enter."
        )
    console.print(f"dm session stored at {target}")


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
    db_sessions = _create_session_factory(runtime.config)
    connector = DmConnectorAdapter(client=client, source=source, store_name=store_name)
    source_config = runtime.config.model_copy(update={"source": source})
    service = SyncService(
        client=None,
        session_factory=db_sessions,
        config=source_config,
        connector=connector,
    )
    try:
        result = service.sync(full=True)
    except DmClientError as exc:
        if runtime.json_output:
            _emit({"ok": False, "error": str(exc)}, json_output=True)
            raise typer.Exit(code=1) from exc
        raise typer.BadParameter(str(exc)) from exc

    payload = {
        "ok": result.ok,
        "full": result.full,
        "pages": result.pages,
        "receipts_seen": result.receipts_seen,
        "new_receipts": result.new_receipts,
        "new_items": result.new_items,
        "skipped_existing": result.skipped_existing,
        "cutoff_hit": result.cutoff_hit,
        "warnings": result.warnings,
        "state_file": str(target_state),
        "dump_html": str(dump_html) if dump_html is not None else None,
    }
    if runtime.json_output:
        _emit(payload, json_output=True)
        return

    table = Table(title="dm Sync Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Pages", str(result.pages))
    table.add_row("Receipts seen", str(result.receipts_seen))
    table.add_row("New receipts", str(result.new_receipts))
    table.add_row("New items", str(result.new_items))
    table.add_row("Skipped existing", str(result.skipped_existing))
    table.add_row("State file", str(target_state))
    if dump_html is not None:
        table.add_row("HTML dump dir", str(dump_html))
    if result.warnings:
        table.add_row("Warnings", "; ".join(result.warnings))
    console.print(table)


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
    runtime = _ctx(ctx)
    target = _resolve_rossmann_state_file(state_file, runtime.config)
    ok = run_rossmann_headful_bootstrap(target, domain=domain)
    if runtime.json_output:
        _emit(
            {
                "ok": ok,
                "state_file": str(target),
                "domain": domain,
                "error": None if ok else "login/session capture failed",
            },
            json_output=True,
        )
        raise typer.Exit(code=0 if ok else 1)
    if not ok:
        raise typer.BadParameter(
            "Rossmann login/session capture failed. Re-run and complete login before pressing Enter."
        )
    console.print(f"Rossmann session stored at {target}")


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
    runtime = _ctx(ctx)
    target_state = _resolve_rossmann_state_file(state_file, runtime.config)
    client = RossmannPlaywrightClient(
        state_file=target_state,
        domain=domain,
        headless=headless,
        max_pages=max_pages,
    )
    db_sessions = _create_session_factory(runtime.config)
    connector = RossmannConnectorAdapter(client=client, source=source, store_name=store_name)
    source_config = runtime.config.model_copy(update={"source": source})
    service = SyncService(
        client=None,
        session_factory=db_sessions,
        config=source_config,
        connector=connector,
    )
    try:
        result = service.sync(full=True)
    except RossmannClientError as exc:
        if runtime.json_output:
            _emit({"ok": False, "error": str(exc)}, json_output=True)
            raise typer.Exit(code=1) from exc
        raise typer.BadParameter(str(exc)) from exc

    payload = {
        "ok": result.ok,
        "full": result.full,
        "pages": result.pages,
        "receipts_seen": result.receipts_seen,
        "new_receipts": result.new_receipts,
        "new_items": result.new_items,
        "skipped_existing": result.skipped_existing,
        "cutoff_hit": result.cutoff_hit,
        "warnings": result.warnings,
        "state_file": str(target_state),
    }
    if runtime.json_output:
        _emit(payload, json_output=True)
        return

    table = Table(title="Rossmann Sync Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Pages", str(result.pages))
    table.add_row("Receipts seen", str(result.receipts_seen))
    table.add_row("New receipts", str(result.new_receipts))
    table.add_row("New items", str(result.new_items))
    table.add_row("Skipped existing", str(result.skipped_existing))
    table.add_row("State file", str(target_state))
    if result.warnings:
        table.add_row("Warnings", "; ".join(result.warnings))
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
