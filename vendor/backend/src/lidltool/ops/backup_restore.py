from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lidltool.config import AppConfig, database_url
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import RecoveryDrillEvidence


@dataclass(slots=True)
class BackupResult:
    provider: str
    db_artifact: Path
    token_artifact: Path | None
    documents_artifact: Path | None


@dataclass(slots=True)
class DrillResult:
    drill_name: str
    provider: str
    backup_result: BackupResult
    restore_probe_path: Path
    elapsed_ms: int
    rto_target_ms: int
    rpo_target_minutes: int
    rto_target_met: bool
    rpo_target_met: bool
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "drill_name": self.drill_name,
            "provider": self.provider,
            "backup_result": {
                "db_artifact": str(self.backup_result.db_artifact),
                "token_artifact": (
                    str(self.backup_result.token_artifact)
                    if self.backup_result.token_artifact
                    else None
                ),
                "documents_artifact": (
                    str(self.backup_result.documents_artifact)
                    if self.backup_result.documents_artifact
                    else None
                ),
            },
            "restore_probe_path": str(self.restore_probe_path),
            "elapsed_ms": self.elapsed_ms,
            "rto_target_ms": self.rto_target_ms,
            "rpo_target_minutes": self.rpo_target_minutes,
            "rto_target_met": self.rto_target_met,
            "rpo_target_met": self.rpo_target_met,
            "metadata": self.metadata,
        }


def _provider_from_url(db_url: str) -> str:
    return db_url.split(":", 1)[0].lower()


def _sqlite_file_from_url(db_url: str) -> Path:
    if not db_url.startswith("sqlite:///"):
        raise ValueError(f"unsupported sqlite url: {db_url}")
    return Path(db_url.replace("sqlite:///", "")).expanduser().resolve()


def backup_database(
    config: AppConfig, output_dir: Path, *, include_documents: bool = True
) -> BackupResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    db_url = database_url(config)
    provider = _provider_from_url(db_url)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")

    if provider != "sqlite":
        raise RuntimeError(
            f"provider '{provider}' backup adapter not implemented yet; use sqlite or add adapter"
        )
    source_db = _sqlite_file_from_url(db_url)
    db_artifact = output_dir / f"db-backup-{stamp}.sqlite"
    shutil.copy2(source_db, db_artifact)

    token_artifact: Path | None = None
    if config.token_file.exists():
        token_artifact = output_dir / f"token-backup-{stamp}.json"
        shutil.copy2(config.token_file, token_artifact)

    documents_artifact: Path | None = None
    if include_documents and config.document_storage_path.exists():
        documents_artifact = output_dir / f"documents-backup-{stamp}"
        if documents_artifact.exists():
            shutil.rmtree(documents_artifact)
        shutil.copytree(config.document_storage_path, documents_artifact)

    return BackupResult(
        provider=provider,
        db_artifact=db_artifact,
        token_artifact=token_artifact,
        documents_artifact=documents_artifact,
    )


def restore_database(
    *,
    provider: str,
    db_artifact: Path,
    restore_target: Path,
) -> Path:
    restore_target.parent.mkdir(parents=True, exist_ok=True)
    if provider != "sqlite":
        raise RuntimeError(
            f"provider '{provider}' restore adapter not implemented yet; use sqlite or add adapter"
        )
    shutil.copy2(db_artifact, restore_target)
    return restore_target


def _persist_drill_evidence(config: AppConfig, drill: DrillResult, artifact_path: Path) -> None:
    db_url = database_url(config)
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    sessions = session_factory(engine)
    with session_scope(sessions) as session:
        session.add(
            RecoveryDrillEvidence(
                drill_name=drill.drill_name,
                provider=drill.provider,
                artifact_path=str(artifact_path),
                elapsed_ms=drill.elapsed_ms,
                rto_target_ms=drill.rto_target_ms,
                rpo_target_minutes=drill.rpo_target_minutes,
                rto_target_met=drill.rto_target_met,
                rpo_target_met=drill.rpo_target_met,
                metadata_json=drill.metadata,
            )
        )


def run_backup_restore_drill(
    config: AppConfig,
    *,
    output_dir: Path,
    drill_name: str = "backup_restore_drill",
    rto_target_ms: int = 30_000,
    rpo_target_minutes: int = 60,
) -> DrillResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = output_dir / "backup"
    backup_result = backup_database(config, backup_dir)

    restore_probe = output_dir / "restore_probe.sqlite"
    started_at = time.monotonic()
    restored = restore_database(
        provider=backup_result.provider,
        db_artifact=backup_result.db_artifact,
        restore_target=restore_probe,
    )
    elapsed_ms = int((time.monotonic() - started_at) * 1000)

    db_mtime = datetime.fromtimestamp(backup_result.db_artifact.stat().st_mtime, tz=UTC)
    backup_age_minutes = max(int((datetime.now(tz=UTC) - db_mtime).total_seconds() / 60), 0)
    rpo_met = backup_age_minutes <= rpo_target_minutes
    rto_met = elapsed_ms <= rto_target_ms

    metadata = {
        "backup_age_minutes": backup_age_minutes,
        "restored_exists": restored.exists(),
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }
    result = DrillResult(
        drill_name=drill_name,
        provider=backup_result.provider,
        backup_result=backup_result,
        restore_probe_path=restored,
        elapsed_ms=elapsed_ms,
        rto_target_ms=rto_target_ms,
        rpo_target_minutes=rpo_target_minutes,
        rto_target_met=rto_met,
        rpo_target_met=rpo_met,
        metadata=metadata,
    )

    report_path = output_dir / "backup_restore_drill_result.json"
    report_path.write_text(json.dumps(result.as_dict(), indent=2), encoding="utf-8")
    _persist_drill_evidence(config, result, report_path)
    return result
