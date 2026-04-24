# Netto Plus Session Bundle Export Prompt

Use this prompt for another agent when the goal is to produce a **user-owned**
Netto Plus session bundle that the desktop plugin can import.

## Why This Exists

The desktop plugin already supports importing a user-supplied
`session_bundle_file`. What is still manual is generating that bundle from the
user's own Netto Plus app session in a repeatable way.

This prompt is for that export job. It is not for adding a built-in connector,
and it is not for bypassing website bot defenses.

## Prompt Template

````md
You are working on the Netto Plus Android export flow.

Goal:
Produce a valid Netto Plus session bundle JSON for the user's own account so it
can be imported into the external desktop plugin at
`plugins/netto_plus_de`.

Constraints:
- Target the Edeka-linked Netto Plus product at `netto-online.de`, not `netto.de`.
- Do not add Netto as a built-in connector.
- Do not work on desktop web login or anti-bot bypassing.
- Use the user's own Android device or Android emulator session.
- Do not commit credentials, raw secrets, or personal receipt payloads into git.
- Save outputs only to an operator-provided local path.

Primary task:
Log into the real Netto Plus Android app with the user's own credentials,
inspect the authenticated receipt flow, and export a bundle in the exact format
required by the desktop plugin.

Expected output file:
- a JSON file named `netto-session-bundle.json`

Required bundle contract:
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

Bundle requirements:
- `schema_version` must be `"1"`
- `account.email` should contain the authenticated account identifier if known
- `receipts` must be a non-empty list
- each receipt must contain:
  - `summary`
  - either `pdf_payload` or `pdf_text`
- prefer `pdf_payload` whenever possible

Investigation workflow:
1. Use Android tooling first.
2. Install or open the real Netto Plus Android app.
3. Log into the user's account.
4. Inspect the receipt history flow.
5. Capture the receipt summary payloads.
6. Capture the receipt PDF payloads or equivalent receipt-detail payloads.
7. Build one local `netto-session-bundle.json` file matching the contract above.
8. Validate that the bundle contains real receipts and can be parsed locally.

Validation requirements:
- Verify at least one receipt exists in the bundle.
- Verify every receipt has a stable unique `BonId`.
- Verify the receipt date parses as ISO-8601.
- Verify `Bonsumme` and `Ersparnis` are numeric.
- Verify `pdf_payload.content` base64-decodes cleanly if present.

Preferred deliverables:
- `netto-session-bundle.json`
- short operator note describing:
  - which Android environment was used
  - where the bundle was saved
  - how many receipts were exported
  - whether PDF payloads were included
- validator output from:
  - `uv run python plugins/netto_plus_de/validate_session_bundle.py /path/to/netto-session-bundle.json --json`

Do not:
- store credentials in repo files
- commit personal bundle files
- replace the desktop plugin auth model
- attempt web anti-bot bypassing

Reference:
- `plugins/netto_plus_de/README.md`
- `plugins/netto_plus_de/docs/ANDROID_SESSION_BUNDLE_WORKFLOW.md`
````

## Critical Notes

A detailed prompt alone is not enough. The important part is that the agent
must target a stable output contract. The desktop plugin already expects a
specific bundle structure, so any export flow must preserve that exact shape.

That is why this prompt is paired with the workflow/reference doc rather than
acting as free-form guidance.
