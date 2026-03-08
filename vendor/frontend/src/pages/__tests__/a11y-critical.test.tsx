import type * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AutomationsPage } from "@/pages/AutomationsPage";
import { AutomationInboxPage } from "@/pages/AutomationInboxPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DocumentsUploadPage } from "@/pages/DocumentsUploadPage";
import { BillsPage } from "@/pages/BillsPage";
import { ReviewQueuePage } from "@/pages/ReviewQueuePage";
import { ReliabilityPage } from "@/pages/ReliabilityPage";
import { TransactionDetailPage } from "@/pages/TransactionDetailPage";
import { TransactionsPage } from "@/pages/TransactionsPage";
import { runAxeAudit } from "@/test/axe";

function renderRoute(routePath: string, initialEntry: string, element: React.JSX.Element) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path={routePath} element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function expectNoAxeViolations(container: HTMLElement): Promise<void> {
  const report = await runAxeAudit(container);
  expect(report.skipped).toBe(false);
  expect(report.violations).toEqual([]);
}

describe("Critical route accessibility (axe)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = init?.method ?? "GET";

        if (method === "GET" && url.pathname === "/api/v1/dashboard/cards") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                totals: {
                  receipt_count: 12,
                  paid_cents: 12345,
                  paid_currency: "EUR",
                  saved_cents: 876,
                  saved_currency: "EUR",
                  gross_cents: 13221,
                  gross_currency: "EUR",
                  savings_rate: 0.0663
                }
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/dashboard/trends") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                points: []
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/dashboard/savings-breakdown") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                view: "native",
                by_type: []
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/dashboard/retailer-composition") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                retailers: []
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/sources") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                sources: []
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/recurring-bills") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                count: 1,
                total: 1,
                limit: 200,
                offset: 0,
                items: [
                  {
                    id: "bill-1",
                    user_id: "user-1",
                    name: "Netflix",
                    merchant_canonical: "netflix",
                    merchant_alias_pattern: null,
                    category: "subscriptions",
                    frequency: "monthly",
                    interval_value: 1,
                    amount_cents: 1299,
                    amount_tolerance_pct: 0.1,
                    currency: "EUR",
                    anchor_date: "2026-02-12",
                    active: true,
                    notes: null,
                    created_at: "2026-02-01T00:00:00Z",
                    updated_at: "2026-02-01T00:00:00Z"
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/recurring-bills/analytics/overview") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                active_bills: 1,
                due_this_week: 1,
                overdue: 0,
                monthly_committed_cents: 1299,
                status_counts: {
                  upcoming: 1
                },
                currency: "EUR"
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/recurring-bills/analytics/calendar") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                year: 2026,
                month: 2,
                days: [
                  {
                    date: "2026-02-12",
                    items: [
                      {
                        occurrence_id: "occ-1",
                        bill_id: "bill-1",
                        bill_name: "Netflix",
                        status: "upcoming",
                        expected_amount_cents: 1299,
                        actual_amount_cents: null
                      }
                    ],
                    count: 1,
                    total_expected_cents: 1299
                  }
                ],
                count: 1
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/recurring-bills/analytics/forecast") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                months: 3,
                points: [
                  { period: "2026-02", projected_cents: 1299, currency: "EUR" },
                  { period: "2026-03", projected_cents: 1299, currency: "EUR" },
                  { period: "2026-04", projected_cents: 1299, currency: "EUR" }
                ],
                total_projected_cents: 3897,
                currency: "EUR"
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/transactions") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                count: 1,
                total: 1,
                limit: 25,
                offset: 0,
                items: [
                  {
                    id: "tx-1",
                    purchased_at: "2026-02-19T12:00:00Z",
                    source_id: "lidl",
                    source_transaction_id: "source-1",
                    store_name: "Store One",
                    total_gross_cents: 999,
                    discount_total_cents: 150,
                    currency: "EUR"
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/transactions/tx-1") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                transaction: {
                  id: "tx-1",
                  source_id: "lidl",
                  source_transaction_id: "source-1",
                  purchased_at: "2026-02-19T12:00:00Z",
                  merchant_name: "Store One",
                  total_gross_cents: 999,
                  discount_total_cents: 150,
                  raw_payload: {
                    source: "fixture"
                  }
                },
                items: [
                  {
                    id: "item-1",
                    line_no: 1,
                    name: "Milk",
                    qty: 1,
                    unit: "pcs",
                    line_total_cents: 199,
                    category: "dairy"
                  }
                ],
                discounts: [],
                documents: []
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/transactions/tx-1/history") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                transaction_id: "tx-1",
                count: 1,
                events: [
                  {
                    id: "hist-1",
                    created_at: "2026-02-19T12:10:00Z",
                    action: "review.transaction_corrected",
                    actor_id: "qa-user",
                    entity_type: "transaction",
                    details: null
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/review-queue") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                limit: 25,
                offset: 0,
                count: 1,
                total: 1,
                items: [
                  {
                    document_id: "doc-1",
                    transaction_id: "tx-1",
                    source_id: "ocr_upload",
                    review_status: "needs_review",
                    ocr_status: "completed",
                    merchant_name: "Review Store",
                    purchased_at: "2026-02-19T11:59:00Z",
                    total_gross_cents: 449,
                    currency: "EUR",
                    transaction_confidence: 0.7,
                    ocr_confidence: 0.82,
                    created_at: "2026-02-19T12:00:00Z"
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/automations") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                count: 1,
                total: 1,
                limit: 25,
                offset: 0,
                items: [
                  {
                    id: "rule-1",
                    name: "Weekly summary rule",
                    rule_type: "weekly_summary",
                    enabled: true,
                    trigger_config: {
                      schedule: {
                        interval_seconds: 3600
                      }
                    },
                    action_config: {
                      months_back: 3,
                      include_breakdown: true
                    },
                    next_run_at: null,
                    last_run_at: null,
                    created_at: "2026-02-19T12:00:00Z",
                    updated_at: "2026-02-19T12:00:00Z"
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/automations/executions") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                count: 1,
                total: 1,
                limit: 25,
                offset: 0,
                items: [
                  {
                    id: "exec-1",
                    rule_id: "rule-1",
                    rule_name: "Inbox Rule",
                    rule_type: "weekly_summary",
                    status: "success",
                    triggered_at: "2026-02-19T12:01:00Z",
                    executed_at: "2026-02-19T12:01:05Z",
                    result: {
                      template: "Weekly summary template"
                    },
                    error: null,
                    created_at: "2026-02-19T12:01:00Z"
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/reliability/slo") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                generated_at: "2026-02-19T12:00:00Z",
                window_hours: 24,
                thresholds: {
                  sync_p95_target_ms: 2500,
                  analytics_p95_target_ms: 2000,
                  min_success_rate: 0.97
                },
                endpoints: [
                  {
                    route: "/api/v1/documents/upload",
                    count: 20,
                    success_rate: 0.98,
                    error_rate: 0.02,
                    p50_duration_ms: 120,
                    p95_duration_ms: 380,
                    p99_duration_ms: 500
                  }
                ],
                families: {
                  analytics: {
                    routes: 2,
                    p95_duration_ms: 180,
                    avg_success_rate: 0.99,
                    p95_target_ms: 2000,
                    slo_pass: true
                  },
                  sync: {
                    routes: 1,
                    p95_duration_ms: 380,
                    avg_success_rate: 0.98,
                    p95_target_ms: 2500,
                    slo_pass: true
                  }
                }
              },
              warnings: [],
              error: null
            })
          };
        }

        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      })
    );
  });

  it("dashboard has no serious accessibility violations", async () => {
    const { container, getByText } = renderRoute("/", "/", <DashboardPage />);
    await waitFor(() => {
      expect(getByText("Net spend")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });

  it("bills has no serious accessibility violations", async () => {
    const { container, getByText } = renderRoute("/bills", "/bills", <BillsPage />);
    await waitFor(() => {
      expect(getByText("Recurring Bills")).toBeInTheDocument();
      expect(getByText("Netflix")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });

  it("transactions has no serious accessibility violations", async () => {
    const { container, getByText } = renderRoute("/transactions", "/transactions", <TransactionsPage />);
    await waitFor(() => {
      expect(getByText("Store One")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });

  it("review queue has no serious accessibility violations", async () => {
    const { container, getByText } = renderRoute("/review-queue", "/review-queue", <ReviewQueuePage />);
    await waitFor(() => {
      expect(getByText("Review Store")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });

  it("automations has no serious accessibility violations", async () => {
    const { container, getByText } = renderRoute("/automations", "/automations", <AutomationsPage />);
    await waitFor(() => {
      expect(getByText("Weekly summary rule")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });

  it("documents upload has no serious accessibility violations", async () => {
    const { container, getByText } = renderRoute("/documents/upload", "/documents/upload", <DocumentsUploadPage />);
    await waitFor(() => {
      expect(getByText("OCR Document Upload")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });

  it("transaction detail has no serious accessibility violations", async () => {
    const { container, getByText } = renderRoute(
      "/transactions/:transactionId",
      "/transactions/tx-1",
      <TransactionDetailPage />
    );
    await waitFor(() => {
      expect(getByText("Transaction Detail")).toBeInTheDocument();
      expect(getByText("Store One")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });

  it("automation inbox has no serious accessibility violations", async () => {
    const { container, getByText } = renderRoute("/automation-inbox", "/automation-inbox", <AutomationInboxPage />);
    await waitFor(() => {
      expect(getByText("Automation Inbox")).toBeInTheDocument();
      expect(getByText("Inbox Rule")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });

  it("reliability has no serious accessibility violations", async () => {
    const { container, getByText } = renderRoute("/reliability", "/reliability", <ReliabilityPage />);
    await waitFor(() => {
      expect(getByText("Reliability Console")).toBeInTheDocument();
      expect(getByText("/api/v1/documents/upload")).toBeInTheDocument();
    });
    await expectNoAxeViolations(container);
  });
});
