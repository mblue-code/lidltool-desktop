# Contributing

Install and check from the repo root:

```bash
npm ci
npm run typecheck
npm run build
```

Desktop is a standalone side repo. Do not add runtime or build-time dependencies on `../../` paths, and do not import or execute code from the main repo at runtime. If shared logic is needed, vendor or copy it into this repo and document the source and sync method.

Before opening a PR:

- run relevant tests, including `npm run test:diagnostics`, `npm run test:runtime-contracts`, `npm run test:updates`, and `npm run test:release-preflight` when touching release/update code
- keep diagnostics bundles, `.env` files, keys, tokens, DSNs, private URLs, source-map tokens, and credentials out of git
- update `README.md` or `docs/` when workflows, packaging, update behavior, diagnostics, or privacy behavior changes
- run `git diff --check`

Diagnostics and telemetry changes must stay privacy-conservative: personal receipt data, credentials, local databases, document storage, scraped retailer HTML, screenshots, and AI chat content must not be collected automatically.
