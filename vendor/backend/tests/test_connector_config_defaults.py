from __future__ import annotations

from lidltool.connectors.lifecycle import _config_field_payload
from lidltool.connectors.registry import build_builtin_connector_registry
from lidltool.connectors.sdk.manifest import ConnectorConfigField


def test_amazon_manifest_exposes_desktop_tuning_fields() -> None:
    manifest = build_builtin_connector_registry().require_manifest("amazon_de")

    assert manifest.config_schema is not None
    field_keys = [field.key for field in manifest.config_schema.fields]
    assert field_keys == ["years", "headless", "dump_html"]
    field_defaults = {field.key: field.default_value for field in manifest.config_schema.fields}
    assert field_defaults == {
        "years": 1,
        "headless": True,
        "dump_html": None,
    }


def test_amazon_fr_manifest_exposes_desktop_tuning_fields() -> None:
    manifest = build_builtin_connector_registry().require_manifest("amazon_fr")

    assert manifest.config_schema is not None
    field_keys = [field.key for field in manifest.config_schema.fields]
    assert field_keys == ["years", "headless", "dump_html"]
    field_defaults = {field.key: field.default_value for field in manifest.config_schema.fields}
    assert field_defaults == {
        "years": 1,
        "headless": True,
        "dump_html": None,
    }


def test_amazon_gb_manifest_exposes_desktop_tuning_fields() -> None:
    manifest = build_builtin_connector_registry().require_manifest("amazon_gb")

    assert manifest.config_schema is not None
    field_keys = [field.key for field in manifest.config_schema.fields]
    assert field_keys == ["years", "headless", "dump_html"]
    field_defaults = {field.key: field.default_value for field in manifest.config_schema.fields}
    assert field_defaults == {
        "years": 1,
        "headless": True,
        "dump_html": None,
    }


def test_config_field_payload_uses_default_value_when_unsaved() -> None:
    field = ConnectorConfigField(
        key="headless",
        label="Run sync headless",
        input_kind="boolean",
        default_value=True,
    )

    payload = _config_field_payload(field, public_values={}, secret_values={})

    assert payload["value"] is True
