from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from lidltool.config import AppConfig
from lidltool.connectors.runtime.context import build_plugin_runtime_environment
from lidltool.connectors.sdk import assert_receipt_connector_contract
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.runtime import (
    AuthBrowserResult,
    PLUGIN_RUNTIME_CONTEXT_ENV,
    build_auth_browser_runtime_context,
)

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = TEMPLATE_ROOT / "plugin.py"
MANIFEST = ConnectorManifest.model_validate_json((TEMPLATE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _load_plugin_module():
    module_name = "reference_receipt_plugin_template"
    if str(TEMPLATE_ROOT) not in sys.path:
        sys.path.insert(0, str(TEMPLATE_ROOT))
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load reference template plugin module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_env(
    tmp_path: Path,
    *,
    runtime_context: dict[str, object] | None = None,
) -> dict[str, str]:
    config = AppConfig(
        db_path=tmp_path / "template.sqlite",
        config_dir=tmp_path / "config",
        source=MANIFEST.source_id,
    )
    return build_plugin_runtime_environment(
        source_config=config,
        source_id=MANIFEST.source_id,
        tracking_source_id=MANIFEST.source_id,
        manifest=MANIFEST,
        working_directory=TEMPLATE_ROOT,
        connector_options={},
        runtime_context=runtime_context,
    )


def test_reference_template_contract_passes_after_plugin_owned_auth(monkeypatch, tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = module.ReferenceTemplateReceiptPlugin()

    base_env = _runtime_env(tmp_path)
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, base_env[PLUGIN_RUNTIME_CONTEXT_ENV])
    monkeypatch.setenv("LIDLTOOL_CONFIG_DIR", base_env["LIDLTOOL_CONFIG_DIR"])

    started = plugin.invoke_action({"action": "start_auth"})
    flow_id = started["output"]["flow_id"]

    auth_result = AuthBrowserResult(
        flow_id=flow_id,
        session_id="session-1",
        mode="local_display",
        start_url="https://example.invalid/reference-login",
        final_url="https://example.invalid/reference-callback?code=fixture",
        callback_url="https://example.invalid/reference-callback?code=fixture",
        started_at="2026-04-12T10:00:00+00:00",
        completed_at="2026-04-12T10:01:00+00:00",
        storage_state={"cookies": [{"name": "fixture_session"}], "origins": []},
    )
    confirm_env = _runtime_env(
        tmp_path,
        runtime_context=build_auth_browser_runtime_context(auth_result),
    )
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, confirm_env[PLUGIN_RUNTIME_CONTEXT_ENV])
    plugin.invoke_action({"action": "confirm_auth"})

    status = plugin.invoke_action({"action": "get_auth_status"})
    assert status["output"]["status"] == "authenticated"

    assert_receipt_connector_contract(plugin, manifest=MANIFEST)


def test_build_pack_script_emits_expected_receipt_pack_layout(tmp_path: Path) -> None:
    import zipfile

    sys.path.insert(0, str(TEMPLATE_ROOT))
    import build_desktop_pack

    pack_path = build_desktop_pack.build_pack(tmp_path)
    assert pack_path.exists()

    with zipfile.ZipFile(pack_path) as archive:
        names = set(archive.namelist())

    assert "plugin-pack.json" in names
    assert "manifest.json" in names
    assert "integrity.json" in names
    assert "payload/plugin.py" in names
    assert "payload/fixtures/raw_records.json" in names
