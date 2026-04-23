import type { QueryClient } from "@tanstack/react-query";

const FINANCE_QUERY_PREFIXES = [
  ["dashboard-overview"],
  ["groceries-page"],
  ["merchants-page"],
  ["cash-flow-page"],
  ["budget-summary"],
  ["cashflow-entries"],
  ["transactions"],
  ["transaction-detail"],
  ["goals-page"],
  ["sources"],
  ["review-queue"],
  ["recurring-bills"],
  ["recurring-overview"],
  ["recurring-calendar"],
  ["recurring-occurrences"],
  ["notifications"]
] as const;

export async function invalidateFinanceWorkspaceQueries(queryClient: QueryClient): Promise<void> {
  await Promise.all(
    FINANCE_QUERY_PREFIXES.map((queryKey) =>
      queryClient.invalidateQueries({ queryKey: [...queryKey] })
    )
  );
}
