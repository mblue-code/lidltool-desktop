import { AgentTool } from "@mariozechner/pi-agent-core";
import { Type } from "@sinclair/typebox";
import { z } from "zod";

import { fetchDashboardCards, fetchDashboardTrends, fetchSavingsBreakdown } from "@/api/dashboard";
import {
  fetchProductPriceSeries,
  fetchProducts,
  postClusterProducts
} from "@/api/products";
import {
  fetchRecurringBills,
  fetchRecurringForecast,
  fetchRecurringGaps,
  fetchRecurringOverview
} from "@/api/recurringBills";
import { CHAT_UI_COMPONENT_NAMES, parseChatUiSpec } from "@/chat/ui/spec";
import { fetchTransactionDetail, fetchTransactions } from "@/api/transactions";
import { apiClient } from "@/lib/api-client";

function toToolResult(details: unknown): { content: Array<{ type: "text"; text: string }>; details: unknown } {
  return {
    content: [{ type: "text", text: JSON.stringify(details, null, 2) }],
    details
  };
}

const AnySchema = z.unknown();

const RenderUiParams = Type.Object({
  spec: Type.Object({}, {
    additionalProperties: true,
    description:
      "Structured UI spec object. Required shape: {\"version\":\"v1\",\"layout\":\"stack|grid\",\"elements\":[...]}."
  })
});

const renderUiTool: AgentTool<any> = {
  name: "render_ui",
  label: "Render UI",
  description: `Render structured UI components in chat. Allowed components: ${CHAT_UI_COMPONENT_NAMES.join(
    ", "
  )}. Use this to present charts/graphs/tables/cards instead of long text dumps.`,
  parameters: RenderUiParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { spec?: unknown };
    if (!parsed.spec || typeof parsed.spec !== "object" || Array.isArray(parsed.spec)) {
      throw new Error("spec must be a JSON object");
    }
    const spec = parseChatUiSpec(parsed.spec);
    return {
      content: [{ type: "text", text: `Rendered ${spec.elements.length} UI element(s).` }],
      details: { ui_spec: spec }
    };
  }
};

const SearchTransactionsParams = Type.Object({
  query: Type.Optional(Type.String()),
  from_date: Type.Optional(Type.String({ description: "ISO date lower bound, e.g. 2025-01-01" })),
  to_date: Type.Optional(Type.String({ description: "ISO date upper bound, e.g. 2025-12-31" })),
  source_id: Type.Optional(Type.String({ description: "Filter by source/retailer id, e.g. lidl_plus_de" })),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 200 })),
  offset: Type.Optional(Type.Number({ minimum: 0 }))
});

const searchTransactionsTool: AgentTool<any> = {
  name: "search_transactions",
  label: "Search Receipts",
  description: "Search transactions by query text, date range, retailer source id, and pagination options.",
  parameters: SearchTransactionsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { query?: string; from_date?: string; to_date?: string; source_id?: string; limit?: number; offset?: number };
    const result = await fetchTransactions({
      query: parsed.query,
      purchasedFrom: parsed.from_date,
      purchasedTo: parsed.to_date,
      sourceId: parsed.source_id,
      limit: parsed.limit,
      offset: parsed.offset
    });
    return toToolResult(result);
  }
};

const GetTransactionDetailParams = Type.Object({
  id: Type.String()
});

const getTransactionDetailTool: AgentTool<any> = {
  name: "get_transaction_detail",
  label: "Transaction Detail",
  description: "Get full detail for one transaction by id.",
  parameters: GetTransactionDetailParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { id: string };
    const result = await fetchTransactionDetail(parsed.id);
    return toToolResult(result);
  }
};

const DashboardSummaryParams = Type.Object({
  year: Type.Optional(Type.Number()),
  month: Type.Optional(Type.Number({ minimum: 1, maximum: 12 }))
});

const dashboardSummaryTool: AgentTool<any> = {
  name: "dashboard_summary",
  label: "Dashboard Summary",
  description: "Get spending totals for a year and optional month.",
  parameters: DashboardSummaryParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { year?: number; month?: number };
    const now = new Date();
    const year = parsed.year ?? now.getFullYear();
    const result = await fetchDashboardCards(year, parsed.month);
    return toToolResult(result);
  }
};

const SpendingTrendsParams = Type.Object({
  year: Type.Optional(Type.Number()),
  months_back: Type.Optional(Type.Number({ minimum: 1, maximum: 24 })),
  end_month: Type.Optional(Type.Number({ minimum: 1, maximum: 12 }))
});

const spendingTrendsTool: AgentTool<any> = {
  name: "spending_trends",
  label: "Spending Trends",
  description: "Get dashboard trends for recent months.",
  parameters: SpendingTrendsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { year?: number; months_back?: number; end_month?: number };
    const now = new Date();
    const year = parsed.year ?? now.getFullYear();
    const result = await fetchDashboardTrends(
      year,
      parsed.months_back ?? 6,
      parsed.end_month ?? now.getMonth() + 1
    );
    return toToolResult(result);
  }
};

const CategoryBreakdownParams = Type.Object({
  year: Type.Optional(Type.Number()),
  month: Type.Optional(Type.Number({ minimum: 1, maximum: 12 })),
  view: Type.Optional(Type.Union([Type.Literal("native"), Type.Literal("normalized")]))
});

const categoryBreakdownTool: AgentTool<any> = {
  name: "category_breakdown",
  label: "Category Breakdown",
  description: "Get savings breakdown by category/type for a period.",
  parameters: CategoryBreakdownParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { year?: number; month?: number; view?: "native" | "normalized" };
    const now = new Date();
    const year = parsed.year ?? now.getFullYear();
    const result = await fetchSavingsBreakdown(year, parsed.month, parsed.view ?? "normalized");
    return toToolResult(result);
  }
};

const SearchProductsParams = Type.Object({
  search: Type.Optional(Type.String()),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 200 }))
});

const searchProductsTool: AgentTool<any> = {
  name: "search_products",
  label: "Search Products",
  description: "Search products by name or alias.",
  parameters: SearchProductsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { search?: string; limit?: number };
    const result = await fetchProducts({ search: parsed.search, limit: parsed.limit });
    return toToolResult(result);
  }
};

const ProductHistoryParams = Type.Object({
  id: Type.String(),
  grain: Type.Optional(Type.Union([Type.Literal("day"), Type.Literal("month"), Type.Literal("year")]))
});

const getProductHistoryTool: AgentTool<any> = {
  name: "get_product_history",
  label: "Product Price History",
  description: "Get price-series history for one product.",
  parameters: ProductHistoryParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { id: string; grain?: "day" | "month" | "year" };
    const result = await fetchProductPriceSeries({
      productId: parsed.id,
      grain: parsed.grain
    });
    return toToolResult(result);
  }
};

const TriggerSyncParams = Type.Object({
  source_id: Type.Optional(Type.String())
});

const triggerSyncTool: AgentTool<any> = {
  name: "trigger_sync",
  label: "Trigger Sync",
  description: "Start connector sync for a source id.",
  parameters: TriggerSyncParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { source_id?: string };
    const sourceId = parsed.source_id || "lidl_plus_de";
    const result = await apiClient.post(`/api/v1/sources/${sourceId}/sync`, AnySchema);
    return toToolResult(result);
  }
};

const ClusterProductsParams = Type.Object({
  force: Type.Optional(Type.Boolean())
});

const clusterProductsTool: AgentTool<any> = {
  name: "cluster_products",
  label: "Cluster Products",
  description: "Start AI clustering for unmatched receipt item names.",
  parameters: ClusterProductsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { force?: boolean };
    const result = await postClusterProducts({ force: parsed.force });
    return toToolResult(result);
  }
};

const AggregateItemsParams = Type.Object({
  query: Type.Optional(Type.String({ description: "Product name to match, e.g. 'gouda', 'milk', 'butter'" })),
  from_date: Type.Optional(Type.String({ description: "ISO date lower bound e.g. 2025-01-01" })),
  to_date: Type.Optional(Type.String({ description: "ISO date upper bound e.g. 2025-12-31" })),
  source_id: Type.Optional(Type.String({ description: "Filter by retailer, e.g. lidl_plus_de" })),
  group_by: Type.Optional(
    Type.Union([
      Type.Literal("source_id"),
      Type.Literal("month"),
      Type.Literal("year"),
      Type.Literal("name")
    ], { description: "Optional breakdown: source_id, month, year, or name" })
  )
});

const aggregateItemsTool: AgentTool<any> = {
  name: "aggregate_items",
  label: "Aggregate Spending",
  description:
    "Compute total spending and quantity for a product name across receipts. Returns grand_total_cents, item_count (number of receipt line items / shopping trips), and total_qty (actual number of units purchased). Use total_qty to answer 'how many X did I buy' and grand_total_cents for spend. Optionally group by source_id, month, year, or name for breakdowns.",
  parameters: AggregateItemsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as {
      query?: string;
      from_date?: string;
      to_date?: string;
      source_id?: string;
      group_by?: string;
    };
    const result = await apiClient.get("/api/v1/items/aggregate", AnySchema, {
      query: parsed.query,
      from_date: parsed.from_date,
      to_date: parsed.to_date,
      source_id: parsed.source_id,
      group_by: parsed.group_by
    });
    return toToolResult(result);
  }
};

const SearchItemsParams = Type.Object({
  query: Type.Optional(Type.String({ description: "Search term matched against item name, e.g. 'gouda', 'milk'" })),
  from_date: Type.Optional(Type.String({ description: "ISO date lower bound, e.g. 2025-01-01" })),
  to_date: Type.Optional(Type.String({ description: "ISO date upper bound, e.g. 2025-12-31" })),
  source_id: Type.Optional(Type.String({ description: "Filter by retailer source id, e.g. lidl_plus_de" })),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 500 })),
  offset: Type.Optional(Type.Number({ minimum: 0 }))
});

const searchItemsTool: AgentTool<any> = {
  name: "search_items",
  label: "Search Line Items",
  description:
    "Search individual receipt line items by product name across all transactions. Use this to find all purchases of a specific product (e.g. 'gouda', 'milk') and sum spending. Supports date range and retailer filters.",
  parameters: SearchItemsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as {
      query?: string;
      from_date?: string;
      to_date?: string;
      source_id?: string;
      limit?: number;
      offset?: number;
    };
    const result = await apiClient.get("/api/v1/items/search", AnySchema, {
      query: parsed.query,
      from_date: parsed.from_date,
      to_date: parsed.to_date,
      source_id: parsed.source_id,
      limit: parsed.limit !== undefined ? String(parsed.limit) : undefined,
      offset: parsed.offset !== undefined ? String(parsed.offset) : undefined
    });
    return toToolResult(result);
  }
};

const BudgetStatusParams = Type.Object({
  year: Type.Optional(Type.Number()),
  month: Type.Optional(Type.Number({ minimum: 1, maximum: 12 }))
});

const getBudgetStatusTool: AgentTool<any> = {
  name: "get_budget_status",
  label: "Budget Status",
  description:
    "Check budget rules and current spending vs budget limits. Use this to answer 'am I on budget?', 'how much budget do I have left?', or 'am I overspending?'.",
  parameters: BudgetStatusParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { year?: number; month?: number };
    const now = new Date();
    const result = await apiClient.get("/api/v1/analytics/budget", AnySchema, {
      year: parsed.year ?? now.getFullYear(),
      month: parsed.month ?? now.getMonth() + 1
    });
    return toToolResult(result);
  }
};

const ListRecurringBillsParams = Type.Object({
  include_inactive: Type.Optional(Type.Boolean())
});

const listRecurringBillsTool: AgentTool<any> = {
  name: "list_recurring_bills",
  label: "List Recurring Bills",
  description: "List configured recurring bills, including amount, cadence, and active status.",
  parameters: ListRecurringBillsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { include_inactive?: boolean };
    const result = await fetchRecurringBills({
      includeInactive: parsed.include_inactive
    });
    return toToolResult(result);
  }
};

const EmptyParams = Type.Object({});

const getRecurringOverviewTool: AgentTool<any> = {
  name: "get_recurring_overview",
  label: "Recurring Overview",
  description: "Get recurring-bill summary: monthly committed total, due this week, and overdue counts.",
  parameters: EmptyParams,
  execute: async () => {
    const result = await fetchRecurringOverview();
    return toToolResult(result);
  }
};

const getUpcomingBillsTool: AgentTool<any> = {
  name: "get_upcoming_bills",
  label: "Recurring Gaps",
  description:
    "Get overdue or unmatched recurring bill occurrences that need attention.",
  parameters: EmptyParams,
  execute: async () => {
    const result = await fetchRecurringGaps();
    return toToolResult(result);
  }
};

const RecurringForecastParams = Type.Object({
  months: Type.Optional(Type.Number({ minimum: 1, maximum: 24 }))
});

const getRecurringForecastTool: AgentTool<any> = {
  name: "get_recurring_forecast",
  label: "Recurring Forecast",
  description:
    "Get projected recurring spend for the next N months.",
  parameters: RecurringForecastParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { months?: number };
    const result = await fetchRecurringForecast({ months: parsed.months });
    return toToolResult(result);
  }
};

const RetailerCompositionParams = Type.Object({
  year: Type.Optional(Type.Number()),
  month: Type.Optional(Type.Number({ minimum: 1, maximum: 12 }))
});

const getRetailerCompositionTool: AgentTool<any> = {
  name: "get_retailer_composition",
  label: "Retailer Composition",
  description:
    "Show how spending is split across retailers/stores (Lidl, Rewe, Kaufland, dm, etc.) for a period. Use this for 'where do I spend the most?', 'which store do I use most?', or 'what share of my spending is at Lidl?'.",
  parameters: RetailerCompositionParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { year?: number; month?: number };
    const now = new Date();
    const result = await apiClient.get("/api/v1/dashboard/retailer-composition", AnySchema, {
      year: parsed.year ?? now.getFullYear(),
      month: parsed.month
    });
    return toToolResult(result);
  }
};

const ShoppingHeatmapView = Type.Union([
  Type.Literal("weekday"),
  Type.Literal("hour"),
  Type.Literal("matrix")
]);

const ShoppingHeatmapValue = Type.Union([
  Type.Literal("net"),
  Type.Literal("gross"),
  Type.Literal("count")
]);

const ShoppingHeatmapParams = Type.Object({
  view: Type.Optional(ShoppingHeatmapView),
  value: Type.Optional(ShoppingHeatmapValue),
  from_date: Type.Optional(Type.String({ description: "ISO date lower bound, e.g. 2025-01-01" })),
  to_date: Type.Optional(Type.String({ description: "ISO date upper bound, e.g. 2025-12-31" })),
  source_kind: Type.Optional(Type.String({ description: "Filter by source kind, e.g. lidl_plus_de" })),
  tz_offset_minutes: Type.Optional(Type.Number({ minimum: -840, maximum: 840 })),
  // Backward-compatible fallbacks. If from/to are omitted, these are expanded into a date window.
  year: Type.Optional(Type.Number()),
  month: Type.Optional(Type.Number({ minimum: 1, maximum: 12 }))
});

function formatIsoDate(year: number, month: number, day: number): string {
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function resolveLegacyDateWindow(
  year: number,
  month?: number
): { fromDate: string; toDate: string } {
  if (month === undefined) {
    return {
      fromDate: formatIsoDate(year, 1, 1),
      toDate: formatIsoDate(year, 12, 31)
    };
  }
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return {
    fromDate: formatIsoDate(year, month, 1),
    toDate: formatIsoDate(year, month, lastDay)
  };
}

const SHOPPING_HEATMAP_ENDPOINTS: Record<"weekday" | "hour" | "matrix", string> = {
  weekday: "/api/v1/analytics/heatmap/weekday",
  hour: "/api/v1/analytics/heatmap/hour",
  matrix: "/api/v1/analytics/heatmap/matrix"
};

const getShoppingHeatmapTool: AgentTool<any> = {
  name: "get_shopping_heatmap",
  label: "Shopping Heatmap",
  description:
    "Show shopping timing patterns by weekday, hour of day, or weekday x hour matrix. Use this for 'which day do I shop most?', 'what time do I usually shop?', 'do I spend more on weekends?', or 'when is my busiest shopping window?'.",
  parameters: ShoppingHeatmapParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as {
      view?: "weekday" | "hour" | "matrix";
      value?: "net" | "gross" | "count";
      from_date?: string;
      to_date?: string;
      source_kind?: string;
      tz_offset_minutes?: number;
      year?: number;
      month?: number;
    };
    const view = parsed.view ?? "weekday";
    const now = new Date();
    const endpoint = SHOPPING_HEATMAP_ENDPOINTS[view];

    let fromDate = parsed.from_date;
    let toDate = parsed.to_date;
    if (!fromDate && !toDate && (parsed.year !== undefined || parsed.month !== undefined)) {
      const legacyWindow = resolveLegacyDateWindow(parsed.year ?? now.getFullYear(), parsed.month);
      fromDate = legacyWindow.fromDate;
      toDate = legacyWindow.toDate;
    }

    const query: Record<string, string | number> = {};
    if (fromDate) {
      query.from_date = fromDate;
    }
    if (toDate) {
      query.to_date = toDate;
    }
    if (parsed.value) {
      query.value = parsed.value;
    }
    if (parsed.source_kind) {
      query.source_kind = parsed.source_kind;
    }
    if (parsed.tz_offset_minutes !== undefined) {
      query.tz_offset_minutes = parsed.tz_offset_minutes;
    }

    const result = await apiClient.get(endpoint, AnySchema, query);
    return toToolResult(result);
  }
};

const PriceIndexParams = Type.Object({
  months_back: Type.Optional(Type.Number({ minimum: 1, maximum: 36 }))
});

const getPriceIndexTool: AgentTool<any> = {
  name: "get_price_index",
  label: "Price Index",
  description:
    "Get a price inflation index per retailer over recent months, showing how prices have changed over time. Use this for 'is Lidl getting more expensive?', 'which store has the best price trend?', or 'how much has inflation affected my shopping?'.",
  parameters: PriceIndexParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { months_back?: number };
    const result = await apiClient.get("/api/v1/analytics/price-index", AnySchema, {
      months_back: parsed.months_back
    });
    return toToolResult(result);
  }
};

const GetProductPurchasesParams = Type.Object({
  id: Type.String({ description: "Product ID from search_products" }),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 }))
});

const getProductPurchasesTool: AgentTool<any> = {
  name: "get_product_purchases",
  label: "Product Purchase History",
  description:
    "Get all individual purchases of a specific product by product ID. Use this to answer 'when did I last buy X?' or 'how often do I buy X?'. First use search_products to find the product ID, then call this tool.",
  parameters: GetProductPurchasesParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { id: string; limit?: number };
    const result = await apiClient.get(`/api/v1/products/${parsed.id}/purchases`, AnySchema, {
      limit: parsed.limit
    });
    return toToolResult(result);
  }
};

const ExecutePythonParams = Type.Object({
  code: Type.String({
    description:
      "Python code to execute. Variables available: DB_PATH (str), conn (sqlite3.Connection, read-only). Use print() for output. Key schema notes: transaction_items.line_total_cents is the final amount the customer paid — discounts are already baked in, do NOT subtract raw_payload discounts again. raw_payload is a JSON string with fields: qty, unit_price_cents, line_total_cents, vat_rate (e.g. '0.07'), discounts (list, already reflected in line_total_cents), is_deposit (int). Example: print(conn.execute('SELECT COUNT(*) FROM transactions').fetchone()[0])"
  }),
  timeout: Type.Optional(Type.Number({ minimum: 5, maximum: 120, description: "Max seconds to run, default 30" }))
});

const executePythonTool: AgentTool<any> = {
  name: "execute_python",
  label: "Run Python",
  description:
    "Execute Python code directly against the database for complex queries that can't be expressed with other tools — e.g. VAT breakdowns, multi-step aggregations, custom analytics. Variables DB_PATH and conn (read-only sqlite3 connection) are pre-available. Use print() to output results. Prefer this over chaining many tool calls when the logic is computational.",
  parameters: ExecutePythonParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { code: string; timeout?: number };
    const result = await apiClient.post("/api/v1/tools/exec", AnySchema, {
      code: parsed.code,
      timeout: parsed.timeout
    });
    return toToolResult(result);
  }
};

export const ALL_TOOLS: AgentTool<any>[] = [
  renderUiTool,
  executePythonTool,
  aggregateItemsTool,
  searchItemsTool,
  searchTransactionsTool,
  getTransactionDetailTool,
  dashboardSummaryTool,
  spendingTrendsTool,
  categoryBreakdownTool,
  getBudgetStatusTool,
  listRecurringBillsTool,
  getRecurringOverviewTool,
  getUpcomingBillsTool,
  getRecurringForecastTool,
  getRetailerCompositionTool,
  getShoppingHeatmapTool,
  getPriceIndexTool,
  searchProductsTool,
  getProductHistoryTool,
  getProductPurchasesTool,
  triggerSyncTool,
  clusterProductsTool
];
