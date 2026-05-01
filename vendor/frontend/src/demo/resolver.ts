import {
  demoAIAgentConfig,
  demoAISettings,
  demoAuth,
  demoChatMessages,
  demoChatThreads,
  demoConnectorSyncStatuses,
  demoConnectors,
  demoDashboardCards,
  demoDashboardTrends,
  demoDepositAnalytics,
  demoProductDetails,
  demoProductPurchases,
  demoProducts,
  demoProductSeries,
  demoRecurringCalendar,
  demoRecurringForecast,
  demoRetailerComposition,
  demoReportPatterns,
  demoReportTemplates,
  demoReviewQueueDetails,
  demoReviewQueueList,
  demoSavingsBreakdown,
  demoSources,
  demoTransactionDetails,
  demoTransactionHistories,
  demoTransactionFacets,
  demoTransactionsList
} from "@/demo/fixtures";

export type DemoResolvedResponse = {
  status: number;
  body: unknown;
};

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function ok(body: unknown): DemoResolvedResponse {
  return {
    status: 200,
    body: deepClone(body)
  };
}

export function resolveDemoRequest(method: string, url: URL): DemoResolvedResponse | null {
  const normalizedMethod = method.toUpperCase();
  const { pathname } = url;

  if (normalizedMethod === "GET" && pathname === "/api/v1/auth/setup-required") return ok(demoAuth.setupRequired);
  if (normalizedMethod === "GET" && pathname === "/api/v1/auth/me") return ok(demoAuth.me);
  if (normalizedMethod === "POST" && pathname === "/api/v1/auth/logout") return ok(demoAuth.logout);

  if (normalizedMethod === "GET" && pathname === "/api/v1/settings/ai") return ok(demoAISettings);
  if (normalizedMethod === "GET" && pathname === "/api/v1/settings/ai/agent-config") return ok(demoAIAgentConfig);

  if (normalizedMethod === "GET" && pathname === "/api/v1/connectors") return ok(demoConnectors);
  if (normalizedMethod === "GET" && pathname.startsWith("/api/v1/connectors/") && pathname.endsWith("/sync/status")) {
    const sourceId = pathname.split("/")[4] ?? "";
    return ok(demoConnectorSyncStatuses[sourceId as keyof typeof demoConnectorSyncStatuses] ?? {
      ok: true,
      result: {
        source_id: sourceId,
        status: "idle",
        command: null,
        pid: null,
        started_at: null,
        finished_at: null,
        return_code: null,
        output_tail: [],
        can_cancel: false
      },
      warnings: [],
      error: null,
      error_code: null
    });
  }

  if (normalizedMethod === "GET" && pathname === "/api/v1/sources") return ok(demoSources);
  if (normalizedMethod === "GET" && pathname === "/api/v1/dashboard/cards") return ok(demoDashboardCards);
  if (normalizedMethod === "GET" && pathname === "/api/v1/dashboard/trends") return ok(demoDashboardTrends);
  if (normalizedMethod === "GET" && pathname === "/api/v1/dashboard/savings-breakdown") return ok(demoSavingsBreakdown);
  if (normalizedMethod === "GET" && pathname === "/api/v1/dashboard/retailer-composition") return ok(demoRetailerComposition);
  if (normalizedMethod === "GET" && pathname === "/api/v1/analytics/deposits") return ok(demoDepositAnalytics);
  if (normalizedMethod === "GET" && pathname === "/api/v1/recurring-bills/analytics/calendar") return ok(demoRecurringCalendar);
  if (normalizedMethod === "GET" && pathname === "/api/v1/recurring-bills/analytics/forecast") return ok(demoRecurringForecast);

  if (normalizedMethod === "GET" && pathname === "/api/v1/transactions") return ok(demoTransactionsList);
  if (normalizedMethod === "GET" && pathname === "/api/v1/transactions/facets") return ok(demoTransactionFacets);
  if (normalizedMethod === "GET" && pathname.startsWith("/api/v1/transactions/") && pathname.endsWith("/history")) {
    const transactionId = pathname.split("/")[4] ?? "";
    return ok(demoTransactionHistories[transactionId as keyof typeof demoTransactionHistories] ?? demoTransactionHistories["tx-demo-1"]);
  }
  if (normalizedMethod === "GET" && pathname.startsWith("/api/v1/transactions/")) {
    const transactionId = pathname.split("/")[4] ?? "";
    return ok(demoTransactionDetails[transactionId as keyof typeof demoTransactionDetails] ?? demoTransactionDetails["tx-demo-1"]);
  }

  if (normalizedMethod === "GET" && pathname === "/api/v1/products") return ok(demoProducts);
  if (normalizedMethod === "GET" && pathname.startsWith("/api/v1/products/") && pathname.endsWith("/price-series")) {
    const productId = pathname.split("/")[4] ?? "";
    return ok(demoProductSeries[productId as keyof typeof demoProductSeries] ?? demoProductSeries["prod-gouda"]);
  }
  if (normalizedMethod === "GET" && pathname.startsWith("/api/v1/products/") && pathname.endsWith("/purchases")) {
    const productId = pathname.split("/")[4] ?? "";
    return ok(demoProductPurchases[productId as keyof typeof demoProductPurchases] ?? demoProductPurchases["prod-gouda"]);
  }
  if (normalizedMethod === "GET" && pathname.startsWith("/api/v1/products/")) {
    const productId = pathname.split("/")[4] ?? "";
    return ok(demoProductDetails[productId as keyof typeof demoProductDetails] ?? demoProductDetails["prod-gouda"]);
  }

  if (normalizedMethod === "GET" && pathname === "/api/v1/review-queue") return ok(demoReviewQueueList);
  if (normalizedMethod === "GET" && pathname.startsWith("/api/v1/review-queue/")) {
    const documentId = pathname.split("/")[4] ?? "";
    return ok(demoReviewQueueDetails[documentId as keyof typeof demoReviewQueueDetails] ?? demoReviewQueueDetails["doc-review-1"]);
  }

  if (normalizedMethod === "GET" && pathname === "/api/v1/chat/threads") return ok(demoChatThreads);
  if (normalizedMethod === "GET" && pathname.startsWith("/api/v1/chat/threads/") && pathname.endsWith("/messages")) {
    const threadId = pathname.split("/")[5] ?? "";
    return ok(demoChatMessages[threadId as keyof typeof demoChatMessages] ?? demoChatMessages["thread-spend"]);
  }

  if (normalizedMethod === "GET" && pathname === "/api/v1/reports/templates") return ok(demoReportTemplates);
  if (normalizedMethod === "GET" && pathname === "/api/v1/reports/patterns") return ok(demoReportPatterns);

  return null;
}
