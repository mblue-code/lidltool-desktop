# Netto Plus Advanced User Quickstart

This connector is currently an advanced-user beta.

It does **not** support normal desktop email/password login. Instead:

1. install the external Netto Plus plugin ZIP
2. generate your own Netto Plus Android session bundle
3. validate that bundle locally
4. import the bundle into the desktop app
5. run sync

## Requirements

- Outlays desktop app
- imported Netto Plus plugin ZIP
- your own Netto Plus account
- Android device or Android emulator access
- local repo checkout if you want to run the validator from this repository

## Step 1: Produce Your Own Bundle

Create a file named:

- `netto-session-bundle.json`

Use these docs as reference:

- [SESSION_BUNDLE_EXPORT_AGENT_PROMPT.md](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/docs/SESSION_BUNDLE_EXPORT_AGENT_PROMPT.md)
- [ANDROID_SESSION_BUNDLE_WORKFLOW.md](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/docs/ANDROID_SESSION_BUNDLE_WORKFLOW.md)

If you want a shape reference first, look at:

- [netto-session-bundle.redacted.json](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/examples/netto-session-bundle.redacted.json)

## Step 2: Validate The Bundle

Run:

```bash
uv run python plugins/netto_plus_de/validate_session_bundle.py /absolute/path/to/netto-session-bundle.json
```

For JSON output:

```bash
uv run python plugins/netto_plus_de/validate_session_bundle.py /absolute/path/to/netto-session-bundle.json --json
```

What success means:

- the JSON shape is valid
- the bundle contains at least one receipt
- dates and money fields parse correctly
- PDF payloads decode if present
- the Netto parser can dry-run the receipts successfully

## Step 3: Import Into Desktop

In the desktop app:

1. import the Netto Plus plugin ZIP
2. enable the connector
3. open `Set up`
4. set `Netto Plus session bundle` to the absolute path of your bundle file
5. save and continue

If setup succeeds, the connector should report that the Netto Plus bundle is
stored locally.

## Step 4: Sync

After setup:

1. click `Import receipts`
2. wait for sync to finish
3. check the Receipts page for imported Netto Plus transactions

## Expected Limits

- this is Android-assisted today
- each user needs their own bundle
- bundles can expire or become stale
- iPhone-only users are not covered by this flow yet

## If Something Fails

- rerun the validator first
- confirm the bundle path is absolute
- confirm the bundle contains `summary` plus `pdf_payload` or `pdf_text`
- regenerate the bundle if the source session is stale
