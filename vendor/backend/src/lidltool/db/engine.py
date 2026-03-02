from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from lidltool.db.models import Base

_MIGRATED_HEAD_URLS: set[str] = set()
_MIGRATION_LOCK = Lock()


def _ensure_parent_dir_for_sqlite(db_url: str) -> None:
    if db_url.startswith("sqlite:///"):
        db_path = Path(db_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)


def create_engine_for_url(db_url: str) -> Engine:
    _ensure_parent_dir_for_sqlite(db_url)
    engine = create_engine(db_url, future=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _: object) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

    return engine


def migrate_db(db_url: str, *, revision: str = "head") -> None:
    if revision == "head":
        with _MIGRATION_LOCK:
            if db_url in _MIGRATED_HEAD_URLS:
                return
    _ensure_parent_dir_for_sqlite(db_url)
    repo_root = Path(__file__).resolve().parents[3]
    migrations_path = Path(__file__).resolve().parent / "migrations"
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


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


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
