# Publication Checklist

This checklist is for the first public GitHub launch and the later paid binary launch.

## Repository Readiness

- add a root `LICENSE`
- confirm `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, and `PRIVACY.md` match the current product behavior
- confirm public docs link only to stable, current workflows
- remove or clearly classify stale internal planning material
- verify issue templates, repository description, homepage URL, and topics before going public

## Product Readiness

- validate fresh install, upgrade, backup, restore, export, and diagnostics flows on macOS and Windows
- verify the packaged app runs without depending on any path outside this repo
- verify update checks are disabled cleanly when no feed is configured
- verify signed release artifacts once signing is finalized

## Commercial Distribution Readiness

- decide what the paid offering includes beyond public source code, such as signed binaries, convenience installers, direct support, or curated connector packs
- document the purchase, delivery, support, and refund flow on the sales website
- make sure commercial delivery does not require private code to exist outside the public repo unless intentionally separated and documented

## Security And Privacy Readiness

- confirm diagnostics redaction still matches the implementation
- keep DSNs, signing credentials, tokens, and private infrastructure out of git
- publish a real security reporting contact path before the public launch
- verify the public repo boundary rules in `docs/public-repo-boundary.md`

## Current Known Blockers

- no root `LICENSE` file yet
- signing and notarization are still documented as deferred
- final clean-machine release validation has not been documented as complete
