import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(process.env.LIDLTOOL_DESKTOP_DIR?.trim() || resolve(__dirname, ".."));
const backendDir = resolve(desktopDir, "vendor", "backend");
const httpServerPath = resolve(backendDir, "src", "lidltool", "api", "http_server.py");
const routeAuthPath = resolve(backendDir, "src", "lidltool", "api", "route_auth.py");
const backupRestorePath = resolve(backendDir, "src", "lidltool", "ops", "backup_restore.py");
const authBrowserRuntimePath = resolve(backendDir, "src", "lidltool", "connectors", "auth", "browser_runtime.py");
const lifecyclePath = resolve(backendDir, "src", "lidltool", "connectors", "lifecycle.py");
const registryPath = resolve(backendDir, "src", "lidltool", "connectors", "registry.py");
const runtimeExecutionPath = resolve(backendDir, "src", "lidltool", "connectors", "runtime", "execution.py");
const runtimeRunnerPath = resolve(backendDir, "src", "lidltool", "connectors", "runtime", "runner.py");
const cliPath = resolve(backendDir, "src", "lidltool", "cli.py");

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

  if (!next.includes("    if include_documents and config.document_storage_path.exists():\n")) {
    next = replaceOnce(
      next,
      "    if config.document_storage_path.exists():\n",
      "    if include_documents and config.document_storage_path.exists():\n",
      backupRestorePath
    );
  }

  return next;
}

function patchAuthBrowserRuntime(current) {
  let next = current;

  if (!next.includes("from tempfile import TemporaryDirectory\n")) {
    next = replaceOnce(
      next,
      "import shutil\nimport sys\n",
      "import shutil\nimport sys\nfrom tempfile import TemporaryDirectory\n",
      authBrowserRuntimePath
    );
  }

  if (!next.includes("with TemporaryDirectory(prefix=\"lidltool-auth-browser-\") as user_data_dir:\n")) {
    next = replaceOnce(
      next,
      "        with sync_playwright() as playwright:\n            browser = _launch_auth_browser(playwright=playwright, headless=headless, environment=environment)\n            context = browser.new_context()\n            captured_url: str | None = None\n            captured_error: str | None = None\n\n            def capture(url: str | None) -> None:\n                nonlocal captured_url\n                matched = _match_callback_candidate(\n                    str(url or \"\").strip(),\n                    callback_prefixes,\n                )\n                if matched is not None:\n                    captured_url = matched\n\n            def attach_page(page: Any) -> None:\n                page.on(\"framenavigated\", lambda frame: capture(frame.url))\n\n            context.on(\"request\", lambda req: capture(req.url))\n            context.on(\"requestfailed\", lambda req: capture(req.url))\n            context.on(\"response\", lambda res: capture(res.headers.get(\"location\")))\n            context.on(\"page\", attach_page)\n\n            page = context.new_page()\n            attach_page(page)\n\n            try:\n                page.goto(request.plan.start_url, wait_until=request.plan.wait_until)\n            except PlaywrightError as exc:\n                context.close()\n                browser.close()\n                raise RuntimeError(f\"browser auth session failed to open login page: {exc}\") from exc\n\n            print(\"Browser open: complete login in the shared auth session window.\", flush=True)\n            deadline = datetime.now(tz=UTC).timestamp() + request.plan.timeout_seconds\n            while captured_url is None and captured_error is None:\n                captured_url = _discover_callback_candidate(\n                    context=context,\n                    callback_prefixes=callback_prefixes,\n                )\n                if captured_url is not None:\n                    break\n                if datetime.now(tz=UTC).timestamp() >= deadline:\n                    break\n                try:\n                    page.wait_for_timeout(500)\n                except PlaywrightError as exc:\n                    captured_url = _discover_callback_candidate(\n                        context=context,\n                        callback_prefixes=callback_prefixes,\n                    )\n                    if captured_url is not None:\n                        break\n                    captured_error = str(exc)\n                    break\n\n            try:\n                context.close()\n            finally:\n                browser.close()\n",
      "        with sync_playwright() as playwright:\n            with TemporaryDirectory(prefix=\"lidltool-auth-browser-\") as user_data_dir:\n                context = launch_playwright_chromium_persistent_context(\n                    playwright=playwright,\n                    user_data_dir=user_data_dir,\n                    headless=headless,\n                    environment=environment,\n                )\n                captured_url: str | None = None\n                captured_error: str | None = None\n\n                def capture(url: str | None) -> None:\n                    nonlocal captured_url\n                    matched = _match_callback_candidate(\n                        str(url or \"\").strip(),\n                        callback_prefixes,\n                    )\n                    if matched is not None:\n                        captured_url = matched\n\n                def attach_page(page: Any) -> None:\n                    page.on(\"framenavigated\", lambda frame: capture(frame.url))\n\n                context.on(\"request\", lambda req: capture(req.url))\n                context.on(\"requestfailed\", lambda req: capture(req.url))\n                context.on(\"response\", lambda res: capture(res.headers.get(\"location\")))\n                context.on(\"page\", attach_page)\n\n                page = context.pages[0] if getattr(context, \"pages\", None) else context.new_page()\n                attach_page(page)\n\n                try:\n                    page.goto(request.plan.start_url, wait_until=request.plan.wait_until)\n                except PlaywrightError as exc:\n                    context.close()\n                    raise RuntimeError(f\"browser auth session failed to open login page: {exc}\") from exc\n\n                print(\"Browser open: complete login in the shared auth session window.\", flush=True)\n                deadline = datetime.now(tz=UTC).timestamp() + request.plan.timeout_seconds\n                while captured_url is None and captured_error is None:\n                    captured_url = _discover_callback_candidate(\n                        context=context,\n                        callback_prefixes=callback_prefixes,\n                    )\n                    if captured_url is not None:\n                        break\n                    if datetime.now(tz=UTC).timestamp() >= deadline:\n                        break\n                    try:\n                        page.wait_for_timeout(500)\n                    except PlaywrightError as exc:\n                        captured_url = _discover_callback_candidate(\n                            context=context,\n                            callback_prefixes=callback_prefixes,\n                        )\n                        if captured_url is not None:\n                            break\n                        captured_error = str(exc)\n                        break\n\n                context.close()\n",
      authBrowserRuntimePath
    );
  }

  if (!next.includes("callback_prefixes = tuple(request.plan.callback_url_prefixes)\n")) {
    next = replaceOnce(
      next,
      "    ) -> str:\n        mode = self._resolve_mode(env=environment, interactive=request.plan.interactive)\n",
      "    ) -> str:\n        callback_prefixes = tuple(request.plan.callback_url_prefixes)\n        mode = self._resolve_mode(env=environment, interactive=request.plan.interactive)\n",
      authBrowserRuntimePath
    );
  }

  if (!next.includes("matched = _match_callback_candidate(")) {
    next = replaceOnce(
      next,
      '            def capture(url: str | None) -> None:\n                nonlocal captured_url\n                candidate = str(url or "").strip()\n                if not candidate:\n                    return\n                if any(candidate.startswith(prefix) for prefix in request.plan.callback_url_prefixes):\n                    captured_url = candidate\n',
      '            def capture(url: str | None) -> None:\n                nonlocal captured_url\n                matched = _match_callback_candidate(\n                    str(url or "").strip(),\n                    callback_prefixes,\n                )\n                if matched is not None:\n                    captured_url = matched\n',
      authBrowserRuntimePath
    );
  }

  if (!next.includes('"requestfailed"')) {
    next = replaceOnce(
      next,
      '            context.on("request", lambda req: capture(req.url))\n            context.on("response", lambda res: capture(res.headers.get("location")))\n',
      '            context.on("request", lambda req: capture(req.url))\n            context.on("requestfailed", lambda req: capture(req.url))\n            context.on("response", lambda res: capture(res.headers.get("location")))\n',
      authBrowserRuntimePath
    );
  }

  if (!next.includes("captured_url = _discover_callback_candidate(")) {
    next = replaceOnce(
      next,
      "            print(\"Browser open: complete login in the shared auth session window.\", flush=True)\n            deadline = datetime.now(tz=UTC).timestamp() + request.plan.timeout_seconds\n            while captured_url is None and captured_error is None:\n                if datetime.now(tz=UTC).timestamp() >= deadline:\n                    break\n                try:\n                    page.wait_for_timeout(500)\n                except PlaywrightError as exc:\n                    captured_error = str(exc)\n                    break\n",
      "            print(\"Browser open: complete login in the shared auth session window.\", flush=True)\n            deadline = datetime.now(tz=UTC).timestamp() + request.plan.timeout_seconds\n            while captured_url is None and captured_error is None:\n                captured_url = _discover_callback_candidate(\n                    context=context,\n                    callback_prefixes=callback_prefixes,\n                )\n                if captured_url is not None:\n                    break\n                if datetime.now(tz=UTC).timestamp() >= deadline:\n                    break\n                try:\n                    page.wait_for_timeout(500)\n                except PlaywrightError as exc:\n                    captured_url = _discover_callback_candidate(\n                        context=context,\n                        callback_prefixes=callback_prefixes,\n                    )\n                    if captured_url is not None:\n                        break\n                    captured_error = str(exc)\n                    break\n",
      authBrowserRuntimePath
    );
  }

  if (!next.includes("def _discover_callback_candidate(")) {
    next = replaceOnce(
      next,
      "        if interactive:\n            return \"headless_capture_only\"\n        return \"headless_capture_only\"\n\n\ndef _launch_auth_browser(\n",
      "        if interactive:\n            return \"headless_capture_only\"\n        return \"headless_capture_only\"\n\n\ndef _discover_callback_candidate(\n    *,\n    context: Any,\n    callback_prefixes: tuple[str, ...],\n) -> str | None:\n    for page in list(getattr(context, \"pages\", ())):\n        candidate = _discover_callback_candidate_from_page(\n            page=page,\n            callback_prefixes=callback_prefixes,\n        )\n        if candidate is not None:\n            return candidate\n    return None\n\n\ndef _discover_callback_candidate_from_page(\n    *,\n    page: Any,\n    callback_prefixes: tuple[str, ...],\n) -> str | None:\n    try:\n        snapshot = page.evaluate(\n            \"\"\"(prefixes) => {\n                const candidates = [];\n                const push = (value) => {\n                    if (typeof value === \\\"string\\\" && value.trim()) {\n                        candidates.push(value.trim());\n                    }\n                };\n\n                push(window.location?.href ?? \\\"\\\");\n\n                for (const element of document.querySelectorAll(\\\"a[href], area[href]\\\")) {\n                    push(element.getAttribute(\\\"href\\\"));\n                }\n                for (const element of document.querySelectorAll(\\\"form[action]\\\")) {\n                    push(element.getAttribute(\\\"action\\\"));\n                }\n                for (const element of document.querySelectorAll(\\\"iframe[src]\\\")) {\n                    push(element.getAttribute(\\\"src\\\"));\n                }\n                for (const element of document.querySelectorAll(\\\"meta[http-equiv]\\\")) {\n                    const httpEquiv = (element.getAttribute(\\\"http-equiv\\\") || \\\"\\\").toLowerCase();\n                    if (httpEquiv === \\\"refresh\\\") {\n                        push(element.getAttribute(\\\"content\\\"));\n                    }\n                }\n\n                const matches = [];\n                for (const value of candidates) {\n                    for (const prefix of prefixes) {\n                        const index = value.indexOf(prefix);\n                        if (index >= 0) {\n                            matches.push(value.slice(index));\n                        }\n                    }\n                }\n\n                return {\n                    matches,\n                    text: document.body?.innerText ?? \\\"\\\",\n                };\n            }\"\"\",\n            list(callback_prefixes),\n        )\n    except PlaywrightError:\n        return None\n\n    if not isinstance(snapshot, dict):\n        return None\n\n    for raw_value in snapshot.get(\"matches\", ()):\n        matched = _match_callback_candidate(str(raw_value or \"\").strip(), callback_prefixes)\n        if matched is not None:\n            return matched\n\n    body_text = str(snapshot.get(\"text\") or \"\")\n    return _match_callback_candidate(body_text, callback_prefixes)\n\n\ndef _match_callback_candidate(candidate: str, callback_prefixes: tuple[str, ...]) -> str | None:\n    raw = candidate.strip()\n    if not raw:\n        return None\n\n    for prefix in callback_prefixes:\n        index = raw.find(prefix)\n        if index < 0:\n            continue\n        matched = raw[index:]\n        for delimiter in ('\\\"', \"'\", \" \", \"\\\\n\", \"\\\\r\", \"\\\\t\", \"<\", \">\", \")\", \"]\"):\n            delimiter_index = matched.find(delimiter)\n            if delimiter_index > 0:\n                matched = matched[:delimiter_index]\n        return matched.rstrip(\".,;\")\n    return None\n\n\ndef _launch_auth_browser(\n",
      authBrowserRuntimePath
    );
  }

  if (
    next.includes("def capture(url: str | None) -> None:\n                    nonlocal captured_url\n") &&
    !next.includes("nonlocal captured_url, saw_navigation_away\n")
  ) {
    next = replaceOnce(
      next,
      "                def capture(url: str | None) -> None:\n                    nonlocal captured_url\n                    matched = _match_callback_candidate(\n                        str(url or \"\").strip(),\n                        callback_prefixes,\n                    )\n",
      "                def capture(url: str | None) -> None:\n                    nonlocal captured_url, saw_navigation_away\n                    saw_navigation_away = _record_navigation_away(\n                        candidate=url,\n                        start_url=normalized_start_url,\n                        saw_navigation_away=saw_navigation_away,\n                    )\n                    matched = _match_callback_candidate(\n                        str(url or \"\").strip(),\n                        callback_prefixes,\n                    )\n",
      authBrowserRuntimePath
    );
  }

  if (next.includes("def capture(url: str | None) -> None:\n                    nonlocal captured_url, saw_navigation_away\n")) {
    next = replaceOnce(
      next,
      "                def capture(url: str | None) -> None:\n                    nonlocal captured_url, saw_navigation_away\n                    saw_navigation_away = _record_navigation_away(\n                        candidate=url,\n                        start_url=normalized_start_url,\n                        saw_navigation_away=saw_navigation_away,\n                    )\n                    matched = _match_callback_candidate(\n                        str(url or \"\").strip(),\n                        callback_prefixes,\n                    )\n",
      "                def capture(url: str | None, *, track_navigation_away: bool = False) -> None:\n                    nonlocal captured_url, saw_navigation_away\n                    if track_navigation_away:\n                        saw_navigation_away = _record_navigation_away(\n                            candidate=url,\n                            start_url=normalized_start_url,\n                            saw_navigation_away=saw_navigation_away,\n                        )\n                    matched = _match_callback_candidate(\n                        str(url or \"\").strip(),\n                        callback_prefixes,\n                    )\n",
      authBrowserRuntimePath
    );
  }

  if (!next.includes("saw_navigation_away = _record_navigation_away(")) {
    next = replaceOnce(
      next,
      "                        if is_main_frame:\n                            normalized_url = _normalize_browser_url(getattr(frame, \"url\", \"\"))\n                            if normalized_url and normalized_url != normalized_start_url:\n                                saw_navigation_away = True\n",
      "                        if is_main_frame:\n                            saw_navigation_away = _record_navigation_away(\n                                candidate=getattr(frame, \"url\", \"\"),\n                                start_url=normalized_start_url,\n                                saw_navigation_away=saw_navigation_away,\n                            )\n",
      authBrowserRuntimePath
    );
  }

  if (next.includes("                        capture(getattr(frame, \"url\", \"\"))\n")) {
    next = replaceOnce(
      next,
      "                        capture(getattr(frame, \"url\", \"\"))\n",
      "                        capture(getattr(frame, \"url\", \"\"), track_navigation_away=is_main_frame)\n",
      authBrowserRuntimePath
    );
  }

  if (next.includes('                context.on("request", lambda req: capture(req.url))\n')) {
    next = replaceOnce(
      next,
      '                context.on("request", lambda req: capture(req.url))\n                context.on("requestfailed", lambda req: capture(req.url))\n                context.on("response", lambda res: capture(res.headers.get("location")))\n',
      '                context.on(\n                    "request",\n                    lambda req: capture(req.url),\n                )\n                context.on(\n                    "requestfailed",\n                    lambda req: capture(req.url),\n                )\n                context.on(\n                    "response",\n                    lambda res: capture(res.headers.get("location")),\n                )\n',
      authBrowserRuntimePath
    );
  }

  if (next.includes("page = context.pages[0] if getattr(context, \"pages\", None) else context.new_page()\n")) {
    next = replaceOnce(
      next,
      "                page = context.pages[0] if getattr(context, \"pages\", None) else context.new_page()\n",
      "                page = context.new_page()\n",
      authBrowserRuntimePath
    );
  }

  if (!next.includes("def _record_navigation_away(")) {
    next = replaceOnce(
      next,
      "def _normalize_browser_url(url: str | None) -> str:\n    return str(url or \"\").strip()\n\n\n",
      "def _normalize_browser_url(url: str | None) -> str:\n    return str(url or \"\").strip()\n\n\ndef _record_navigation_away(\n    *,\n    candidate: str | None,\n    start_url: str,\n    saw_navigation_away: bool,\n) -> bool:\n    if saw_navigation_away:\n        return True\n    normalized_candidate = _normalize_browser_url(candidate)\n    if not normalized_candidate or normalized_candidate == start_url:\n        return False\n    parsed = urllib.parse.urlparse(normalized_candidate)\n    return parsed.scheme in {\"http\", \"https\"} and bool(parsed.netloc)\n\n\n",
      authBrowserRuntimePath
    );
  }

  if (next.includes("return bool(normalized_candidate) and normalized_candidate != start_url\n")) {
    next = replaceOnce(
      next,
      "    return bool(normalized_candidate) and normalized_candidate != start_url\n",
      "    if not normalized_candidate or normalized_candidate == start_url:\n        return False\n    parsed = urllib.parse.urlparse(normalized_candidate)\n    return parsed.scheme in {\"http\", \"https\"} and bool(parsed.netloc)\n",
      authBrowserRuntimePath
    );
  }

  return next;
}

function patchHttpServer(current) {
  let next = current;
  const backupRouteBlock =
    `    @app.post("/api/v1/system/backup")\n` +
    `    def run_system_backup(\n` +
    `        request: Request,\n` +
    `        payload: SystemBackupRequest,\n` +
    `    ) -> Any:\n` +
    `        try:\n` +
    `            context = _resolve_request_context(request)\n` +
    `            app_config = context.config\n` +
    `            with session_scope(context.sessions) as session:\n` +
    `                auth_context = _require_user_session_auth_context(\n` +
    `                    request=request,\n` +
    `                    session=session,\n` +
    `                    config=app_config,\n` +
    `                    admin_required=True,\n` +
    `                )\n` +
    `                current_user = auth_context.user\n` +
    `\n` +
    `                timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")\n` +
    `                if payload.output_dir and payload.output_dir.strip():\n` +
    `                    output_dir = Path(payload.output_dir.strip()).expanduser().resolve()\n` +
    `                else:\n` +
    `                    output_dir = (app_config.config_dir / "desktop-backups" / f"backup-{timestamp}").resolve()\n` +
    `\n` +
    `                output_dir.mkdir(parents=True, exist_ok=True)\n` +
    `                if any(output_dir.iterdir()):\n` +
    `                    raise RuntimeError(f"backup output directory must be empty: {output_dir}")\n` +
    `\n` +
    `                backup_result = backup_database(\n` +
    `                    app_config, output_dir, include_documents=payload.include_documents\n` +
    `                )\n` +
    `                copied: list[str] = [str(backup_result.db_artifact)]\n` +
    `                skipped: list[str] = []\n` +
    `\n` +
    `                token_artifact: str | None = None\n` +
    `                if backup_result.token_artifact:\n` +
    `                    token_artifact = str(backup_result.token_artifact)\n` +
    `                    copied.append(token_artifact)\n` +
    `                else:\n` +
    `                    skipped.append("token file not found")\n` +
    `\n` +
    `                documents_artifact: str | None = None\n` +
    `                if payload.include_documents:\n` +
    `                    if backup_result.documents_artifact:\n` +
    `                        documents_artifact = str(backup_result.documents_artifact)\n` +
    `                        copied.append(documents_artifact)\n` +
    `                    else:\n` +
    `                        skipped.append("documents directory not found")\n` +
    `                else:\n` +
    `                    skipped.append("documents excluded by request")\n` +
    `\n` +
    `                credential_key_artifact: str | None = None\n` +
    `                credential_key = (\n` +
    `                    os.getenv("LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY")\n` +
    `                    or app_config.credential_encryption_key\n` +
    `                )\n` +
    `                if credential_key and credential_key.strip():\n` +
    `                    key_artifact = output_dir / "credential_encryption_key.txt"\n` +
    `                    key_artifact.write_text(f"{credential_key.strip()}\\n", encoding="utf-8")\n` +
    `                    credential_key_artifact = str(key_artifact)\n` +
    `                    copied.append(credential_key_artifact)\n` +
    `                else:\n` +
    `                    skipped.append("credential encryption key not available")\n` +
    `\n` +
    `                export_artifact: str | None = None\n` +
    `                export_records: int | None = None\n` +
    `                if payload.include_export_json:\n` +
    `                    export_payload = export_receipts(session)\n` +
    `                    export_file = output_dir / "receipts-export.json"\n` +
    `                    export_file.write_text(\n` +
    `                        json.dumps(export_payload, indent=2, default=str), encoding="utf-8"\n` +
    `                    )\n` +
    `                    export_artifact = str(export_file)\n` +
    `                    export_records = len(export_payload)\n` +
    `                    copied.append(export_artifact)\n` +
    `\n` +
    `                manifest_path = output_dir / "backup-manifest.json"\n` +
    `                manifest_payload = {\n` +
    `                    "created_at": datetime.now(tz=UTC).isoformat(),\n` +
    `                    "requested_by_user_id": current_user.user_id,\n` +
    `                    "provider": backup_result.provider,\n` +
    `                    "output_dir": str(output_dir),\n` +
    `                    "db_artifact": str(backup_result.db_artifact),\n` +
    `                    "token_artifact": token_artifact,\n` +
    `                    "documents_artifact": documents_artifact,\n` +
    `                    "credential_key_artifact": credential_key_artifact,\n` +
    `                    "export_artifact": export_artifact,\n` +
    `                    "export_records": export_records,\n` +
    `                    "include_documents": payload.include_documents,\n` +
    `                    "include_export_json": payload.include_export_json,\n` +
    `                    "copied": copied,\n` +
    `                    "skipped": skipped,\n` +
    `                }\n` +
    `                manifest_path.write_text(\n` +
    `                    json.dumps(manifest_payload, indent=2), encoding="utf-8"\n` +
    `                )\n` +
    `                copied.append(str(manifest_path))\n` +
    `\n` +
    `                result = {\n` +
    `                    "provider": backup_result.provider,\n` +
    `                    "output_dir": str(output_dir),\n` +
    `                    "db_artifact": str(backup_result.db_artifact),\n` +
    `                    "token_artifact": token_artifact,\n` +
    `                    "documents_artifact": documents_artifact,\n` +
    `                    "credential_key_artifact": credential_key_artifact,\n` +
    `                    "export_artifact": export_artifact,\n` +
    `                    "export_records": export_records,\n` +
    `                    "manifest_path": str(manifest_path),\n` +
    `                    "copied": copied,\n` +
    `                    "skipped": skipped,\n` +
    `                }\n` +
    `            return _response(True, result=result, warnings=[], error=None)\n` +
    `        except Exception as exc:  # noqa: BLE001\n` +
    `            return _error_response(exc)\n\n`;
  const backupRoutePattern =
    /    @app\.post\("\/api\/v1\/system\/backup"\)\n[\s\S]*?\n\n(?=    @app\.post\("\/api\/v1\/documents\/upload"\)\n)/;

  if (!next.includes("        scheduler: AutomationScheduler | None = None\n")) {
    if (next.includes("        app.state.desktop_mode = config.desktop_mode\n")) {
      next = replaceOnce(
        next,
        "        app.state.desktop_mode = config.desktop_mode\n",
        "        app.state.desktop_mode = config.desktop_mode\n        scheduler: AutomationScheduler | None = None\n",
        httpServerPath
      );
    } else {
      next = replaceOnce(
        next,
        "        scheduler = AutomationScheduler(session_factory=sessions, config=config)\n",
        "        scheduler: AutomationScheduler | None = None\n        scheduler = AutomationScheduler(session_factory=sessions, config=config)\n",
        httpServerPath
      );
    }
  }

  if (!next.includes("            if scheduler is not None:\n                scheduler.stop()\n")) {
    next = replaceOnce(
      next,
      "            live_sync_stop.set()\n            scheduler.stop()\n",
      "            live_sync_stop.set()\n            if scheduler is not None:\n                scheduler.stop()\n",
      httpServerPath
    );
  }

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
      "class TransactionItemAllocationUpdateRequest(BaseModel):\n    shared: bool\n\n\nUploadFormFile = Annotated[UploadFile, File(...)]\n",
      `class TransactionItemAllocationUpdateRequest(BaseModel):\n    shared: bool\n\n\nclass SystemBackupRequest(BaseModel):\n    output_dir: str | None = None\n    include_documents: bool = True\n    include_export_json: bool = True\n\n\nUploadFormFile = Annotated[UploadFile, File(...)]\n`,
      httpServerPath
    );
  }

  if (backupRoutePattern.test(next)) {
    next = next.replace(backupRoutePattern, backupRouteBlock);
  } else if (!next.includes('@app.post("/api/v1/system/backup")')) {
    next = replaceOnce(
      next,
      '    @app.post("/api/v1/documents/upload")\n',
      `${backupRouteBlock}    @app.post("/api/v1/documents/upload")\n`,
      httpServerPath
    );
  }

  return next;
}

function patchLifecycle(current) {
  let next = current;

  if (!next.includes('if origin == "local_path":')) {
    next = replaceOnce(
      next,
      '    if origin == "builtin":\n        return True, True\n',
      '    if origin == "builtin":\n        return True, True\n    if origin == "local_path":\n        # In Electron, explicit pack enablement in the control center is the install toggle.\n        # When a desktop-managed pack is present on the active plugin path, it should already\n        # behave as installed and enabled in the lifecycle layer.\n        return True, True\n',
      lifecyclePath
    );
  }

  return next;
}

function patchRegistry(current) {
  let next = current;

  if (!next.includes("import os\nimport sys\n")) {
    next = replaceOnce(
      next,
      "from __future__ import annotations\n\nimport sys\n",
      "from __future__ import annotations\n\nimport os\nimport sys\n",
      registryPath
    );
  }

  if (!next.includes("def _plugin_host_kind() -> str:\n")) {
    next = replaceOnce(
      next,
      "_BUILTIN_CONNECTOR_MANIFEST_DEFINITIONS: tuple[dict[str, Any], ...] = (\n",
      "_BUILTIN_CONNECTOR_MANIFEST_DEFINITIONS: tuple[dict[str, Any], ...] = (\n",
      registryPath
    );
    next = replaceOnce(
      next,
      ")\n\n\nclass ConnectorRegistry:\n",
      `)\n\n\ndef _plugin_host_kind() -> str:\n    return "electron" if os.getenv("LIDLTOOL_CONNECTOR_HOST_KIND", "").strip().lower() == "electron" else "self_hosted"\n\n\nclass ConnectorRegistry:\n`,
      registryPath
    );
  }

  if (!next.includes('evaluate_plugin_compatibility(manifest, host_kind=_plugin_host_kind())')) {
    next = next.replaceAll(
      "evaluate_plugin_compatibility(manifest)",
      "evaluate_plugin_compatibility(manifest, host_kind=_plugin_host_kind())"
    );
  }

  if (!next.includes("decision = evaluate_plugin_policy(manifest, config=config, host_kind=_plugin_host_kind())")) {
    next = replaceOnce(
      next,
      "        decision = evaluate_plugin_policy(manifest, config=config)\n",
      "        decision = evaluate_plugin_policy(manifest, config=config, host_kind=_plugin_host_kind())\n",
      registryPath
    );
  }

  return next;
}

function patchRuntimeExecution(current) {
  let next = current;

  if (!next.includes("import os\nimport sys\n")) {
    next = replaceOnce(
      next,
      "from __future__ import annotations\n\nimport sys\n",
      "from __future__ import annotations\n\nimport os\nimport sys\n",
      runtimeExecutionPath
    );
  }

  if (!next.includes("def _plugin_host_kind() -> str:\n")) {
    next = replaceOnce(
      next,
      'ConnectorOperation = Literal["bootstrap", "sync"]\n',
      'ConnectorOperation = Literal["bootstrap", "sync"]\n\n\ndef _plugin_host_kind() -> str:\n    return "electron" if os.getenv("LIDLTOOL_CONNECTOR_HOST_KIND", "").strip().lower() == "electron" else "self_hosted"\n',
      runtimeExecutionPath
    );
  }

  if (!next.includes("host_kind=_plugin_host_kind()")) {
    next = replaceOnce(
      next,
      "        decision = evaluate_plugin_policy(manifest, config=self._config)\n",
      "        decision = evaluate_plugin_policy(manifest, config=self._config, host_kind=_plugin_host_kind())\n",
      runtimeExecutionPath
    );
  }

  return next;
}

function patchRuntimeRunner(current) {
  let next = current;

  if (!next.includes("path = _resolve_module_path(module_ref)\n")) {
    next = replaceOnce(
      next,
      "        path = Path(module_ref)\n        if not path.is_absolute():\n            path = Path.cwd() / path\n",
      "        path = _resolve_module_path(module_ref)\n",
      runtimeRunnerPath
    );
  }

  if (!next.includes("def _resolve_module_path(module_ref: str) -> Path:\n")) {
    next = replaceOnce(
      next,
      "    return importlib.import_module(module_ref)\n\n\n",
      `    return importlib.import_module(module_ref)\n\n\ndef _resolve_module_path(module_ref: str) -> Path:\n    path = Path(module_ref)\n    if path.is_absolute():\n        return path\n\n    cwd = Path.cwd()\n    direct = (cwd / path).resolve()\n    if direct.exists():\n        return direct\n\n    # Some desktop-installed packs still encode the runtime root inside the entrypoint\n    # even though the subprocess already starts from that directory.\n    if len(path.parts) > 1 and path.parts[0] == cwd.name:\n        trimmed = cwd.joinpath(*path.parts[1:]).resolve()\n        if trimmed.exists():\n            return trimmed\n\n    return direct\n\n\n`,
      runtimeRunnerPath
    );
  }

  return next;
}

function patchRouteAuth(current) {
  if (current.includes('RouteAuthPolicy("POST", "/api/v1/system/backup", "admin_only"),')) {
    return current;
  }

  return replaceOnce(
    current,
    '    RouteAuthPolicy("POST", "/api/v1/documents/upload", "authenticated_principal"),\n',
    '    RouteAuthPolicy("POST", "/api/v1/system/backup", "admin_only"),\n    RouteAuthPolicy("POST", "/api/v1/documents/upload", "authenticated_principal"),\n',
    routeAuthPath
  );
}

function patchCli(current) {
  if (current.includes('return "stage=authenticating detail=checking_saved_session"')) {
    return current;
  }

  return replaceOnce(
    current,
    `def _sync_progress_description(state: SyncProgress) -> str:
    if state.stage == "discovering":
        pages = str(state.pages)
        if state.pages_total:
            pages = f"{pages}/{state.pages_total}"
        return f"stage=discovering pages={pages} queued={state.discovered_receipts}"
    if state.stage == "processing":
        current = f" current={state.current_record_ref}" if state.current_record_ref else ""
        return (
            f"stage=processing seen={state.receipts_seen}/{state.discovered_receipts or '?'} "
            f"new={state.new_receipts} items={state.new_items} skipped={state.skipped_existing}{current}"
        )
    return (
        f"stage={state.stage} pages={state.pages} queued={state.discovered_receipts} "
        f"seen={state.receipts_seen} new={state.new_receipts}"
    )
`,
    `def _sync_progress_description(state: SyncProgress) -> str:
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
`,
    cliPath
  );
}

if (!existsSync(httpServerPath) || !existsSync(routeAuthPath) || !existsSync(backupRestorePath) || !existsSync(authBrowserRuntimePath) || !existsSync(lifecyclePath) || !existsSync(registryPath) || !existsSync(runtimeExecutionPath) || !existsSync(runtimeRunnerPath) || !existsSync(cliPath)) {
  throw new Error(`Vendored backend sources not found under ${backendDir}. Run 'npm run vendor:sync' first.`);
}

const patchedBackupRestore = patchBackupRestore(readFileSync(backupRestorePath, "utf-8"));
writeFileSync(backupRestorePath, patchedBackupRestore, "utf-8");

const patchedAuthBrowserRuntime = patchAuthBrowserRuntime(readFileSync(authBrowserRuntimePath, "utf-8"));
writeFileSync(authBrowserRuntimePath, patchedAuthBrowserRuntime, "utf-8");

const patchedHttpServer = patchHttpServer(readFileSync(httpServerPath, "utf-8"));
writeFileSync(httpServerPath, patchedHttpServer, "utf-8");

const patchedRouteAuth = patchRouteAuth(readFileSync(routeAuthPath, "utf-8"));
writeFileSync(routeAuthPath, patchedRouteAuth, "utf-8");

const patchedLifecycle = patchLifecycle(readFileSync(lifecyclePath, "utf-8"));
writeFileSync(lifecyclePath, patchedLifecycle, "utf-8");

const patchedRegistry = patchRegistry(readFileSync(registryPath, "utf-8"));
writeFileSync(registryPath, patchedRegistry, "utf-8");

const patchedRuntimeExecution = patchRuntimeExecution(readFileSync(runtimeExecutionPath, "utf-8"));
writeFileSync(runtimeExecutionPath, patchedRuntimeExecution, "utf-8");

const patchedRuntimeRunner = patchRuntimeRunner(readFileSync(runtimeRunnerPath, "utf-8"));
writeFileSync(runtimeRunnerPath, patchedRuntimeRunner, "utf-8");

const patchedCli = patchCli(readFileSync(cliPath, "utf-8"));
writeFileSync(cliPath, patchedCli, "utf-8");

console.log("Patched vendored backend with desktop backup endpoint support, auth policy alignment, desktop lifecycle alignment, electron plugin host-kind support, desktop runtime entrypoint tolerance, and desktop sync progress UX messaging.");
