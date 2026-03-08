import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const backendDir = resolve(desktopDir, "vendor", "backend");
const httpServerPath = resolve(backendDir, "src", "lidltool", "api", "http_server.py");
const backupRestorePath = resolve(backendDir, "src", "lidltool", "ops", "backup_restore.py");

function replaceOnce(source, searchValue, replaceValue, label) {
  if (!source.includes(searchValue)) {
    throw new Error(`Could not patch ${label}: expected snippet not found.`);
  }
  return source.replace(searchValue, replaceValue);
}

function patchBackupRestore(current) {
  let next = current;

  if (!next.includes("include_documents: bool = True")) {
    next = replaceOnce(
      next,
      "def backup_database(config: AppConfig, output_dir: Path) -> BackupResult:\n",
      "def backup_database(\n    config: AppConfig, output_dir: Path, *, include_documents: bool = True\n) -> BackupResult:\n",
      backupRestorePath
    );
  }

  next = replaceOnce(
    next,
    "    if config.document_storage_path.exists():\n",
    "    if include_documents and config.document_storage_path.exists():\n",
    backupRestorePath
  );

  return next;
}

function patchHttpServer(current) {
  let next = current;

  if (!next.includes("    export_receipts,\n")) {
    next = replaceOnce(
      next,
      "    dashboard_trends,\n",
      "    dashboard_trends,\n    export_receipts,\n",
      httpServerPath
    );
  }

  if (!next.includes("from lidltool.ops import backup_database")) {
    next = replaceOnce(
      next,
      "from lidltool.ingest.overrides import OverrideService\n",
      "from lidltool.ingest.overrides import OverrideService\nfrom lidltool.ops import backup_database\n",
      httpServerPath
    );
  }

  if (!next.includes("class SystemBackupRequest(BaseModel):")) {
    next = replaceOnce(
      next,
      "class TransactionItemSharingRequest(BaseModel):\n    family_shared: bool\n\n\nUploadFormFile = Annotated[UploadFile, File(...)]\n",
      `class TransactionItemSharingRequest(BaseModel):\n    family_shared: bool\n\n\nclass SystemBackupRequest(BaseModel):\n    output_dir: str | None = None\n    include_documents: bool = True\n    include_export_json: bool = True\n\n\nUploadFormFile = Annotated[UploadFile, File(...)]\n`,
      httpServerPath
    );
  }

  if (!next.includes('@app.post("/api/v1/system/backup")')) {
    next = replaceOnce(
      next,
      '    @app.post("/api/v1/documents/upload")\n',
      `    @app.post("/api/v1/system/backup")\n    def run_system_backup(\n        request: Request,\n        payload: SystemBackupRequest,\n        db: str | None = None,\n        config: str | None = None,\n    ) -> Any:\n        try:\n            context = _resolve_request_context(request, db=db, config_path=config)\n            app_config = context.config\n            warnings = _apply_auth_guard(app_config, request=request)\n            with session_scope(context.sessions) as session:\n                current_user = _resolve_request_user(\n                    request=request, session=session, config=app_config\n                )\n                _require_admin(current_user)\n\n                timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")\n                if payload.output_dir and payload.output_dir.strip():\n                    output_dir = Path(payload.output_dir.strip()).expanduser().resolve()\n                else:\n                    output_dir = (app_config.config_dir / "desktop-backups" / f"backup-{timestamp}").resolve()\n\n                output_dir.mkdir(parents=True, exist_ok=True)\n                if any(output_dir.iterdir()):\n                    raise RuntimeError(f"backup output directory must be empty: {output_dir}")\n\n                backup_result = backup_database(\n                    app_config, output_dir, include_documents=payload.include_documents\n                )\n                copied: list[str] = [str(backup_result.db_artifact)]\n                skipped: list[str] = []\n\n                token_artifact: str | None = None\n                if backup_result.token_artifact:\n                    token_artifact = str(backup_result.token_artifact)\n                    copied.append(token_artifact)\n                else:\n                    skipped.append("token file not found")\n\n                documents_artifact: str | None = None\n                if payload.include_documents:\n                    if backup_result.documents_artifact:\n                        documents_artifact = str(backup_result.documents_artifact)\n                        copied.append(documents_artifact)\n                    else:\n                        skipped.append("documents directory not found")\n                else:\n                    skipped.append("documents excluded by request")\n\n                credential_key_artifact: str | None = None\n                credential_key = (\n                    os.getenv("LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY")\n                    or app_config.credential_encryption_key\n                )\n                if credential_key and credential_key.strip():\n                    key_artifact = output_dir / "credential_encryption_key.txt"\n                    key_artifact.write_text(f"{credential_key.strip()}\\n", encoding="utf-8")\n                    credential_key_artifact = str(key_artifact)\n                    copied.append(credential_key_artifact)\n                else:\n                    skipped.append("credential encryption key not available")\n\n                export_artifact: str | None = None\n                export_records: int | None = None\n                if payload.include_export_json:\n                    export_payload = export_receipts(session)\n                    export_file = output_dir / "receipts-export.json"\n                    export_file.write_text(\n                        json.dumps(export_payload, indent=2, default=str), encoding="utf-8"\n                    )\n                    export_artifact = str(export_file)\n                    export_records = len(export_payload)\n                    copied.append(export_artifact)\n\n                manifest_path = output_dir / "backup-manifest.json"\n                manifest_payload = {\n                    "created_at": datetime.now(tz=UTC).isoformat(),\n                    "requested_by_user_id": current_user.user_id,\n                    "provider": backup_result.provider,\n                    "output_dir": str(output_dir),\n                    "db_artifact": str(backup_result.db_artifact),\n                    "token_artifact": token_artifact,\n                    "documents_artifact": documents_artifact,\n                    "credential_key_artifact": credential_key_artifact,\n                    "export_artifact": export_artifact,\n                    "export_records": export_records,\n                    "include_documents": payload.include_documents,\n                    "include_export_json": payload.include_export_json,\n                    "copied": copied,\n                    "skipped": skipped,\n                }\n                manifest_path.write_text(\n                    json.dumps(manifest_payload, indent=2), encoding="utf-8"\n                )\n                copied.append(str(manifest_path))\n\n                result = {\n                    "provider": backup_result.provider,\n                    "output_dir": str(output_dir),\n                    "db_artifact": str(backup_result.db_artifact),\n                    "token_artifact": token_artifact,\n                    "documents_artifact": documents_artifact,\n                    "credential_key_artifact": credential_key_artifact,\n                    "export_artifact": export_artifact,\n                    "export_records": export_records,\n                    "manifest_path": str(manifest_path),\n                    "copied": copied,\n                    "skipped": skipped,\n                }\n            return _response(True, result=result, warnings=warnings, error=None)\n        except Exception as exc:  # noqa: BLE001\n            return _error_response(exc)\n\n    @app.post("/api/v1/documents/upload")\n`,
      httpServerPath
    );
  }

  return next;
}

if (!existsSync(httpServerPath) || !existsSync(backupRestorePath)) {
  throw new Error(`Vendored backend sources not found under ${backendDir}. Run 'npm run vendor:sync' first.`);
}

const patchedBackupRestore = patchBackupRestore(readFileSync(backupRestorePath, "utf-8"));
writeFileSync(backupRestorePath, patchedBackupRestore, "utf-8");

const patchedHttpServer = patchHttpServer(readFileSync(httpServerPath, "utf-8"));
writeFileSync(httpServerPath, patchedHttpServer, "utf-8");

console.log("Patched vendored backend with desktop backup endpoint support.");
