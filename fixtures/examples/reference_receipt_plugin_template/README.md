# Reference Receipt Plugin Template

This template is the clean-break reference for third-party merchant receipt plugins after the plugin-platform reform.

It demonstrates:

- a standalone subprocess receipt plugin with no merchant-specific core bridge
- plugin-owned auth lifecycle actions: `start_auth`, `cancel_auth`, `confirm_auth`, `get_auth_status`
- generic shared-browser bootstrap using the public SDK runtime helpers
- plugin-local state under `context.storage`
- fixture-driven parsing and normalization
- plugin-local pytest layout
- desktop receipt-pack ZIP creation that matches Electron pack validation

## Layout

```text
reference_receipt_plugin_template/
  manifest.json
  plugin.py
  README.md
  build_desktop_pack.py
  fixtures/
    raw_records.json
  tests/
    test_reference_template_plugin.py
```

## What to replace first

Replace these reference placeholders with merchant-specific code:

- `start_url` and `callback_url_prefixes` in `plugin.py`
- fixture record loading in `fixtures/raw_records.json`
- receipt discovery/fetch code in `discover_records` and `fetch_record`
- normalization logic in `normalize_record`
- discount extraction logic in `extract_discounts`
- diagnostics fields so they reflect real merchant/runtime concerns

Keep these patterns:

- use `load_plugin_runtime_context()` inside actions
- persist plugin state under `context.storage.data_dir`
- expose auth lifecycle status through the public receipt contract
- return merchant-specific diagnostics from `get_diagnostics`
- keep desktop pack metadata generic and ZIP-based

## Self-hosted local run

Suggested config:

```toml
connector_plugin_search_paths = ["./examples/reference_receipt_plugin_template"]
connector_external_runtime_enabled = true
connector_external_receipt_plugins_enabled = true
connector_external_allowed_trust_classes = ["community_unsigned"]
```

Typical flow:

```bash
lidltool connectors auth status --source-id reference_template_receipt_de --json
lidltool connectors auth bootstrap --source-id reference_template_receipt_de --json
lidltool connectors sync --source-id reference_template_receipt_de --full --json
```

This template intentionally requires auth before sync. The local tests simulate `confirm_auth` by injecting a shared-browser callback result through the public runtime context.

## Plugin-local tests

Run:

```bash
pytest examples/reference_receipt_plugin_template/tests/test_reference_template_plugin.py
```

What they cover:

- plugin-owned auth bootstrap to authenticated state
- full public receipt contract after auth is established
- desktop pack ZIP structure produced by `build_desktop_pack.py`

## Desktop pack build

Build a manual-import ZIP:

```bash
python examples/reference_receipt_plugin_template/build_desktop_pack.py --output-dir /tmp/reference-template-pack
```

The script emits:

- `plugin-pack.json`
- `manifest.json`
- `integrity.json`
- `payload/plugin.py`
- `payload/fixtures/raw_records.json`

No `signature.json` is included because local manual import does not require trusted-signature metadata.

## Desktop import checklist

1. Build the ZIP with `build_desktop_pack.py`.
2. Open LidlTool Desktop and go to the connectors page.
3. Use `Import local pack` and select the generated ZIP.
4. Confirm the pack is shown as `community_unsigned` and initially disabled.
5. Enable the pack.
6. Run the connector auth/bootstrap action and complete the shared browser flow.
7. Run a sync and confirm the connector is visible through generic connector discovery.
8. Disable or uninstall the pack and confirm desktop removes it without touching unrelated connectors.

## Packaging notes

- `manifest.json` stays at the ZIP root.
- Runtime files go under `payload/`.
- the pack builder rewrites the packaged manifest entrypoint to `payload/plugin.py:ReferenceTemplateReceiptPlugin`.
- `plugin-pack.json` declares `manifest_path = "manifest.json"` and `runtime_root = "payload"`.
- `integrity.json` must hash every shipped file in the archive.
- Trusted catalog installs add a detached `signature.json`, but local ZIP import does not.
