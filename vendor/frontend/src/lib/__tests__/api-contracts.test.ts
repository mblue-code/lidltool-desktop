import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchDashboardCards,
  fetchDashboardTrends,
  fetchRetailerComposition,
  fetchSavingsBreakdown
} from "@/api/dashboard";
import { fetchReliabilitySlo } from "@/api/reliability";
import {
  approveReviewDocument,
  fetchReviewQueue,
  fetchReviewQueueDetail
} from "@/api/reviewQueue";
import { fetchAutomationExecutions, fetchAutomationRules } from "@/api/automations";
import {
  fetchTransactionDetail,
  fetchTransactionHistory,
  fetchTransactions
} from "@/api/transactions";
import { ApiValidationError } from "@/lib/api-errors";
import transactionsDetailFixture from "@/test/fixtures/backend-contracts/transactions-detail.json";
import transactionsHistoryFixture from "@/test/fixtures/backend-contracts/transactions-history.json";
import transactionsListFixture from "@/test/fixtures/backend-contracts/transactions-list.json";

type MockRoute = {
  method: string;
  path: string;
  result: unknown;
  ok?: boolean;
  status?: number;
};

function okEnvelope(result: unknown): Record<string, unknown> {
  return {
    ok: true,
    result,
    warnings: [],
    error: null
  };
}

function stubApiRoutes(routes: MockRoute[]): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      const method = init?.method ?? "GET";
      const route = routes.find((candidate) => candidate.method === method && candidate.path === url.pathname);

      if (!route) {
        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      }

      return {
        ok: route.ok ?? true,
        status: route.status ?? 200,
        json: async () => okEnvelope(route.result)
      };
    })
  );
}

// Values sourced from docs/api/examples/savings_breakdown.example.json
const savingsBreakdownExample: {
  response: {
    result: {
      by_type: Array<{
        type: string;
        saved_cents: number;
        discount_events: number;
      }>;
    };
  };
} = {
  response: {
    result: {
      by_type: [
        {
          type: "lidl_plus",
          discount_events: 31,
          saved_cents: 2710
        }
      ]
    }
  }
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("API contract drift checks", () => {
  it("parses dashboard contracts from representative fixtures", async () => {
    const savingsExampleType = savingsBreakdownExample.response.result.by_type[0];

    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/dashboard/cards",
        result: {
          totals: {
            receipt_count: 8,
            paid_cents: 26_400,
            paid_currency: "EUR",
            saved_cents: 3_200,
            saved_currency: "EUR",
            gross_cents: 29_600,
            gross_currency: "EUR",
            savings_rate: 0.1081
          }
        }
      },
      {
        method: "GET",
        path: "/api/v1/dashboard/trends",
        result: {
          points: [
            {
              year: 2026,
              month: 2,
              period_key: "2026-02",
              paid_cents: 26_400,
              saved_cents: 3_200,
              savings_rate: 0.1081
            }
          ]
        }
      },
      {
        method: "GET",
        path: "/api/v1/dashboard/savings-breakdown",
        result: {
          view: "native",
          by_type: [
            {
              type: savingsExampleType.type,
              saved_cents: savingsExampleType.saved_cents,
              saved_currency: "EUR",
              discount_events: savingsExampleType.discount_events
            }
          ]
        }
      },
      {
        method: "GET",
        path: "/api/v1/dashboard/retailer-composition",
        result: {
          retailers: [
            {
              source_id: "lidl",
              retailer: "Lidl",
              paid_cents: 26_400,
              saved_cents: 3_200,
              paid_share: 1,
              saved_share: 1,
              savings_rate: 0.1081
            }
          ]
        }
      }
    ]);

    const [cards, trends, breakdown, composition] = await Promise.all([
      fetchDashboardCards(2026, 2),
      fetchDashboardTrends(2026, 6, 2),
      fetchSavingsBreakdown(2026, 2, "native"),
      fetchRetailerComposition(2026, 2)
    ]);

    expect({
      cards: cards.totals,
      trendPoints: trends.points.length,
      breakdownTypes: breakdown.by_type.map((entry) => entry.type),
      retailerRows: composition.retailers.length
    }).toMatchInlineSnapshot(`
      {
        "breakdownTypes": [
          "lidl_plus",
        ],
        "cards": {
          "gross_cents": 29600,
          "gross_currency": "EUR",
          "paid_cents": 26400,
          "paid_currency": "EUR",
          "receipt_count": 8,
          "saved_cents": 3200,
          "saved_currency": "EUR",
          "savings_rate": 0.1081,
        },
        "retailerRows": 1,
        "trendPoints": 1,
      }
    `);
  });

  it("fails dashboard parsing on drifted payload keys", async () => {
    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/dashboard/cards",
        result: {
          totals: {
            receipt_count: "8",
            paid_cents: 26_400,
            paid_currency: "EUR",
            saved_cents: 3_200,
            saved_currency: "EUR",
            gross_cents: 29_600,
            gross_currency: "EUR",
            savings_rate: 0.1081
          }
        }
      }
    ]);

    await expect(fetchDashboardCards(2026, 2)).rejects.toBeInstanceOf(ApiValidationError);
  });

  it("parses transactions contracts from backend-realistic fixtures", async () => {
    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/transactions",
        result: transactionsListFixture
      },
      {
        method: "GET",
        path: "/api/v1/transactions/tx-1",
        result: transactionsDetailFixture
      },
      {
        method: "GET",
        path: "/api/v1/transactions/tx-1/history",
        result: transactionsHistoryFixture
      }
    ]);

    const [list, detail, history] = await Promise.all([
      fetchTransactions({ limit: 25, offset: 0 }),
      fetchTransactionDetail("tx-1"),
      fetchTransactionHistory("tx-1")
    ]);

    expect({
      listCount: list.total,
      firstSourceId: list.items[0]?.source_id,
      detailItemCount: detail.items.length,
      historyCount: history.count,
      listItemId: list.items[0]?.id,
      detailDocumentCount: detail.documents.length
    }).toMatchInlineSnapshot(`
      {
        "detailDocumentCount": 1,
        "detailItemCount": 1,
        "firstSourceId": "lidl_plus_de",
        "historyCount": 1,
        "listCount": 2,
        "listItemId": "tx-1",
      }
    `);
  });

  it("fails transactions list parsing when source_id is missing", async () => {
    const drifted = {
      ...transactionsListFixture,
      items: transactionsListFixture.items.map((item, index) =>
        index === 0
          ? {
              ...item,
              source_id: undefined
            }
          : item
      )
    };

    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/transactions",
        result: drifted
      }
    ]);

    await expect(fetchTransactions({ limit: 25, offset: 0 })).rejects.toBeInstanceOf(ApiValidationError);
  });

  it("fails transactions parsing on drifted payload types", async () => {
    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/transactions/tx-1",
        result: {
          transaction: {
            id: "tx-1",
            source_id: "lidl",
            source_transaction_id: "source-1",
            purchased_at: "2026-02-19T09:00:00Z",
            merchant_name: "Store Alpha",
            total_gross_cents: 920,
            discount_total_cents: 120,
            raw_payload: {}
          },
          items: [
            {
              id: "item-1",
              line_no: "1",
              name: "Milk",
              qty: 1,
              unit: "pcs",
              line_total_cents: 199,
              category: "grocery"
            }
          ],
          discounts: [],
          documents: []
        }
      }
    ]);

    await expect(fetchTransactionDetail("tx-1")).rejects.toBeInstanceOf(ApiValidationError);
  });

  it("parses review queue contracts and rejects drifted payloads", async () => {
    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/review-queue",
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
              merchant_name: "Store Alpha",
              purchased_at: "2026-02-19T09:00:00Z",
              total_gross_cents: 920,
              currency: "EUR",
              transaction_confidence: 0.7,
              ocr_confidence: 0.82,
              created_at: "2026-02-19T12:00:00Z"
            }
          ]
        }
      },
      {
        method: "GET",
        path: "/api/v1/review-queue/doc-1",
        result: {
          document: {
            id: "doc-1",
            transaction_id: "tx-1",
            source_id: "ocr_upload",
            review_status: "needs_review",
            ocr_status: "completed",
            file_name: "receipt.png",
            mime_type: "image/png",
            storage_uri: "file:///tmp/receipt.png",
            ocr_provider: "external_api",
            ocr_confidence: 0.82,
            ocr_fallback_used: false,
            ocr_latency_ms: 300,
            ocr_text: "receipt text",
            created_at: "2026-02-19T12:00:00Z",
            processed_at: "2026-02-19T12:01:00Z"
          },
          transaction: {
            id: "tx-1",
            source_id: "ocr_upload",
            source_transaction_id: "source-1",
            purchased_at: "2026-02-19T11:59:00Z",
            merchant_name: "Store Alpha",
            total_gross_cents: 920,
            currency: "EUR",
            discount_total_cents: null,
            confidence: 0.7,
            raw_payload: {}
          },
          items: [],
          confidence: {
            transaction_confidence: 0.7
          }
        }
      },
      {
        method: "POST",
        path: "/api/v1/review-queue/doc-1/approve",
        result: {
          document_id: "doc-1",
          review_status: "approved"
        }
      }
    ]);

    await expect(fetchReviewQueue({ limit: 25, offset: 0 })).resolves.toMatchObject({ total: 1 });
    await expect(fetchReviewQueueDetail("doc-1")).resolves.toMatchObject({
      document: { id: "doc-1" }
    });
    await expect(approveReviewDocument("doc-1", { actor_id: "qa" })).resolves.toMatchObject({
      review_status: "approved"
    });

    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/review-queue",
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
              merchant_name: "Store Alpha",
              purchased_at: "2026-02-19T09:00:00Z",
              total_gross_cents: "920",
              currency: "EUR",
              transaction_confidence: 0.7,
              ocr_confidence: 0.82,
              created_at: "2026-02-19T12:00:00Z"
            }
          ]
        }
      }
    ]);

    await expect(fetchReviewQueue({ limit: 25, offset: 0 })).rejects.toBeInstanceOf(ApiValidationError);
  });

  it("parses automations and reliability contracts and rejects drifted payloads", async () => {
    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/automations",
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
        }
      },
      {
        method: "GET",
        path: "/api/v1/automations/executions",
        result: {
          count: 1,
          total: 1,
          limit: 25,
          offset: 0,
          items: [
            {
              id: "exec-1",
              rule_id: "rule-1",
              rule_name: "Weekly summary rule",
              rule_type: "weekly_summary",
              status: "success",
              triggered_at: "2026-02-19T12:10:00Z",
              executed_at: "2026-02-19T12:10:02Z",
              result: {
                summary: "ok"
              },
              error: null,
              created_at: "2026-02-19T12:10:00Z"
            }
          ]
        }
      },
      {
        method: "GET",
        path: "/api/v1/reliability/slo",
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
              route: "/api/v1/transactions",
              count: 100,
              success_rate: 0.99,
              error_rate: 0.01,
              p50_duration_ms: 45,
              p95_duration_ms: 120,
              p99_duration_ms: 200
            }
          ],
          families: {
            analytics: {
              routes: 4,
              p95_duration_ms: 180,
              avg_success_rate: 0.99,
              p95_target_ms: 2000,
              slo_pass: true
            }
          }
        }
      }
    ]);

    await expect(fetchAutomationRules(25, 0)).resolves.toMatchObject({ total: 1 });
    await expect(fetchAutomationExecutions({ limit: 25, offset: 0 })).resolves.toMatchObject({ total: 1 });
    await expect(fetchReliabilitySlo({ windowHours: 24 })).resolves.toMatchObject({ window_hours: 24 });

    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/automations",
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
              enabled: "true",
              trigger_config: {},
              action_config: {},
              next_run_at: null,
              last_run_at: null,
              created_at: "2026-02-19T12:00:00Z",
              updated_at: "2026-02-19T12:00:00Z"
            }
          ]
        }
      }
    ]);

    await expect(fetchAutomationRules(25, 0)).rejects.toBeInstanceOf(ApiValidationError);

    stubApiRoutes([
      {
        method: "GET",
        path: "/api/v1/reliability/slo",
        result: {
          generated_at: "2026-02-19T12:00:00Z",
          window_hours: 24,
          thresholds: {
            sync_p95_target_ms: 2500,
            analytics_p95_target_ms: "2000",
            min_success_rate: 0.97
          },
          endpoints: [],
          families: {}
        }
      }
    ]);

    await expect(fetchReliabilitySlo({ windowHours: 24 })).rejects.toBeInstanceOf(ApiValidationError);
  });
});
