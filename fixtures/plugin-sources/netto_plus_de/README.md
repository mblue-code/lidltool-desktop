# Netto Plus External Plugin

This plugin implements Netto Plus as an external receipt plugin for the public
plugin runtime. It targets the Edeka-linked Netto Plus product at
`netto-online.de`, not `netto.de`.

## Current desktop bootstrap model

Netto Plus digital receipts are app-backed. During the investigation for this
plugin, the Android flow authenticated successfully, but host-side desktop
browser login and host-side receipt API calls were blocked by the anti-bot path
used by `sso.netto-online.de` and `clickforbrand.de`.

The desktop-targeted bootstrap therefore imports a JSON session bundle captured
from the Android receipt flow instead of pretending that a normal desktop web
login works today.

This is intended to be a user-supplied bundle model:

- every user installs the same plugin ZIP
- every user imports their own Netto Plus Android session bundle
- the desktop plugin then syncs and normalizes receipts from that bundle

Reference docs for producing those bundles are in:

- [docs/ADVANCED_USER_QUICKSTART.md](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/docs/ADVANCED_USER_QUICKSTART.md)
- [docs/SESSION_BUNDLE_EXPORT_AGENT_PROMPT.md](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/docs/SESSION_BUNDLE_EXPORT_AGENT_PROMPT.md)
- [docs/ANDROID_SESSION_BUNDLE_WORKFLOW.md](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/docs/ANDROID_SESSION_BUNDLE_WORKFLOW.md)
- [examples/netto-session-bundle.redacted.json](/Volumes/macminiExtern/lidl-receipts-cli/plugins/netto_plus_de/examples/netto-session-bundle.redacted.json)

## Session bundle format

The connector expects a JSON file with this shape:

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

`pdf_text` can be used instead of `pdf_payload` for offline tests.

The session bundle contract is intentionally simple so that multiple future
bootstrap paths can target the same desktop import model:

- Android agent/export flow
- future Android helper app
- future iPhone export path
- future official export or partner integration, if one becomes available

## Bundle validation helper

Before importing a user-generated bundle into desktop, validate it locally:

```bash
uv run python plugins/netto_plus_de/validate_session_bundle.py /absolute/path/to/netto-session-bundle.json
```

For machine-readable output:

```bash
uv run python plugins/netto_plus_de/validate_session_bundle.py /absolute/path/to/netto-session-bundle.json --json
```

The validator checks the bundle shape and then dry-runs the Netto parser and
normalizer against every receipt in the bundle.

## Parser notes

The Netto receipt parser uses the PDF payload because the public history API
only returns receipt summaries. The parser currently handles:

- repeated quantity blocks such as `2 x 0,89`
- weighted items such as `0,329 kg 27,90 EUR/kg`
- item-level discounts such as `GRATIS -0,99` and `Rabatt 30% -1,59`
- transaction discounts such as `5€ Rabatt Warenkorb -5,00`
- deposit/refund rows such as `Einwegleergut 19% -0,25`

The normalized transaction total comes from the captured Netto history payload.
The normalized `discount_total_cents` intentionally follows Netto's reported
`Ersparnis` value from the app API, which can differ from the sum of every
negative line printed on the PDF.
