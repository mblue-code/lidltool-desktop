from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.auth.crypto import decrypt_payload, encrypt_payload
from lidltool.config import AppConfig, database_url
from lidltool.connectors.management import plugin_management_payload
from lidltool.connectors.release_policy import release_policy_payload
from lidltool.connectors.registry import ConnectorRegistry, get_connector_registry
from lidltool.connectors.sdk.manifest import (
    ConnectorConfigField,
    ConnectorManifest,
)
from lidltool.db.engine import create_engine_for_url, session_factory, session_scope
from lidltool.db.models import ConnectorConfigState, ConnectorLifecycleState

_AUTO_INSTALLED_SOURCES = {"edeka_de"}
_INSTALLABLE_ORIGINS = {"local_path", "marketplace", "catalog"}
_REMOVABLE_ORIGINS = {"local_path", "marketplace"}


def reconcile_connector_lifecycle(
    session: Session,
    *,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
    include_sensitive_details: bool = True,
) -> dict[str, dict[str, Any]]:
    resolved_registry = registry or get_connector_registry(config)
    management = plugin_management_payload(
        session,
        config=config,
        registry=resolved_registry,
        include_sensitive_details=include_sensitive_details,
    )
    lifecycle_by_source = {
        row.source_id: row
        for row in session.execute(select(ConnectorLifecycleState)).scalars().all()
    }
    config_by_source = {
        row.source_id: row
        for row in session.execute(select(ConnectorConfigState)).scalars().all()
    }
    management_by_source: dict[str, Mapping[str, Any]] = {}

    projected: dict[str, dict[str, Any]] = {}
    now = datetime.now(tz=UTC)

    for item in management["entries"]:
        if item.get("plugin_family") != "receipt":
            continue
        source_id = _text(item.get("source_id"))
        if not source_id:
            continue
        management_by_source[source_id] = item
        manifest = resolved_registry.get_manifest(source_id)
        lifecycle_row = lifecycle_by_source.get(source_id)
        current_origin = _normalize_origin(item.get("plugin_origin"))
        if manifest is not None and lifecycle_row is None:
            installed, desired_enabled = _default_lifecycle_values(item=item, manifest=manifest)
            lifecycle_row = ConnectorLifecycleState(
                source_id=source_id,
                plugin_id=manifest.plugin_id,
                install_origin=current_origin,
                installed=installed,
                desired_enabled=desired_enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(lifecycle_row)
            lifecycle_by_source[source_id] = lifecycle_row
        elif lifecycle_row is not None:
            expected_plugin_id = manifest.plugin_id if manifest is not None else _text(item.get("plugin_id"))
            if lifecycle_row.plugin_id != expected_plugin_id:
                lifecycle_row.plugin_id = expected_plugin_id
            if current_origin != "catalog" or not lifecycle_row.install_origin:
                lifecycle_row.install_origin = current_origin

        config_row = config_by_source.get(source_id)
        expected_plugin_id = manifest.plugin_id if manifest is not None else _text(item.get("plugin_id"))
        if config_row is not None and config_row.plugin_id != expected_plugin_id:
            config_row.plugin_id = expected_plugin_id

        public_values = _public_config_values(config_row)
        secret_values = _secret_config_values(config_row, config=config)
        install_state = _install_state(item=item, manifest=manifest, lifecycle=lifecycle_row)
        enable_state = _enable_state(item=item, lifecycle=lifecycle_row, install_state=install_state)
        release = release_policy_payload(source_id=source_id, manifest=manifest)
        config_state = _config_state(
            manifest=manifest,
            public_values=public_values,
            secret_values=secret_values,
        )
        projected[source_id] = {
            "source_id": source_id,
            "manifest": manifest,
            "item": item,
            "lifecycle": lifecycle_row,
            "config_row": config_row,
            "origin": current_origin,
            "install_origin": _install_origin(
                item=item,
                lifecycle=lifecycle_row,
            ),
            "install_state": install_state,
            "enable_state": enable_state,
            "config_state": config_state,
            "release": release,
            "stale": False,
            "stale_reason": None,
            "public_config": public_values,
            "secret_config": secret_values,
        }

    for source_id, lifecycle_row in list(lifecycle_by_source.items()):
        if source_id in projected:
            continue
        config_row = config_by_source.get(source_id)
        if not lifecycle_row.installed:
            session.delete(lifecycle_row)
            lifecycle_by_source.pop(source_id, None)
            continue
        public_values = _public_config_values(config_row)
        secret_values = _secret_config_values(config_row, config=config)
        install_origin = _normalize_origin(lifecycle_row.install_origin)
        projected[source_id] = _stale_projected_state(
            source_id=source_id,
            lifecycle=lifecycle_row,
            config_row=config_row,
            install_origin=install_origin,
            public_values=public_values,
            secret_values=secret_values,
        )

    session.flush()
    return projected


def connector_runtime_options(
    *,
    source_id: str,
    config: AppConfig,
    session: Session | None = None,
    registry: ConnectorRegistry | None = None,
    allow_reconcile_writes: bool = True,
) -> dict[str, Any]:
    resolved_registry = registry or get_connector_registry(config)
    if not allow_reconcile_writes:
        manifest = resolved_registry.get_manifest(source_id)
        if session is not None:
            row = session.get(ConnectorConfigState, source_id)
            return _runtime_options_for_manifest_row(
                manifest=manifest,
                row=row,
                config=config,
            )
        engine = create_engine_for_url(database_url(config))
        sessions = session_factory(engine)
        try:
            with session_scope(sessions) as db_session:
                row = db_session.get(ConnectorConfigState, source_id)
                return _runtime_options_for_manifest_row(
                    manifest=manifest,
                    row=row,
                    config=config,
                )
        finally:
            engine.dispose()

    if session is not None:
        state = reconcile_connector_lifecycle(session, config=config, registry=resolved_registry).get(source_id)
        if state is None:
            return {}
        return _runtime_options_from_state(state)

    engine = create_engine_for_url(database_url(config))
    sessions = session_factory(engine)
    try:
        with session_scope(sessions) as db_session:
            state = reconcile_connector_lifecycle(
                db_session,
                config=config,
                registry=resolved_registry,
            ).get(source_id)
            if state is None:
                return {}
            return _runtime_options_from_state(state)
    finally:
        engine.dispose()


def connector_lifecycle_record_payload(
    session: Session,
    *,
    source_id: str,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> dict[str, Any]:
    state = reconcile_connector_lifecycle(session, config=config, registry=registry).get(source_id)
    if state is None:
        raise RuntimeError("source not found")
    manifest = state["manifest"]
    if manifest is None:
        raise RuntimeError("source not found")
    fields = list(manifest.config_schema.fields) if manifest.config_schema is not None else []
    public_values = dict(state["public_config"])
    secret_values = dict(state["secret_config"])
    return {
        "source_id": source_id,
        "plugin_id": manifest.plugin_id,
        "display_name": manifest.display_name,
        "install_origin": state["install_origin"],
        "config_state": state["config_state"],
        "fields": [
            _config_field_payload(
                field,
                public_values=public_values,
                secret_values=secret_values,
            )
            for field in fields
        ],
    }


def update_connector_config(
    session: Session,
    *,
    source_id: str,
    config: AppConfig,
    values: Mapping[str, Any] | None,
    clear_secret_keys: list[str] | None = None,
    registry: ConnectorRegistry | None = None,
) -> dict[str, Any]:
    state = reconcile_connector_lifecycle(session, config=config, registry=registry).get(source_id)
    if state is None:
        raise RuntimeError("source not found")
    manifest = state["manifest"]
    if manifest is None:
        raise RuntimeError("source not found")

    config_row = state["config_row"]
    public_values = dict(state["public_config"])
    secret_values = dict(state["secret_config"])
    submitted_values = dict(values or {})
    clear_set = {item for item in (clear_secret_keys or []) if item}

    field_by_key = {
        field.key: field
        for field in (manifest.config_schema.fields if manifest.config_schema is not None else ())
    }
    unknown_keys = sorted(set(submitted_values) - set(field_by_key))
    if unknown_keys:
        raise RuntimeError(f"invalid connector config field(s): {', '.join(unknown_keys)}")

    for key in clear_set:
        field = field_by_key.get(key)
        if field is None:
            raise RuntimeError(f"invalid connector config field: {key}")
        if not field.sensitive:
            public_values.pop(key, None)
            continue
        secret_values.pop(key, None)

    for key, raw_value in submitted_values.items():
        field = field_by_key[key]
        normalized = _normalize_field_value(field, raw_value)
        if normalized is None:
            if field.sensitive:
                secret_values.pop(key, None)
            else:
                public_values.pop(key, None)
            continue
        if field.sensitive:
            secret_values[key] = normalized
        else:
            public_values[key] = normalized

    if config_row is None:
        config_row = ConnectorConfigState(
            source_id=source_id,
            plugin_id=manifest.plugin_id,
            public_config_json={},
            secret_config_encrypted=None,
        )
        session.add(config_row)

    config_row.plugin_id = manifest.plugin_id
    config_row.public_config_json = public_values or None
    config_row.secret_config_encrypted = _encrypt_secret_values(config, secret_values) if secret_values else None
    session.flush()

    return connector_lifecycle_record_payload(
        session,
        source_id=source_id,
        config=config,
        registry=registry,
    )


def install_connector(
    session: Session,
    *,
    source_id: str,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> dict[str, Any]:
    state = reconcile_connector_lifecycle(session, config=config, registry=registry).get(source_id)
    if state is None:
        raise RuntimeError("source not found")
    lifecycle = state["lifecycle"]
    manifest = state["manifest"]
    if manifest is None or lifecycle is None:
        raise RuntimeError("connector install is not available for this source")
    lifecycle.plugin_id = manifest.plugin_id
    lifecycle.install_origin = _normalize_origin(manifest.plugin_origin)
    lifecycle.installed = True
    session.flush()
    return _lifecycle_action_result(session, source_id=source_id, config=config, registry=registry)


def set_connector_enabled(
    session: Session,
    *,
    source_id: str,
    enabled: bool,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> dict[str, Any]:
    state = reconcile_connector_lifecycle(session, config=config, registry=registry).get(source_id)
    if state is None:
        raise RuntimeError("source not found")
    lifecycle = state["lifecycle"]
    manifest = state["manifest"]
    if manifest is None or lifecycle is None:
        raise RuntimeError("connector lifecycle is not available for this source")
    lifecycle.plugin_id = manifest.plugin_id
    lifecycle.install_origin = _normalize_origin(manifest.plugin_origin)
    if not lifecycle.installed and enabled:
        raise RuntimeError("connector must be installed before it can be enabled")
    lifecycle.desired_enabled = enabled
    session.flush()
    return _lifecycle_action_result(session, source_id=source_id, config=config, registry=registry)


def uninstall_connector(
    session: Session,
    *,
    source_id: str,
    purge_config: bool = False,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> dict[str, Any]:
    state = reconcile_connector_lifecycle(session, config=config, registry=registry).get(source_id)
    if state is None:
        raise RuntimeError("source not found")
    lifecycle = state["lifecycle"]
    if lifecycle is None:
        raise RuntimeError("connector lifecycle is not available for this source")
    removable = bool(state["release"]["default_visibility"] in {"default", "operator_only"}) and (
        state["install_origin"] in _REMOVABLE_ORIGINS
    )
    if not removable:
        raise RuntimeError("connector uninstall is not available for this source")

    plugin_id = _text(state["item"].get("plugin_id")) or lifecycle.plugin_id
    display_name = _text(state["item"].get("display_name")) or source_id
    install_origin = state["install_origin"]

    lifecycle.installed = False
    lifecycle.desired_enabled = False

    config_row = state["config_row"]
    if purge_config and config_row is not None:
        session.delete(config_row)
        config_row = None

    manifest = state["manifest"]
    if manifest is None and config_row is None:
        session.delete(lifecycle)

    session.flush()
    if manifest is None:
        return {
            "source_id": source_id,
            "plugin_id": plugin_id,
            "display_name": display_name,
            "install_origin": install_origin,
            "install_state": "discovered",
            "enable_state": "disabled",
            "config_state": "not_required" if config_row is None else "complete",
            "stale": False,
            "stale_reason": None,
            "config_preserved": config_row is not None,
        }

    result = _lifecycle_action_result(session, source_id=source_id, config=config, registry=registry)
    result["config_preserved"] = not purge_config
    return result


def connector_operation_snapshot(
    session: Session,
    *,
    source_id: str,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> dict[str, Any]:
    state = reconcile_connector_lifecycle(session, config=config, registry=registry).get(source_id)
    if state is None:
        raise RuntimeError("source not found")
    manifest = state["manifest"]
    if manifest is None:
        raise RuntimeError("source not found")
    return {
        "source_id": source_id,
        "plugin_id": _text(state["item"].get("plugin_id")) or (manifest.plugin_id if manifest is not None else None),
        "display_name": _text(state["item"].get("display_name")) or (manifest.display_name if manifest is not None else source_id),
        "origin": state["origin"],
        "install_origin": state["install_origin"],
        "install_state": state["install_state"],
        "enable_state": state["enable_state"],
        "config_state": state["config_state"],
        "status_detail": _status_detail_from_item(state["item"]),
        "stale": state["stale"],
        "stale_reason": state["stale_reason"],
        "runtime_options": _runtime_options_from_state(state),
        "manifest": manifest,
        "item": state["item"],
    }


def assert_connector_operation_allowed(
    session: Session,
    *,
    source_id: str,
    operation: str,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> dict[str, Any]:
    snapshot = connector_operation_snapshot(
        session,
        source_id=source_id,
        config=config,
        registry=registry,
    )
    install_state = snapshot["install_state"]
    enable_state = snapshot["enable_state"]
    config_state = snapshot["config_state"]
    if install_state != "installed":
        raise RuntimeError("setup required")
    if enable_state == "disabled":
        raise RuntimeError("connector is disabled")
    if enable_state == "blocked":
        raise RuntimeError("connector blocked by server policy")
    if enable_state == "invalid":
        raise RuntimeError("connector is invalid")
    if enable_state == "incompatible":
        raise RuntimeError("connector is incompatible with this server")
    if config_state in {"required", "incomplete"}:
        raise RuntimeError("connector configuration is incomplete")
    return snapshot


def _lifecycle_action_result(
    session: Session,
    *,
    source_id: str,
    config: AppConfig | None,
    registry: ConnectorRegistry | None,
) -> dict[str, Any]:
    snapshot = connector_operation_snapshot(
        session,
        source_id=source_id,
        config=config,
        registry=registry,
    )
    return {
        "source_id": snapshot["source_id"],
        "plugin_id": snapshot["plugin_id"],
        "display_name": snapshot["display_name"],
        "install_origin": snapshot["install_origin"],
        "install_state": snapshot["install_state"],
        "enable_state": snapshot["enable_state"],
        "config_state": snapshot["config_state"],
        "stale": snapshot["stale"],
        "stale_reason": snapshot["stale_reason"],
    }


def _status_detail_from_item(item: Mapping[str, Any]) -> str | None:
    operator_state = item.get("operator_state")
    if isinstance(operator_state, Mapping):
        summary = _text(operator_state.get("summary"))
        if summary:
            return summary
        block = operator_state.get("block")
        if isinstance(block, Mapping):
            return _text(block.get("summary")) or _text(block.get("detail"))
    return _text(item.get("status"))


def _runtime_options_from_state(state: Mapping[str, Any]) -> dict[str, Any]:
    manifest = state.get("manifest")
    public_values = state.get("public_config") or {}
    secret_values = state.get("secret_config") or {}
    options = {}
    if isinstance(public_values, Mapping):
        options.update(public_values)
    if isinstance(secret_values, Mapping):
        options.update(secret_values)
    if isinstance(manifest, ConnectorManifest) and manifest.config_schema is not None:
        for field in manifest.config_schema.fields:
            if field.key in options:
                continue
            if field.default_value is not None:
                options[field.key] = field.default_value
    return options


def _runtime_options_for_manifest_row(
    *,
    manifest: ConnectorManifest | None,
    row: ConnectorConfigState | None,
    config: AppConfig,
) -> dict[str, Any]:
    state = {
        "manifest": manifest,
        "public_config": _public_config_values(row),
        "secret_config": _secret_config_values(row, config=config),
    }
    return _runtime_options_from_state(state)


def _default_lifecycle_values(
    *,
    item: Mapping[str, Any],
    manifest: ConnectorManifest,
) -> tuple[bool, bool]:
    origin = _normalize_origin(item.get("plugin_origin"))
    if origin == "builtin":
        return True, True
    if origin == "local_path":
        # In Electron, explicit pack enablement in the control center is the install toggle.
        # When a desktop-managed pack is present on the active plugin path, it should already
        # behave as installed and enabled in the lifecycle layer.
        return True, True
    repo_managed = bool(manifest.metadata.get("repo_managed"))
    if manifest.source_id in _AUTO_INSTALLED_SOURCES or repo_managed:
        return True, True
    return False, False


def _install_state(
    *,
    item: Mapping[str, Any],
    manifest: ConnectorManifest | None,
    lifecycle: ConnectorLifecycleState | None,
) -> str:
    origin = _normalize_origin(item.get("plugin_origin"))
    if origin == "catalog" and (lifecycle is None or not lifecycle.installed):
        return "catalog_only"
    if lifecycle is not None and lifecycle.installed:
        return "installed"
    if manifest is None:
        return "discovered"
    return "discovered"


def _enable_state(
    *,
    item: Mapping[str, Any],
    lifecycle: ConnectorLifecycleState | None,
    install_state: str,
) -> str:
    status = _text(item.get("status"))
    if status == "blocked_by_policy":
        return "blocked"
    if status == "invalid":
        return "invalid"
    if status == "incompatible":
        return "incompatible"
    if install_state != "installed":
        return "disabled"
    if lifecycle is None:
        return "disabled"
    return "enabled" if lifecycle.desired_enabled else "disabled"


def _config_state(
    *,
    manifest: ConnectorManifest | None,
    public_values: Mapping[str, Any],
    secret_values: Mapping[str, Any],
) -> str:
    fields = list(manifest.config_schema.fields) if manifest is not None and manifest.config_schema else []
    if not fields:
        return "not_required"
    required_fields = [field for field in fields if field.required]
    if not required_fields:
        return "complete"
    present_count = 0
    missing_count = 0
    for field in required_fields:
        if _value_for_field(field, public_values, secret_values) is None:
            missing_count += 1
        else:
            present_count += 1
    if present_count == 0:
        return "required"
    if missing_count > 0:
        return "incomplete"
    return "complete"


def _config_field_payload(
    field: ConnectorConfigField,
    *,
    public_values: Mapping[str, Any],
    secret_values: Mapping[str, Any],
) -> dict[str, Any]:
    if field.sensitive:
        return {
            "key": field.key,
            "label": field.label,
            "description": field.description,
            "input_kind": field.input_kind,
            "required": field.required,
            "sensitive": True,
            "operator_only": field.operator_only,
            "placeholder": field.placeholder,
            "has_value": _value_for_field(field, public_values, secret_values) is not None,
        }
    value = _value_for_field(field, public_values, secret_values)
    return {
        "key": field.key,
        "label": field.label,
        "description": field.description,
        "input_kind": field.input_kind,
        "required": field.required,
        "sensitive": False,
        "operator_only": field.operator_only,
        "placeholder": field.placeholder,
        "value": value,
    }


def _install_origin(
    *,
    item: Mapping[str, Any],
    lifecycle: ConnectorLifecycleState | None,
) -> str | None:
    if lifecycle is not None and lifecycle.install_origin:
        return _normalize_origin(lifecycle.install_origin)
    origin = _normalize_origin(item.get("plugin_origin"))
    return None if origin == "catalog" else origin


def _stale_projected_state(
    *,
    source_id: str,
    lifecycle: ConnectorLifecycleState,
    config_row: ConnectorConfigState | None,
    install_origin: str,
    public_values: Mapping[str, Any],
    secret_values: Mapping[str, Any],
) -> dict[str, Any]:
    display_name = source_id.replace("_", " ").title()
    release = release_policy_payload(source_id=source_id, manifest=None)
    item = {
        "source_id": source_id,
        "plugin_id": lifecycle.plugin_id or (config_row.plugin_id if config_row is not None else None),
        "display_name": display_name,
        "plugin_origin": install_origin,
        "runtime_kind": None,
        "status": "invalid",
        "status_detail": "Installed connector files are missing from this server.",
        "support": {"trust_class": None},
        "operator_state": {
            "summary": "Installed connector files are missing from this server.",
            "block": {
                "code": "plugin_missing",
                "label": "Plugin missing",
                "summary": "The installed connector is no longer available on disk.",
                "detail": "Restore the plugin files or uninstall the connector to clean up stale state.",
            },
        },
        "origin": {
            "search_path": None,
            "origin_path": None,
            "origin_directory": None,
        },
        "diagnostics": [
            "Persisted connector lifecycle state still references a plugin that is no longer discoverable.",
        ],
    }
    return {
        "source_id": source_id,
        "manifest": None,
        "item": item,
        "lifecycle": lifecycle,
        "config_row": config_row,
        "origin": install_origin,
        "install_origin": install_origin,
        "install_state": "installed",
        "enable_state": "invalid",
        "config_state": "not_required",
        "release": release,
        "stale": True,
        "stale_reason": "plugin_missing",
        "public_config": dict(public_values),
        "secret_config": dict(secret_values),
    }


def _value_for_field(
    field: ConnectorConfigField,
    public_values: Mapping[str, Any],
    secret_values: Mapping[str, Any],
) -> Any:
    if field.sensitive:
        return secret_values.get(field.key)
    return public_values.get(field.key)


def _public_config_values(row: ConnectorConfigState | None) -> dict[str, Any]:
    raw = row.public_config_json if row is not None else None
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in raw.items()}


def _secret_config_values(
    row: ConnectorConfigState | None,
    *,
    config: AppConfig | None,
) -> dict[str, Any]:
    if row is None or not row.secret_config_encrypted or config is None:
        return {}
    secret = (config.credential_encryption_key or "").strip()
    if not secret:
        return {}
    try:
        envelope = json.loads(row.secret_config_encrypted)
        if not isinstance(envelope, dict):
            return {}
        payload = decrypt_payload(envelope, secret=secret)
    except Exception:
        return {}
    values = payload.get("values")
    if not isinstance(values, dict):
        return {}
    return {str(key): value for key, value in values.items()}


def _encrypt_secret_values(config: AppConfig, values: Mapping[str, Any]) -> str:
    secret = (config.credential_encryption_key or "").strip()
    if not secret:
        raise RuntimeError(
            "credential encryption key is required for connector secrets; "
            "set LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY"
        )
    payload = encrypt_payload(
        {"values": dict(values)},
        secret=secret,
        key_id=config.credential_encryption_key_id,
    )
    return json.dumps(payload, separators=(",", ":"))


def _normalize_field_value(field: ConnectorConfigField, value: Any) -> str | int | float | bool | None:
    if value is None:
        return None
    if field.input_kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        raise RuntimeError(f"invalid boolean value for {field.key}")
    if field.input_kind == "number":
        if isinstance(value, bool):
            raise RuntimeError(f"invalid numeric value for {field.key}")
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return None
            try:
                return int(candidate) if candidate.isdigit() else float(candidate)
            except ValueError as exc:
                raise RuntimeError(f"invalid numeric value for {field.key}") from exc
        raise RuntimeError(f"invalid numeric value for {field.key}")
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    if isinstance(value, (int, float, bool)):
        return value
    raise RuntimeError(f"invalid config value for {field.key}")


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
