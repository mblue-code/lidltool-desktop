# Frontend Dashboard

React + TypeScript frontend for Lidl receipts analytics and operations workflows.

## Stack

- Vite
- React 18
- React Router
- TanStack Query
- Tailwind CSS v4 + shadcn/ui
- Vitest + Testing Library

## Local Setup

```bash
cd frontend
npm install
```

Start development server:

```bash
VITE_DASHBOARD_API_BASE=http://127.0.0.1:8000 \
VITE_DASHBOARD_DB=~/.local/share/lidltool/db.sqlite \
npm run dev
```

Build production bundle:

```bash
npm run build
```

## Environment Variables

- `VITE_DASHBOARD_API_BASE`: Backend base URL. Required outside local defaults.
- `VITE_DASHBOARD_DB`: Optional db path query passthrough used in local workflows.
- `VITE_OPENCLAW_API_KEY`: Optional API key header for auth-enforced backend modes.

## Test and Quality Gates

Run frontend tests:

```bash
npm test
```

Run accessibility-focused Vitest checks (axe):

```bash
npm run test:a11y
```

Run Playwright smoke E2E:

```bash
npm run test:e2e
```

Install browser runtime once for Playwright:

```bash
npx playwright install chromium
```

Run the full Phase 6 quality gate:

```bash
npm run quality:phase6
```

Phase 6 hardening baseline includes:

- Route-level lazy loading with suspense fallback.
- Route prefetch on navigation hover/focus.
- Global React error boundary fallback.
- Accessibility improvements in shell navigation and form control labeling.
- Expanded unit/integration coverage for shell/error-boundary behavior.
- Smoke E2E coverage for dashboard, overrides, review approval, and automation run.
- Axe-based critical page accessibility smoke checks.

## Release Runbook (Frontend)

1. Run `npm run build` and `npm test`.
2. Verify core routes load: dashboard, transactions, documents, review queue, automations, inbox, reliability.
3. Verify mutation flows manually:
   - Transaction override save.
   - Review approve/reject.
   - Document upload + process.
4. Confirm `VITE_DASHBOARD_API_BASE` and `VITE_DASHBOARD_DB` are set correctly for target environment.
