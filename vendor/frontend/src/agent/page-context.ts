type RouteContextRule = {
  prefix: string;
  context: string;
};

const ROUTE_CONTEXT_RULES: RouteContextRule[] = [
  {
    prefix: "/transactions/",
    context:
      "Page context: Transaction Detail. The user is inspecting one receipt with line items, totals, discounts, and metadata. Available tools: get_transaction_detail (exact receipt facts), search_transactions (similar baskets/time windows), aggregate_items and get_product_purchases (item-level price/quantity context)."
  },
  {
    prefix: "/review-queue/",
    context:
      "Page context: Review Queue Detail. The user is validating one low-confidence extraction. Available tools: get_transaction_detail (ground truth check), search_items (line-level corroboration), search_transactions (pattern cross-check against similar receipts)."
  },
  {
    prefix: "/review-queue",
    context:
      "Page context: Review Queue. The user is triaging low-confidence records. Prioritize fast validation steps and call out uncertainty clearly."
  },
  {
    prefix: "/quality",
    context:
      "Page context: Data Quality. The user is reviewing OCR/confidence issues and data hygiene. Useful tools here: search_items for raw line checks, aggregate_items for normalization impact, cluster_products for grouping diagnostics."
  },
  {
    prefix: "/imports/manual",
    context:
      "Page context: Manual Import. The user can create transactions manually. Provide field-level guidance, validation expectations, and safe import practices."
  },
  {
    prefix: "/imports/ocr",
    context:
      "Page context: OCR Import. The user uploads receipt files for extraction. Advise on image quality, extraction limits, and post-import verification steps."
  },
  {
    prefix: "/documents/upload",
    context:
      "Page context: OCR Import. The user uploads receipt files for extraction. Advise on image quality, extraction limits, and post-import verification steps."
  },
  {
    prefix: "/automation-inbox",
    context:
      "Page context: Automation Inbox. The user reviews automation runs and outputs. Help interpret results, failures, and next operational actions."
  },
  {
    prefix: "/automations",
    context:
      "Page context: Automations. The user configures recurring rules and workflows. Explain trigger logic, scope effects, and safe rollout/testing."
  },
  {
    prefix: "/connectors",
    context:
      "Page context: Connectors. The user manages source connections and sync health. Focus on connector status, sync troubleshooting, and expected downstream data effects."
  },
  {
    prefix: "/settings/ai",
    context:
      "Page context: AI Settings. The user configures AI provider/model access. Give safe configuration guidance and verification steps."
  },
  {
    prefix: "/settings/users",
    context:
      "Page context: User Settings. The user manages users and permissions. Focus on role effects, access boundaries, and security hygiene."
  },
  {
    prefix: "/reliability",
    context:
      "Page context: Reliability. The user monitors health and incidents. Prioritize probable causes, blast radius, and recovery checks."
  },
  {
    prefix: "/sources",
    context:
      "Page context: Sources. The user is reviewing source configuration and provenance. Clarify which data comes from each source and how source settings affect analytics."
  },
  {
    prefix: "/receipts",
    context:
      "Page context: Receipts. The user is in the transaction list and can drill into receipt rows. Help with filtering, anomaly spotting, and selecting next receipts to inspect."
  },
  {
    prefix: "/explore",
    context:
      "Page context: Explore. The user can filter and search transactions by date, merchant, category, and amount. Give step-by-step filter guidance using fields visible in this view."
  },
  {
    prefix: "/products",
    context:
      "Page context: Products. The user is browsing product-level history across retailers. Available tools: search_products (find candidates), get_product_history (price timeline), get_product_purchases (purchase cadence and quantity)."
  },
  {
    prefix: "/compare",
    context:
      "Page context: Comparisons. The user compares products or baskets side-by-side. Available tools: aggregate_items (normalized basket totals), get_price_index (price movement), get_product_history (direct timeline comparisons)."
  },
  {
    prefix: "/budget",
    context:
      "Page context: Budget. The user is tracking spend versus targets. Emphasize variance drivers, forecast risk, and concrete corrective actions."
  },
  {
    prefix: "/bills",
    context:
      "Page context: Bills. The user is managing recurring obligations (rent, subscriptions, utilities), due dates, and match status. Helpful tools: list_recurring_bills, get_recurring_overview, get_upcoming_bills, get_recurring_forecast."
  },
  {
    prefix: "/patterns",
    context:
      "Page context: Patterns. The user is analyzing recurring behavior and seasonality. Highlight repeated spend patterns and cost-reduction opportunities."
  },
  {
    prefix: "/",
    context:
      "Page context: Overview. The user is reviewing top-level spending KPIs, trends, and summaries. Explain headline movement and suggest which page to open next for deeper analysis."
  }
];

function matchesRoute(pathname: string, prefix: string): boolean {
  if (prefix === "/") {
    return pathname === "/";
  }
  if (prefix.endsWith("/")) {
    return pathname.startsWith(prefix);
  }
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

export function getSidePanelPageContext(pathname: string): string | null {
  if (!pathname) {
    return null;
  }
  if (matchesRoute(pathname, "/chat")) {
    return null;
  }
  if (pathname.startsWith("/transactions/")) {
    const transactionId = pathname.split("/")[2]?.trim();
    if (transactionId) {
      return [
        "Page context: Transaction Detail.",
        `Current transaction id: ${transactionId}.`,
        "The user is inspecting one receipt with line items, totals, discounts, and metadata.",
        "Before answering any factual question about this receipt, call get_transaction_detail with the current transaction id.",
        "If the user asks about similar baskets or time windows, use search_transactions in addition to the detail lookup.",
        "Never invent VAT, items, totals, discounts, or pfand. If a field is absent in tool output, say it is absent."
      ].join(" ");
    }
  }
  for (const rule of ROUTE_CONTEXT_RULES) {
    if (matchesRoute(pathname, rule.prefix)) {
      return rule.context;
    }
  }
  return null;
}
