# Netto Plus Android Session Bundle Workflow

This document records the workflow used to derive the current desktop import
model for the external Netto Plus plugin.

It is a reference for future operators or agents that need to export a
user-owned Netto Plus session bundle.

## Scope

- Correct target: Netto Plus / `netto-online.de`
- Wrong target: `netto.de`
- Plugin model: external plugin only
- Desktop auth model: import a user-supplied Android session bundle

## Why The Plugin Uses Bundle Import

The receipt flow is app-backed. During the original investigation, Android app
login and receipt retrieval were feasible, but host-side desktop login and
host-side replay of the same flow were not reliable enough to treat as a normal
desktop credential login.

The practical desktop model is therefore:

1. authenticate in the real Android app
2. export the user's own receipt/session bundle
3. import that bundle into the desktop plugin
4. let the plugin parse and normalize the captured receipts

## Android Environment Used

Local Android tooling on this machine:

- SDK root: `/Users/maximilianblucher/Library/Android/sdk`
- Emulator: `/Users/maximilianblucher/Library/Android/sdk/emulator/emulator`
- ADB: `/Users/maximilianblucher/Library/Android/sdk/platform-tools/adb`

Useful emulator notes:

- reusable rooted AVD: `Pixel_6`
- normal non-rooted AVD: `Pixel_9_Pro`
- AVD storage root: `~/.android/avd`
- resolved AVD storage path: `/Volumes/macminiExtern/DevData/Android/avd`

Useful commands:

```bash
/Users/maximilianblucher/Library/Android/sdk/emulator/emulator -avd Pixel_6
/Users/maximilianblucher/Library/Android/sdk/platform-tools/adb devices -l
/Users/maximilianblucher/Library/Android/sdk/platform-tools/adb -s emulator-5556 root
/Users/maximilianblucher/Library/Android/sdk/platform-tools/adb -s emulator-5556 emu avd name
```

## App Identity

Observed Android package:

- `com.valuephone.vpnetto`

Observed service families during the investigation:

- `https://sso.netto-online.de/oauth`
- `https://www.clickforbrand.de/aia/`
- `https://www.clickforbrand.de/appservice/`

These findings explain the product boundary, but the desktop plugin does not
depend on replaying those login flows directly.

## Export Target

The export job should produce one JSON file for the user's own account:

- `netto-session-bundle.json`

The current plugin expects this shape:

```json
{
  "schema_version": "1",
  "account": {
    "email": "user@example.com"
  },
  "receipts": [
    {
      "summary": {
        "BonId": "8640333292129767634134",
        "Einkaufsdatum": "2026-03-13T10:45:27.920+01:00",
        "Bonsumme": 19.92,
        "Ersparnis": 5.99,
        "Filiale": {
          "FilialNummer": "2459",
          "Bezeichnung": "Calberlah-Windmühlenweg 2",
          "Strasse": "Windmühlenweg 2",
          "Plz": "38547",
          "Ort": "Calberlah"
        }
      },
      "pdf_payload": {
        "content": "<base64 pdf>",
        "mimeType": "application/pdf",
        "filename": "receipt.pdf"
      }
    }
  ]
}
```

Notes:

- `receipts` must not be empty
- every receipt must include `summary`
- prefer `pdf_payload`
- `pdf_text` is acceptable only as a fallback for offline parsing or tests

## Practical Export Workflow

1. Start an Android environment.
   Use either a real user device or the rooted `Pixel_6` emulator.

2. Open the real Netto Plus app.
   Confirm the app is the Netto Plus / Edeka-linked product, not `netto.de`.

3. Log into the user's own account.
   Never store credentials in repo files or commit them.

4. Navigate to receipt history.
   Confirm at least one digital receipt is present.

5. Capture receipt summaries.
   Export or reconstruct the fields needed for each receipt `summary`.

6. Capture receipt detail content.
   Prefer the PDF payload used by the app flow, because the plugin parser uses
   the PDF content for line-item parsing.

7. Assemble the session bundle JSON.
   One file should contain the account identifier and the receipt list.

8. Validate the bundle locally.
   Check that:
   - the JSON is valid
   - `schema_version` is `"1"`
   - every receipt has `BonId`
   - every receipt has a parseable `Einkaufsdatum`
   - `pdf_payload.content` decodes cleanly if present

9. Import the bundle into desktop.
   In the desktop app, configure the Netto Plus connector with the absolute path
   to `netto-session-bundle.json`.

10. Validate the bundle before import if possible.
    Run:

```bash
uv run python plugins/netto_plus_de/validate_session_bundle.py /absolute/path/to/netto-session-bundle.json
```

## Normalization Rules Observed During The Real Investigation

The current parser in `plugin.py` was based on real Netto receipt data and
currently handles:

- repeated quantity blocks such as `2 x 0,89`
- weighted items such as `0,329 kg 27,90 EUR/kg`
- item-level negative lines such as `GRATIS -0,99`
- markdown lines such as `Rabatt 30% -1,59`
- basket discounts such as `5€ Rabatt Warenkorb -5,00`
- deposit/refund rows such as `Einwegleergut 19% -0,25`

Important savings rule:

- `discount_total_cents` follows the Netto app/API `Ersparnis`
- it does **not** blindly sum every negative line printed in the receipt PDF

## Known Limits

- This is not a fully self-serve desktop email/password login flow.
- Each user needs a bundle derived from their own Netto Plus account.
- Bundles may expire, become stale, or need regeneration after app/session
  changes.
- This workflow is Android-first today. It is not yet a universal iPhone path.

## Recommended Operator Output

For a successful export job, the operator or agent should hand back:

- path to `netto-session-bundle.json`
- number of receipts exported
- whether `pdf_payload` was included
- any reason the bundle might need refresh soon

## Related Files

- [README.md](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/README.md)
- [plugin.py](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/plugin.py)
- [SESSION_BUNDLE_EXPORT_AGENT_PROMPT.md](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/docs/SESSION_BUNDLE_EXPORT_AGENT_PROMPT.md)
