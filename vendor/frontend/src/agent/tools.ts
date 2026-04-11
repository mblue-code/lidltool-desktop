import { AgentTool } from "@mariozechner/pi-agent-core";
import { Type } from "@sinclair/typebox";
import { z } from "zod";

import { fetchDashboardCards, fetchDashboardTrends, fetchSavingsBreakdown } from "@/api/dashboard";
import {
  createAutomationRule,
  fetchAutomationRules,
  updateAutomationRule
} from "@/api/automations";
import {
  createOfferSource,
  deleteOfferSource,
  fetchOfferMerchantItems,
  createOfferWatchlist,
  deleteOfferWatchlist,
  fetchOfferMatches,
  fetchOfferRefreshRuns,
  fetchOfferSources,
  fetchOfferWatchlists,
  postOfferRefresh,
  updateOfferSource,
  updateOfferWatchlist
} from "@/api/offers";
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

const ListOfferSourcesParams = Type.Object({});

const listOfferSourcesTool: AgentTool<any> = {
  name: "list_offer_sources",
  label: "Offer Sources",
  description:
    "List user-managed offer sources. These are merchant offer URLs created in the app and scanned by the AI assistant.",
  parameters: ListOfferSourcesParams,
  execute: async () => {
    const result = await fetchOfferSources();
    return toToolResult(result);
  }
};

const CreateOfferSourceParams = Type.Object({
  merchant_name: Type.String(),
  merchant_url: Type.String(),
  display_name: Type.Optional(Type.String()),
  country_code: Type.Optional(Type.String({ minLength: 2, maxLength: 2 })),
  notes: Type.Optional(Type.String())
});

const createOfferSourceTool: AgentTool<any> = {
  name: "create_offer_source",
  label: "Create Offer Source",
  description:
    "Create a new AI-scanned offer source from a merchant offer page URL. Use this when the user gives you a specific offers page link.",
  parameters: CreateOfferSourceParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as {
      merchant_name: string;
      merchant_url: string;
      display_name?: string;
      country_code?: string;
      notes?: string;
    };
    const result = await createOfferSource(parsed);
    return toToolResult(result);
  }
};

const UpdateOfferSourceParams = Type.Object({
  source_id: Type.String(),
  merchant_name: Type.Optional(Type.String()),
  merchant_url: Type.Optional(Type.String()),
  display_name: Type.Optional(Type.String()),
  country_code: Type.Optional(Type.String({ minLength: 2, maxLength: 2 })),
  notes: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  active: Type.Optional(Type.Boolean())
});

const updateOfferSourceTool: AgentTool<any> = {
  name: "update_offer_source",
  label: "Update Offer Source",
  description: "Update an existing user-managed offer source by source_id.",
  parameters: UpdateOfferSourceParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as {
      source_id: string;
      merchant_name?: string;
      merchant_url?: string;
      display_name?: string;
      country_code?: string;
      notes?: string | null;
      active?: boolean;
    };
    const result = await updateOfferSource(parsed.source_id, {
      merchant_name: parsed.merchant_name,
      merchant_url: parsed.merchant_url,
      display_name: parsed.display_name,
      country_code: parsed.country_code,
      notes: parsed.notes,
      active: parsed.active
    });
    return toToolResult(result);
  }
};

const DeleteOfferSourceParams = Type.Object({
  source_id: Type.String()
});

const deleteOfferSourceTool: AgentTool<any> = {
  name: "delete_offer_source",
  label: "Delete Offer Source",
  description: "Delete an existing user-managed offer source by source_id.",
  parameters: DeleteOfferSourceParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { source_id: string };
    const result = await deleteOfferSource(parsed.source_id);
    return toToolResult(result);
  }
};

const ListOfferMerchantItemsParams = Type.Object({
  merchant_name: Type.String(),
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 200 }))
});

const listOfferMerchantItemsTool: AgentTool<any> = {
  name: "list_offer_merchant_items",
  label: "Merchant Purchase Items",
  description:
    "List items the user has already bought from a merchant. Use this when creating a watchlist for a merchant with existing receipt history.",
  parameters: ListOfferMerchantItemsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { merchant_name: string; limit?: number };
    const result = await fetchOfferMerchantItems({
      merchantName: parsed.merchant_name,
      limit: parsed.limit
    });
    return toToolResult(result);
  }
};

const ListOfferWatchlistsParams = Type.Object({
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 200 }))
});

const listOfferWatchlistsTool: AgentTool<any> = {
  name: "list_offer_watchlists",
  label: "Offer Watchlists",
  description: "List the user's current offer watchlists.",
  parameters: ListOfferWatchlistsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { limit?: number };
    const result = await fetchOfferWatchlists();
    const items = typeof parsed.limit === "number" ? result.items.slice(0, parsed.limit) : result.items;
    return toToolResult({
      ...result,
      count: items.length,
      items
    });
  }
};

const CreateOfferWatchlistParams = Type.Object({
  product_id: Type.Optional(Type.String()),
  query_text: Type.Optional(Type.String()),
  source_id: Type.Optional(Type.String()),
  min_discount_percent: Type.Optional(Type.Number({ minimum: 0, maximum: 100 })),
  max_price_cents: Type.Optional(Type.Number({ minimum: 0 })),
  notes: Type.Optional(Type.String())
});

const createOfferWatchlistTool: AgentTool<any> = {
  name: "create_offer_watchlist",
  label: "Create Offer Watchlist",
  description:
    "Create a watchlist entry for offer tracking. Provide either product_id or query_text. Optional source_id should match one of the user-managed offer sources.",
  parameters: CreateOfferWatchlistParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as {
      product_id?: string;
      query_text?: string;
      source_id?: string;
      min_discount_percent?: number;
      max_price_cents?: number;
      notes?: string;
    };
    const result = await createOfferWatchlist({
      product_id: parsed.product_id,
      query_text: parsed.query_text,
      source_id: parsed.source_id,
      min_discount_percent: parsed.min_discount_percent,
      max_price_cents: parsed.max_price_cents,
      notes: parsed.notes
    });
    return toToolResult(result);
  }
};

const UpdateOfferWatchlistParams = Type.Object({
  id: Type.String(),
  product_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  query_text: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  source_id: Type.Optional(Type.Union([Type.String(), Type.Null()])),
  min_discount_percent: Type.Optional(Type.Union([Type.Number({ minimum: 0, maximum: 100 }), Type.Null()])),
  max_price_cents: Type.Optional(Type.Union([Type.Number({ minimum: 0 }), Type.Null()])),
  active: Type.Optional(Type.Boolean()),
  notes: Type.Optional(Type.Union([Type.String(), Type.Null()]))
});

const updateOfferWatchlistTool: AgentTool<any> = {
  name: "update_offer_watchlist",
  label: "Update Offer Watchlist",
  description: "Update an existing offer watchlist entry by id.",
  parameters: UpdateOfferWatchlistParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as {
      id: string;
      product_id?: string | null;
      query_text?: string | null;
      source_id?: string | null;
      min_discount_percent?: number | null;
      max_price_cents?: number | null;
      active?: boolean;
      notes?: string | null;
    };
    const result = await updateOfferWatchlist(parsed.id, {
      product_id: parsed.product_id,
      query_text: parsed.query_text,
      source_id: parsed.source_id,
      min_discount_percent: parsed.min_discount_percent,
      max_price_cents: parsed.max_price_cents,
      active: parsed.active,
      notes: parsed.notes
    });
    return toToolResult(result);
  }
};

const DeleteOfferWatchlistParams = Type.Object({
  id: Type.String()
});

const deleteOfferWatchlistTool: AgentTool<any> = {
  name: "delete_offer_watchlist",
  label: "Delete Offer Watchlist",
  description: "Delete an offer watchlist entry by id.",
  parameters: DeleteOfferWatchlistParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { id: string };
    const result = await deleteOfferWatchlist(parsed.id);
    return toToolResult(result);
  }
};

const RefreshOffersParams = Type.Object({
  source_ids: Type.Optional(Type.Array(Type.String())),
  discovery_limit: Type.Optional(Type.Number({ minimum: 1, maximum: 500 }))
});

const refreshOffersTool: AgentTool<any> = {
  name: "refresh_offers",
  label: "Refresh Offers",
  description:
    "Trigger offer discovery for user-managed merchant URLs. The AI assistant fetches those configured pages and extracts current offers.",
  parameters: RefreshOffersParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { source_ids?: string[]; discovery_limit?: number };
    const result = await postOfferRefresh({
      source_ids: parsed.source_ids,
      discovery_limit: parsed.discovery_limit
    });
    return toToolResult(result);
  }
};

const ListOfferMatchesParams = Type.Object({
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 200 }))
});

const listOfferMatchesTool: AgentTool<any> = {
  name: "list_offer_matches",
  label: "Offer Matches",
  description: "List active offer matches for the user's watchlists.",
  parameters: ListOfferMatchesParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { limit?: number };
    const result = await fetchOfferMatches(parsed.limit);
    return toToolResult(result);
  }
};

const ListOfferRefreshRunsParams = Type.Object({
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 100 }))
});

const listOfferRefreshRunsTool: AgentTool<any> = {
  name: "list_offer_refresh_runs",
  label: "Offer Refresh Runs",
  description: "List recent offer refresh runs, including status and per-source results.",
  parameters: ListOfferRefreshRunsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { limit?: number };
    const result = await fetchOfferRefreshRuns(parsed.limit);
    return toToolResult(result);
  }
};

const ListOfferRefreshAutomationsParams = Type.Object({
  limit: Type.Optional(Type.Number({ minimum: 1, maximum: 200 }))
});

const listOfferRefreshAutomationsTool: AgentTool<any> = {
  name: "list_offer_refresh_automations",
  label: "Offer Refresh Automations",
  description: "List automation rules that schedule offer refreshes.",
  parameters: ListOfferRefreshAutomationsParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as { limit?: number };
    const result = await fetchAutomationRules(parsed.limit ?? 100, 0);
    const items = result.items.filter((rule) => rule.rule_type === "offer_refresh");
    return toToolResult({
      ...result,
      count: items.length,
      total: items.length,
      items
    });
  }
};

const OfferAutomationScheduleMode = Type.Union([Type.Literal("interval"), Type.Literal("weekly")]);

function resolveBrowserTimeZone(): string | undefined {
  try {
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return typeof timeZone === "string" && timeZone.trim().length > 0 ? timeZone : undefined;
  } catch {
    return undefined;
  }
}

const CreateOfferRefreshAutomationParams = Type.Object({
  name: Type.String(),
  enabled: Type.Optional(Type.Boolean()),
  source_ids: Type.Optional(Type.Array(Type.String())),
  discovery_limit: Type.Optional(Type.Number({ minimum: 1, maximum: 500 })),
  schedule_mode: Type.Optional(OfferAutomationScheduleMode),
  interval_seconds: Type.Optional(Type.Number({ minimum: 60 })),
  weekday: Type.Optional(Type.Number({ minimum: 0, maximum: 6 })),
  hour: Type.Optional(Type.Number({ minimum: 0, maximum: 23 })),
  minute: Type.Optional(Type.Number({ minimum: 0, maximum: 59 }))
});

function buildOfferRefreshTriggerConfig(params: {
  schedule_mode?: "interval" | "weekly";
  interval_seconds?: number;
  weekday?: number;
  hour?: number;
  minute?: number;
}): Record<string, unknown> {
  if (params.schedule_mode === "weekly") {
    const timeZone = resolveBrowserTimeZone();
    return {
      schedule: {
        mode: "weekly",
        weekday: params.weekday ?? 0,
        hour: params.hour ?? 8,
        minute: params.minute ?? 0,
        timezone: timeZone
      }
    };
  }
  return {
    schedule: {
      mode: "interval",
      interval_seconds: params.interval_seconds ?? 3600
    }
  };
}

const createOfferRefreshAutomationTool: AgentTool<any> = {
  name: "create_offer_refresh_automation",
  label: "Create Offer Refresh Automation",
  description:
    "Create a scheduled automation rule for offer_refresh. Use weekly scheduling for requests like 'every Monday morning'. weekday uses Monday=0 through Sunday=6.",
  parameters: CreateOfferRefreshAutomationParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as {
      name: string;
      enabled?: boolean;
      source_ids?: string[];
      discovery_limit?: number;
      schedule_mode?: "interval" | "weekly";
      interval_seconds?: number;
      weekday?: number;
      hour?: number;
      minute?: number;
    };
    const result = await createAutomationRule({
      name: parsed.name,
      rule_type: "offer_refresh",
      enabled: parsed.enabled ?? true,
      trigger_config: buildOfferRefreshTriggerConfig(parsed),
      action_config: {
        source_ids: parsed.source_ids ?? [],
        discovery_limit: parsed.discovery_limit
      }
    });
    return toToolResult(result);
  }
};

const UpdateOfferRefreshAutomationParams = Type.Object({
  id: Type.String(),
  name: Type.Optional(Type.String()),
  enabled: Type.Optional(Type.Boolean()),
  source_ids: Type.Optional(Type.Array(Type.String())),
  discovery_limit: Type.Optional(Type.Union([Type.Number({ minimum: 1, maximum: 500 }), Type.Null()])),
  schedule_mode: Type.Optional(OfferAutomationScheduleMode),
  interval_seconds: Type.Optional(Type.Number({ minimum: 60 })),
  weekday: Type.Optional(Type.Number({ minimum: 0, maximum: 6 })),
  hour: Type.Optional(Type.Number({ minimum: 0, maximum: 23 })),
  minute: Type.Optional(Type.Number({ minimum: 0, maximum: 59 }))
});

const updateOfferRefreshAutomationTool: AgentTool<any> = {
  name: "update_offer_refresh_automation",
  label: "Update Offer Refresh Automation",
  description:
    "Update a scheduled offer_refresh automation rule by id. weekday uses Monday=0 through Sunday=6.",
  parameters: UpdateOfferRefreshAutomationParams,
  execute: async (_toolCallId, params) => {
    const parsed = params as {
      id: string;
      name?: string;
      enabled?: boolean;
      source_ids?: string[];
      discovery_limit?: number | null;
      schedule_mode?: "interval" | "weekly";
      interval_seconds?: number;
      weekday?: number;
      hour?: number;
      minute?: number;
    };
    const payload: Record<string, unknown> = {};
    if (parsed.name !== undefined) {
      payload.name = parsed.name;
    }
    if (parsed.enabled !== undefined) {
      payload.enabled = parsed.enabled;
    }
    if (
      parsed.schedule_mode !== undefined ||
      parsed.interval_seconds !== undefined ||
      parsed.weekday !== undefined ||
      parsed.hour !== undefined ||
      parsed.minute !== undefined
    ) {
      payload.trigger_config = buildOfferRefreshTriggerConfig(parsed);
    }
    if (parsed.source_ids !== undefined || parsed.discovery_limit !== undefined) {
      payload.action_config = {
        source_ids: parsed.source_ids ?? [],
        discovery_limit: parsed.discovery_limit ?? undefined
      };
    }
    const result = await updateAutomationRule(parsed.id, payload);
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
  listOfferSourcesTool,
  createOfferSourceTool,
  updateOfferSourceTool,
  deleteOfferSourceTool,
  listOfferMerchantItemsTool,
  listOfferWatchlistsTool,
  createOfferWatchlistTool,
  updateOfferWatchlistTool,
  deleteOfferWatchlistTool,
  refreshOffersTool,
  listOfferMatchesTool,
  listOfferRefreshRunsTool,
  listOfferRefreshAutomationsTool,
  createOfferRefreshAutomationTool,
  updateOfferRefreshAutomationTool,
  triggerSyncTool,
  clusterProductsTool
];
