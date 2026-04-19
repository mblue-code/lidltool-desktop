from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4


def _plugin_module_path() -> Path:
    return Path(__file__).resolve().parents[5] / "plugins" / "rewe_de" / "plugin.py"


def _load_rewe_plugin_module():
    module_name = f"test_rewe_plugin_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, _plugin_module_path())
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_context(tmp_path: Path, *, options: dict[str, object] | None = None) -> SimpleNamespace:
    data_dir = tmp_path / "plugin-runtime" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        connector_options=dict(options or {}),
        tracking_source_id="rewe_de",
        storage=SimpleNamespace(data_dir=data_dir),
    )


def test_rewe_auth_status_marks_stale_saved_session_as_expired(tmp_path: Path, monkeypatch) -> None:
    module = _load_rewe_plugin_module()
    runtime_context = _runtime_context(tmp_path)
    monkeypatch.setattr(module, "load_plugin_runtime_context", lambda: runtime_context)

    state_file = module._state_file_for_context()
    module._write_json(state_file, {"cookies": [{"name": "stale"}], "origins": []})

    def _raise_expired(*, storage_state, start_url, headless):  # type: ignore[no-untyped-def]
        del storage_state, start_url, headless
        raise module.RewePluginError(
            "REWE session expired or did not reach the authenticated account area",
            code="auth_required",
        )

    monkeypatch.setattr(module, "_verify_rewe_storage_state", _raise_expired)

    plugin = module.ReweReceiptPlugin()
    status = plugin._get_auth_status()

    assert status.status == "expired"
    assert status.is_authenticated is False
    assert "expired" in str(status.detail).lower()
    assert status.metadata["reauth_required"] is True


def test_rewe_start_auth_replaces_stale_state_without_manual_deletion(
    tmp_path: Path, monkeypatch
) -> None:
    fresh_state_path = tmp_path / "fresh-storage-state.json"
    fresh_state_path.write_text(
        json.dumps({"cookies": [{"name": "fresh"}], "origins": []}),
        encoding="utf-8",
    )

    module = _load_rewe_plugin_module()
    runtime_context = _runtime_context(
        tmp_path,
        options={"import_storage_state_file": str(fresh_state_path)},
    )
    monkeypatch.setattr(module, "load_plugin_runtime_context", lambda: runtime_context)

    state_file = module._state_file_for_context()
    module._write_json(state_file, {"cookies": [{"name": "stale"}], "origins": []})

    def _verify_state(*, storage_state, start_url, headless):  # type: ignore[no-untyped-def]
        del start_url, headless
        cookies = storage_state.get("cookies", [])
        if cookies and cookies[0].get("name") == "stale":
            raise module.RewePluginError(
                "REWE session expired or did not reach the authenticated account area",
                code="auth_required",
            )
        return dict(storage_state)

    monkeypatch.setattr(module, "_verify_rewe_storage_state", _verify_state)

    plugin = module.ReweReceiptPlugin()
    result = plugin._start_auth()

    assert result.status == "confirmed"
    assert result.metadata["replaced_stale_session"] is True
    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved_state["cookies"][0]["name"] == "fresh"
