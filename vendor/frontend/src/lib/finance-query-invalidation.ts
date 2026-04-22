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
  ["goals-page"]
] as const;

export async function invalidateFinanceWorkspaceQueries(queryClient: QueryClient): Promise<void> {
  await Promise.all(
    FINANCE_QUERY_PREFIXES.map((queryKey) =>
      queryClient.invalidateQueries({ queryKey: [...queryKey] })
    )
  );
}
