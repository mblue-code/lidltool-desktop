from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from lidltool.db.models import Base

_MIGRATED_HEAD_URLS: set[str] = set()
_MIGRATION_LOCK = Lock()
_SQLITE_MIGRATION_RETRY_TIMEOUT_S = 60.0
_SQLITE_MIGRATION_RETRY_DELAY_S = 0.25
_LEGACY_CONNECTOR_LIFECYCLE_REVISION = "0015_connector_lifecycle_state"
_LEGACY_REBASE_REVISION = "0014_offer_platform_foundation"
_LEGACY_CONNECTOR_TARGET_REVISION = "0020_connector_lifecycle_install_origin"
_LEGACY_PRE_CONNECTOR_HEAD = "0018_monthly_budget_cashflow"


def _ensure_parent_dir_for_sqlite(db_url: str) -> None:
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)


def _sqlite_db_path(db_url: str) -> Path | None:
    if not db_url.startswith("sqlite:///"):
        return None
    return Path(db_url.replace("sqlite:///", ""))


@contextmanager
def _migration_guard(db_url: str) -> Iterator[None]:
    sqlite_path = _sqlite_db_path(db_url)
    if sqlite_path is None:
        yield
        return
    lock_path = sqlite_path.parent / ".alembic-migrate.lock"
    with lock_path.open("w", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def create_engine_for_url(db_url: str) -> Engine:
    _ensure_parent_dir_for_sqlite(db_url)
    engine = create_engine(db_url, future=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _: object) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()

    return engine


def _resolve_backend_repo_root() -> Path:
    configured = os.getenv("LIDLTOOL_REPO_ROOT", "").strip()
    candidate_paths: list[Path] = []
    if configured:
        candidate_paths.append(Path(configured).expanduser().resolve())

    module_path = Path(__file__).resolve()
    candidate_paths.extend(module_path.parents[:6])

    for candidate in candidate_paths:
        if (candidate / "alembic.ini").is_file():
            return candidate

    return module_path.parents[3]


def _resolve_migrations_path(repo_root: Path) -> Path:
    source_migrations = repo_root / "src" / "lidltool" / "db" / "migrations"
    if source_migrations.is_dir():
        return source_migrations
    return Path(__file__).resolve().parent / "migrations"


def migrate_db(db_url: str, *, revision: str = "head") -> None:
    if revision == "head":
        with _MIGRATION_LOCK:
            if db_url in _MIGRATED_HEAD_URLS:
                return
    deadline = time.monotonic() + _SQLITE_MIGRATION_RETRY_TIMEOUT_S
    while True:
        try:
            with _migration_guard(db_url):
                if revision == "head":
                    with _MIGRATION_LOCK:
                        if db_url in _MIGRATED_HEAD_URLS:
                            return
                _ensure_parent_dir_for_sqlite(db_url)
                repo_root = _resolve_backend_repo_root()
                migrations_path = _resolve_migrations_path(repo_root)
                config = Config(str(repo_root / "alembic.ini"))
                config.set_main_option("script_location", str(migrations_path))
                config.set_main_option("sqlalchemy.url", db_url)
                if revision == "head":
                    head_revision = ScriptDirectory.from_config(config).get_current_head()
                    if head_revision is None:
                        raise RuntimeError("alembic script directory has no head revision")
                    inspector_engine = create_engine_for_url(db_url)
                    try:
                        with inspector_engine.connect() as connection:
                            table_names = set(inspect(connection).get_table_names())
                            existing_revisions: set[str] = set()
                            if "alembic_version" in table_names:
                                rows = connection.execute(text("SELECT version_num FROM alembic_version"))
                                existing_revisions = {str(row[0]) for row in rows}
                    finally:
                        inspector_engine.dispose()
                    if _remediate_legacy_connector_revision(
                        config=config,
                        db_url=db_url,
                        table_names=table_names,
                        existing_revisions=existing_revisions,
                    ):
                        inspector_engine = create_engine_for_url(db_url)
                        try:
                            with inspector_engine.connect() as connection:
                                table_names = set(inspect(connection).get_table_names())
                                rows = connection.execute(text("SELECT version_num FROM alembic_version"))
                                existing_revisions = {str(row[0]) for row in rows}
                        finally:
                            inspector_engine.dispose()
                    metadata_tables = set(Base.metadata.tables.keys())
                    # Tables must all exist AND have the same columns as the model (catches column additions).
                    tables_present = metadata_tables.issubset(table_names)
                    schema_looks_current = False
                    if tables_present:
                        insp_engine = create_engine_for_url(db_url)
                        try:
                            with insp_engine.connect() as _conn:
                                _inspector = inspect(_conn)
                                schema_looks_current = all(
                                    {c["name"] for c in _inspector.get_columns(tbl)}
                                    >= {col.name for col in Base.metadata.tables[tbl].columns}
                                    for tbl in metadata_tables
                                )
                        finally:
                            insp_engine.dispose()
                    needs_stamp = schema_looks_current and (
                        "alembic_version" not in table_names or existing_revisions != {head_revision}
                    )
                    if needs_stamp:
                        if "alembic_version" in table_names and existing_revisions != {head_revision}:
                            reset_engine = create_engine_for_url(db_url)
                            try:
                                with reset_engine.begin() as connection:
                                    connection.execute(text("DELETE FROM alembic_version"))
                            finally:
                                reset_engine.dispose()
                        command.stamp(config, head_revision)
                command.upgrade(config, revision)
                if revision == "head":
                    with _MIGRATION_LOCK:
                        _MIGRATED_HEAD_URLS.add(db_url)
                return
        except (OperationalError, CommandError) as exc:
            if _should_retry_concurrent_sqlite_migration(
                exc=exc,
                db_url=db_url,
                revision=revision,
                deadline=deadline,
            ):
                time.sleep(_SQLITE_MIGRATION_RETRY_DELAY_S)
                continue
            raise


def _remediate_legacy_connector_revision(
    *,
    config: Config,
    db_url: str,
    table_names: set[str],
    existing_revisions: set[str],
) -> bool:
    if existing_revisions != {_LEGACY_CONNECTOR_LIFECYCLE_REVISION}:
        return False

    reset_engine = create_engine_for_url(db_url)
    try:
        with reset_engine.begin() as connection:
            connection.execute(text("DELETE FROM alembic_version"))
    finally:
        reset_engine.dispose()

    command.stamp(config, _LEGACY_REBASE_REVISION)
    command.upgrade(config, _LEGACY_PRE_CONNECTOR_HEAD)
    _ensure_connector_state_schema(db_url, table_names)
    command.stamp(config, _LEGACY_CONNECTOR_TARGET_REVISION)
    return True


def _ensure_connector_state_schema(db_url: str, table_names: set[str]) -> None:
    engine = create_engine_for_url(db_url)
    try:
        with engine.begin() as connection:
            metadata = Base.metadata
            inspector = inspect(connection)
            existing_tables = set(inspector.get_table_names()) | set(table_names)

            connector_lifecycle = metadata.tables["connector_lifecycle_state"]
            connector_config = metadata.tables["connector_config_state"]

            if "connector_lifecycle_state" not in existing_tables:
                connector_lifecycle.create(bind=connection, checkfirst=True)
            if "connector_config_state" not in existing_tables:
                connector_config.create(bind=connection, checkfirst=True)

            inspector = inspect(connection)
            lifecycle_columns = {column["name"] for column in inspector.get_columns("connector_lifecycle_state")}
            if "install_origin" not in lifecycle_columns:
                connection.execute(text("ALTER TABLE connector_lifecycle_state ADD COLUMN install_origin VARCHAR"))

            existing_indexes = {index["name"] for index in inspector.get_indexes("connector_lifecycle_state")}
            for index in connector_lifecycle.indexes:
                if index.name and index.name not in existing_indexes:
                    index.create(bind=connection, checkfirst=True)

            existing_config_indexes = {index["name"] for index in inspector.get_indexes("connector_config_state")}
            for index in connector_config.indexes:
                if index.name and index.name not in existing_config_indexes:
                    index.create(bind=connection, checkfirst=True)
    finally:
        engine.dispose()


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    from lidltool.analytics.item_categorizer import ensure_category_taxonomy
    from lidltool.analytics.finance_taxonomy import ensure_finance_taxonomy
    from lidltool.analytics.transaction_categorizer import register_transaction_categorizer_events

    with Session(engine) as session:
        ensure_category_taxonomy(session)
        ensure_finance_taxonomy(session)
        session.commit()
    register_transaction_categorizer_events()


def _looks_like_concurrent_sqlite_migration(exc: OperationalError) -> bool:
    message = str(exc).casefold()
    return "already exists" in message or "duplicate column name" in message


def _should_retry_concurrent_sqlite_migration(
    *,
    exc: Exception,
    db_url: str,
    revision: str,
    deadline: float,
) -> bool:
    if revision != "head" or not db_url.startswith("sqlite:///") or time.monotonic() >= deadline:
        return False
    message = str(exc).casefold()
    if isinstance(exc, OperationalError):
        return _looks_like_concurrent_sqlite_migration(exc)
    return (
        "expected to match one row when updating" in message
        or "database is locked" in message
    )


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
