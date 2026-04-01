from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.api.source_models import serialize_source_sync_status
from lidltool.config import AppConfig
from lidltool.connectors.auth.auth_orchestration import ConnectorAuthOrchestrationService
from lidltool.connectors.lifecycle import reconcile_connector_lifecycle
from lidltool.connectors.registry import (
    ConnectorRegistry,
    get_connector_registry,
    source_bootstrap_command,
    source_sync_command,
)
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.db.models import Source

_LISTED_RECEIPT_CONNECTORS = {
    "lidl_plus_de",
    "edeka_de",
    "amazon_de",
    "kaufland_de",
    "dm_de",
    "rossmann_de",
    "rewe_de",
}

_ORIGIN_LABELS: dict[str, str] = {
    "builtin": "Built-in",
    "local_path": "External",
    "marketplace": "Marketplace",
    "catalog": "Catalog",
}

def connector_discovery_payload(
    app: FastAPI,
    session: Session,
    *,
    auth_service: ConnectorAuthOrchestrationService,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
    viewer_is_admin: bool = False,
) -> dict[str, Any]:
    resolved_registry = registry or get_connector_registry(config)
    lifecycle = reconcile_connector_lifecycle(
        session,
        config=config,
        registry=resolved_registry,
        include_sensitive_details=viewer_is_admin,
    )
    known_source_ids = {
        str(source_id)
        for source_id in session.execute(select(Source.id)).scalars().all()
    }

    rows: list[dict[str, Any]] = []
    user_status_counts: dict[str, int] = defaultdict(int)
    for source_id, state in lifecycle.items():
        item = state["item"]
        manifest = state["manifest"]
        if not _should_list_connector(source_id=source_id, manifest=manifest):
            continue

        origin_context = item.get("origin") if isinstance(item.get("origin"), dict) else {}
        origin = state["origin"]
        install_state = state["install_state"]
        enable_state = state["enable_state"]
        config_state = state["config_state"]
        connector_options = dict(state["public_config"])
        connector_options.update(state["secret_config"])
        release = state["release"]
        maturity = str(release["maturity"])
        runtime_enabled = manifest is not None and install_state == "installed" and enable_state == "enabled"
        bootstrap = _bootstrap_payload(auth_service, source_id=source_id, enabled=runtime_enabled)
        auth_state, auth_detail = _auth_status(
            auth_service,
            source_id=source_id,
            enabled=runtime_enabled,
            connector_options=connector_options or None,
        )
        sync = serialize_source_sync_status(app, session, source_id=source_id)
        status_detail = _status_detail(
            item=item,
            auth_detail=auth_detail,
            bootstrap=bootstrap,
            sync=sync,
        )
        user_status = _user_status(
            maturity=maturity,
            install_state=install_state,
            enable_state=enable_state,
            config_state=config_state,
            supports_bootstrap=_supports_bootstrap(manifest),
            supports_sync=_supports_sync(manifest),
            auth_state=auth_state,
            bootstrap=bootstrap,
            sync=sync,
        )
        source_exists = source_id in known_source_ids
        actions = _actions_payload(
            source_id=source_id,
            source_exists=source_exists,
            install_state=install_state,
            install_origin=state["install_origin"],
            supports_bootstrap=_supports_bootstrap(manifest),
            supports_sync=_supports_sync(manifest),
            enable_state=enable_state,
            config_state=config_state,
            user_status=user_status,
            viewer_is_admin=viewer_is_admin,
            config=config,
            registry=resolved_registry,
        )
        row = {
            "source_id": source_id,
            "plugin_id": _text(item.get("plugin_id")),
            "display_name": _text(item.get("display_name")) or source_id.replace("_", " ").title(),
            "origin": origin,
            "origin_label": _ORIGIN_LABELS[origin],
            "runtime_kind": _text(item.get("runtime_kind")),
            "install_origin": state["install_origin"],
            "install_state": install_state,
            "enable_state": enable_state,
            "config_state": config_state,
            "maturity": maturity,
            "maturity_label": str(release["label"]),
            "supports_bootstrap": _supports_bootstrap(manifest),
            "supports_sync": _supports_sync(manifest),
            "supports_live_session": _supports_live_session(manifest),
            "supports_live_session_bootstrap": _supports_live_session(manifest),
            "trust_class": _text(item.get("support", {}).get("trust_class"))
            or _text(item.get("trust_class")),
            "status_detail": status_detail,
            "last_sync_summary": _last_sync_summary(sync),
            "last_synced_at": _last_synced_at(sync),
            "ui": {
                "status": user_status,
                "visibility": str(release["default_visibility"]),
                "description": _user_description(
                    user_status=user_status,
                    display_name=_text(item.get("display_name")) or source_id,
                    maturity=maturity,
                    origin=origin,
                    auth_state=auth_state,
                    install_state=install_state,
                    enable_state=enable_state,
                    config_state=config_state,
                ),
                "actions": actions,
            },
            "actions": actions,
            "advanced": {
                "source_exists": source_exists,
                "stale": state["stale"],
                "stale_reason": state["stale_reason"],
                "auth_state": auth_state if viewer_is_admin else "hidden",
                "latest_sync_output": _latest_sync_output(sync) if viewer_is_admin else [],
                "latest_bootstrap_output": list(bootstrap["output_tail"]) if viewer_is_admin else [],
                "latest_sync_status": sync["status"] if viewer_is_admin else "hidden",
                "latest_bootstrap_status": bootstrap["status"] if viewer_is_admin else "hidden",
                "block_reason": item.get("operator_state", {}).get("block") if viewer_is_admin else None,
                "policy": _policy_payload(item, config=config) if viewer_is_admin else None,
                "release": release,
                "origin": {
                    "kind": origin if viewer_is_admin else "hidden",
                    "runtime_kind": _text(item.get("runtime_kind")) if viewer_is_admin else None,
                    "search_path": _text(origin_context.get("search_path")) if viewer_is_admin else None,
                    "origin_path": _text(origin_context.get("origin_path")) if viewer_is_admin else None,
                    "origin_directory": _text(origin_context.get("origin_directory")) if viewer_is_admin else None,
                },
                "diagnostics": list(item.get("diagnostics", [])) if viewer_is_admin else [],
                "manual_commands": actions["operator"].get("manual_commands", {}) if viewer_is_admin else {},
            },
        }
        rows.append(row)
        user_status_counts[user_status] += 1

    rows.sort(key=lambda item: (str(item["display_name"]).lower(), str(item["source_id"]).lower()))
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "viewer": {"is_admin": viewer_is_admin},
        "operator_actions": {
            "can_reload": viewer_is_admin,
            "can_rescan": viewer_is_admin,
        },
        "summary": {
            "total_connectors": len(rows),
            "by_status": dict(sorted(user_status_counts.items())),
        },
        "connectors": rows,
    }


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return None


def _normalize_origin(value: Any) -> str:
    normalized = _text(value)
    if normalized in {"builtin", "local_path", "marketplace", "catalog"}:
        return normalized
    if normalized == "external":
        return "local_path"
    return "catalog"


def _should_list_connector(*, source_id: str, manifest: ConnectorManifest | None) -> bool:
    if source_id in _LISTED_RECEIPT_CONNECTORS:
        return True
    if manifest is None:
        return True
    return _supports_bootstrap(manifest) or _supports_sync(manifest)


def _supports_bootstrap(manifest: ConnectorManifest | None) -> bool:
    if manifest is None:
        return False
    if manifest.auth is not None and manifest.auth.auth_kind != "none":
        return True
    return bool(manifest.builtin_cli and manifest.builtin_cli.bootstrap_args)


def _supports_sync(manifest: ConnectorManifest | None) -> bool:
    if manifest is None:
        return False
    sync_capabilities = {"historical_sync", "incremental_sync", "order_history"}
    return bool(sync_capabilities.intersection(manifest.capabilities))


def _supports_live_session(manifest: ConnectorManifest | None) -> bool:
    if manifest is None:
        return False
    if manifest.auth is not None and manifest.auth.supports_live_session_bootstrap:
        return True
    return "live_session_bootstrap" in manifest.capabilities


def _bootstrap_payload(
    auth_service: ConnectorAuthOrchestrationService,
    *,
    source_id: str,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return _idle_bootstrap(source_id)
    snapshot = auth_service.get_bootstrap_status(source_id=source_id)
    return {
        "source_id": source_id,
        "status": snapshot.state,
        "command": " ".join(snapshot.command) if snapshot.command else None,
        "pid": snapshot.pid,
        "started_at": snapshot.started_at.isoformat() if snapshot.started_at is not None else None,
        "finished_at": snapshot.finished_at.isoformat() if snapshot.finished_at is not None else None,
        "return_code": snapshot.return_code,
        "output_tail": list(snapshot.output_tail),
        "can_cancel": snapshot.can_cancel,
    }


def _idle_bootstrap(source_id: str) -> dict[str, Any]:
    return {
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


def _auth_status(
    auth_service: ConnectorAuthOrchestrationService,
    *,
    source_id: str,
    enabled: bool,
    connector_options: dict[str, Any] | None = None,
) -> tuple[str, str | None]:
    if not enabled:
        return "not_available", None
    snapshot = auth_service.get_auth_status(
        source_id=source_id,
        connector_options=connector_options,
        validate_session=False,
    )
    return snapshot.state, snapshot.detail


def _status_detail(
    *,
    item: dict[str, Any],
    auth_detail: str | None,
    bootstrap: dict[str, Any],
    sync: dict[str, Any],
) -> str | None:
    block = item.get("operator_state", {}).get("block")
    if isinstance(block, dict):
        summary = _text(block.get("summary"))
        if summary:
            return summary
    if auth_detail:
        return auth_detail
    latest_job = sync.get("latest_job")
    if isinstance(latest_job, dict):
        error = _text(latest_job.get("error"))
        if error:
            return error
    output_tail = bootstrap.get("output_tail")
    if isinstance(output_tail, list):
        for line in reversed(output_tail):
            candidate = _text(line)
            if candidate:
                return candidate
    operator_summary = _text(item.get("operator_state", {}).get("summary"))
    if operator_summary:
        return operator_summary
    return None


def _user_status(
    *,
    maturity: str,
    install_state: str,
    enable_state: str,
    config_state: str,
    supports_bootstrap: bool,
    supports_sync: bool,
    auth_state: str,
    bootstrap: dict[str, Any],
    sync: dict[str, Any],
) -> str:
    bootstrap_status = _text(bootstrap.get("status")) or "idle"
    sync_status = _text(sync.get("status")) or "idle"
    latest_job = sync.get("latest_job")
    latest_job_status = (
        _text(latest_job.get("status")).lower()
        if isinstance(latest_job, dict) and _text(latest_job.get("status"))
        else None
    )
    last_success_at = _text(sync.get("last_success_at"))

    if bootstrap_status == "running" or sync_status == "running":
        return "syncing"
    if enable_state == "invalid":
        return "error"
    if enable_state in {"blocked", "incompatible"}:
        return "needs_attention"
    if install_state != "installed":
        return "setup_required"
    if enable_state == "disabled":
        return "needs_attention"
    if config_state in {"required", "incomplete"}:
        return "setup_required"
    if bootstrap_status == "failed" or latest_job_status in {"failed", "canceled"}:
        return "error"
    if auth_state == "reauth_required":
        return "needs_attention"
    if maturity in {"preview", "stub"} and auth_state not in {"connected", "bootstrap_running"} and not last_success_at:
        return "preview"
    if supports_bootstrap and auth_state in {"not_connected", "bootstrap_canceled"}:
        return "setup_required"
    if supports_sync and (last_success_at or latest_job_status in {"success", "partial_success"}):
        return "ready"
    if auth_state == "connected":
        return "connected"
    if supports_bootstrap:
        return "setup_required"
    if maturity in {"preview", "stub"}:
        return "preview"
    return "ready" if supports_sync else "connected"


def _last_synced_at(sync: dict[str, Any]) -> str | None:
    latest_job = sync.get("latest_job")
    if isinstance(latest_job, dict):
        finished_at = _text(latest_job.get("finished_at"))
        if finished_at:
            return finished_at
    return _text(sync.get("last_success_at"))


def _last_sync_summary(sync: dict[str, Any]) -> str | None:
    latest_job = sync.get("latest_job")
    if not isinstance(latest_job, dict):
        return None
    summary = latest_job.get("summary")
    if isinstance(summary, dict):
        progress = summary.get("progress")
        if isinstance(progress, dict):
            new_receipts = int(progress.get("new_receipts", 0) or 0)
            new_items = int(progress.get("new_items", 0) or 0)
            receipts_seen = int(progress.get("receipts_seen", 0) or 0)
            if new_receipts or new_items or receipts_seen:
                return (
                    f"{new_receipts} new receipt(s), {new_items} new item(s), "
                    f"{receipts_seen} checked"
                )
        warnings = summary.get("warnings")
        if isinstance(warnings, list) and warnings:
            return _text(warnings[0])
    error = _text(latest_job.get("error"))
    if error:
        return error
    status = _text(latest_job.get("status"))
    if status:
        return f"Last sync finished with status: {status.lower()}"
    return None


def _latest_sync_output(sync: dict[str, Any]) -> list[str]:
    current_run = sync.get("current_run")
    if not isinstance(current_run, dict):
        return []
    output = current_run.get("output_tail")
    if not isinstance(output, list):
        return []
    return [str(item) for item in output if str(item).strip()]


def _user_description(
    *,
    user_status: str,
    display_name: str,
    maturity: str,
    origin: str,
    auth_state: str,
    install_state: str,
    enable_state: str,
    config_state: str,
) -> str:
    if user_status == "setup_required":
        if install_state != "installed":
            return f"Install and set up {display_name} before the first sync."
        if config_state in {"required", "incomplete"}:
            return f"Finish the {display_name} setup before syncing."
        return f"Connect {display_name} to start syncing receipts."
    if user_status == "connected":
        return f"{display_name} is connected. You can start a sync at any time."
    if user_status == "syncing":
        return f"{display_name} is syncing in the background."
    if user_status == "ready":
        return f"{display_name} is ready for regular receipt sync."
    if user_status == "needs_attention":
        if auth_state == "reauth_required":
            return f"{display_name} needs to be reconnected before the next sync."
        if enable_state == "disabled":
            return f"{display_name} is installed but currently turned off on this server."
        if enable_state in {"blocked", "incompatible"}:
            return f"{display_name} is installed but cannot run on this server right now."
        return f"{display_name} needs operator attention before syncing again."
    if user_status == "error":
        return f"The latest setup or sync for {display_name} did not complete successfully."
    if maturity in {"preview", "stub"}:
        origin_label = _ORIGIN_LABELS.get(origin, "Connector").lower()
        return f"{origin_label.capitalize()} preview connector. Expect rough edges and reconnects."
    return f"{display_name} is available."


def _actions_payload(
    *,
    source_id: str,
    source_exists: bool,
    install_state: str,
    install_origin: str | None,
    supports_bootstrap: bool,
    supports_sync: bool,
    enable_state: str,
    config_state: str,
    user_status: str,
    viewer_is_admin: bool,
    config: AppConfig | None,
    registry: ConnectorRegistry,
) -> dict[str, Any]:
    primary = _action_payload(kind=None, enabled=False)
    if install_state != "installed":
        if viewer_is_admin:
            primary = _action_payload(kind="set_up", enabled=True)
    elif enable_state == "enabled":
        if user_status in {"setup_required", "preview"} and (
            supports_bootstrap or config_state != "not_required"
        ):
            primary = _action_payload(kind="set_up", enabled=True)
        elif user_status in {"needs_attention", "error"} and supports_bootstrap:
            primary = _action_payload(kind="reconnect", enabled=True)
        elif user_status in {"connected", "ready"} and supports_sync:
            primary = _action_payload(kind="sync_now", enabled=True)
    elif enable_state == "disabled":
        if viewer_is_admin:
            primary = _action_payload(kind="set_up", enabled=True)
    if primary["kind"] is None and source_exists:
        primary = _action_payload(kind="open_source", href="/sources", enabled=True)

    secondary = _action_payload(kind=None, enabled=False)
    if source_exists and primary["kind"] != "open_source":
        secondary = _action_payload(
            kind="view_receipts" if supports_sync else "open_source",
            href="/transactions" if supports_sync else "/sources",
            enabled=True,
        )

    bootstrap_command = source_bootstrap_command(source_id, config=config, registry=registry)
    sync_command = source_sync_command(source_id, config=config, registry=registry)
    manual_commands: dict[str, str] = {}
    if viewer_is_admin:
        if bootstrap_command is not None:
            manual_commands["bootstrap"] = " ".join(bootstrap_command)
        if sync_command is not None:
            manual_commands["sync"] = " ".join(sync_command)
            manual_commands["full_sync"] = " ".join([*sync_command, "--full"])

    return {
        "primary": primary,
        "secondary": secondary,
        "operator": {
            "full_sync": viewer_is_admin and supports_sync and enable_state == "enabled",
            "rescan": viewer_is_admin,
            "reload": viewer_is_admin,
            "install": viewer_is_admin and install_state != "installed",
            "enable": viewer_is_admin and install_state == "installed" and enable_state == "disabled",
            "disable": viewer_is_admin and enable_state == "enabled",
            "uninstall": viewer_is_admin and install_state == "installed" and install_origin in {"local_path", "marketplace"},
            "configure": viewer_is_admin and config_state != "not_required",
            "manual_commands": manual_commands,
        },
    }


def _action_payload(
    *,
    kind: str | None,
    href: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "href": href,
        "enabled": enabled and kind is not None,
    }


def _policy_payload(item: dict[str, Any], *, config: AppConfig | None) -> dict[str, Any]:
    operator_state = item.get("operator_state")
    block = operator_state.get("block") if isinstance(operator_state, dict) else None
    return {
        "blocked": isinstance(block, dict),
        "block_reason": block if isinstance(block, dict) else None,
        "status": _text(item.get("status")),
        "status_detail": _text(item.get("status_detail")),
        "trust_class": _text(item.get("support", {}).get("trust_class")),
        "external_runtime_enabled": (
            bool(config.connector_external_runtime_enabled) if config is not None else None
        ),
        "external_receipt_plugins_enabled": (
            bool(config.connector_external_receipt_plugins_enabled) if config is not None else None
        ),
        "allowed_trust_classes": (
            list(config.connector_external_allowed_trust_classes) if config is not None else []
        ),
    }
