# Mobile Foundation Fork

This directory vendors the upstream native mobile harnesses from the old self-hosted repo as a starting point for a desktop-paired mobile product.

Source:
- upstream repo: `/Volumes/macminiExtern/lidl-receipts-cli`
- upstream paths:
  - `apps/android-harness`
  - `apps/ios-harness`

Sync method:
- run `npm run vendor:sync:mobile`
- override the source checkout with `-- --source-repo /path/to/repo` or `LIDLTOOL_UPSTREAM_REPO=/path/to/repo`

What is intentionally included now:
- native app scaffolding and project files
- pairing-first Android and iOS shells
- local session/device persistence patterns
- app-private capture queues for receipt images/PDFs
- explicit foreground sync clients for the desktop mobile protocol
- local transaction and budget-summary read models

What is intentionally not solved yet:
- polished desktop QR-pairing UI
- local LAN discovery beyond the endpoint carried in the pairing payload
- native camera capture
- conflict resolution for future mobile write models
- manual expense/category edit sync

These apps are currently vendored native companion foundations. They build from local paths inside this repo, but they are not packaged inside the Electron desktop installer.
