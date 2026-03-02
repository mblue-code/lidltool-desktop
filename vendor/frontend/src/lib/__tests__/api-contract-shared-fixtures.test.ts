import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchDashboardCards,
  fetchDashboardTrends,
  fetchRetailerComposition,
  fetchSavingsBreakdown
} from "@/api/dashboard";
import { fetchReliabilitySlo } from "@/api/reliability";
import { fetchReviewQueue, fetchReviewQueueDetail } from "@/api/reviewQueue";
import { fetchAutomationExecutions, fetchAutomationRules } from "@/api/automations";
import { fetchTransactionDetail, fetchTransactionHistory, fetchTransactions } from "@/api/transactions";
import sharedFixtureData from "@/test/fixtures/backend-contracts/api-contract-fixtures.shared.json";

type SharedFixtureEntry = {
  method: string;
  path: string;
  status_code: number;
  response: unknown;
};

type SharedFixtureFile = {
  fixtures: Record<string, SharedFixtureEntry>;
};

function loadSharedFixtures(): SharedFixtureFile {
  return sharedFixtureData as SharedFixtureFile;
}

function stubFromSharedFixtures(fixtures: Record<string, SharedFixtureEntry>): void {
  const byRoute = new Map<string, SharedFixtureEntry>();
  for (const value of Object.values(fixtures)) {
    byRoute.set(`${value.method.toUpperCase()} ${value.path}`, value);
  }

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      const method = (init?.method ?? "GET").toUpperCase();
      const route = byRoute.get(`${method} ${url.pathname}`);
      if (!route) {
        throw new Error(`Unexpected request in shared fixture test: ${method} ${url.pathname}`);
      }
      return {
        ok: route.status_code >= 200 && route.status_code < 300,
        status: route.status_code,
        json: async () => route.response
      };
    })
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("API contracts from shared backend fixtures", () => {
  it("parses frontend adapters against backend-generated fixture corpus", async () => {
    const shared = loadSharedFixtures();
    stubFromSharedFixtures(shared.fixtures);

    const txFixture = shared.fixtures.transactions_list.response as {
      result: { items: Array<{ id: string }> };
    };
    const reviewFixture = shared.fixtures.review_queue_list.response as {
      result: { items: Array<{ document_id: string }> };
    };
    const transactionId = txFixture.result.items[0].id;
    const reviewDocumentId = reviewFixture.result.items[0].document_id;

    const [
      cards,
      trends,
      savings,
      composition,
      transactions,
      detail,
      history,
      reviewList,
      reviewDetail,
      automationRules,
      automationExecutions,
      reliability
    ] = await Promise.all([
      fetchDashboardCards(2026, 2),
      fetchDashboardTrends(2026, 2, 2),
      fetchSavingsBreakdown(2026, 2, "native"),
      fetchRetailerComposition(2026, 2),
      fetchTransactions({ year: 2026, month: 2, limit: 25, offset: 0 }),
      fetchTransactionDetail(transactionId),
      fetchTransactionHistory(transactionId),
      fetchReviewQueue({ limit: 25, offset: 0 }),
      fetchReviewQueueDetail(reviewDocumentId),
      fetchAutomationRules(25, 0),
      fetchAutomationExecutions({ limit: 25, offset: 0 }),
      fetchReliabilitySlo({ windowHours: 24 })
    ]);

    expect(cards.totals.receipt_count).toBeGreaterThan(0);
    expect(trends.points.length).toBeGreaterThan(0);
    expect(savings.by_type.length).toBeGreaterThan(0);
    expect(composition.retailers[0]?.source_id).toBe("lidl_plus_de");
    expect(transactions.items[0]?.source_id).toBe("lidl_plus_de");
    expect(detail.transaction.id).toBe(transactionId);
    expect(history.transaction_id).toBe(transactionId);
    expect(reviewList.items[0]?.document_id).toBe(reviewDocumentId);
    expect(reviewDetail.document.id).toBe(reviewDocumentId);
    expect(automationRules.items.length).toBeGreaterThan(0);
    expect(automationExecutions.items.length).toBeGreaterThan(0);
    expect(reliability.window_hours).toBe(24);
  });
});
