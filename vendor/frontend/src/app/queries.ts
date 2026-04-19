import { queryOptions } from "@tanstack/react-query";

import { fetchDepositAnalytics } from "@/api/analytics";
import {
  fetchDashboardCardsWithWarnings,
  fetchDashboardTrendsWithWarnings,
  fetchRetailerCompositionWithWarnings,
  fetchSavingsBreakdownWithWarnings
} from "@/api/dashboard";
import { fetchReliabilitySlo } from "@/api/reliability";
import { fetchReviewQueue, fetchReviewQueueDetail } from "@/api/reviewQueue";
import { fetchAutomationExecutions, fetchAutomationRules } from "@/api/automations";
import { fetchTransactionDetail, fetchTransactionHistory, fetchTransactions } from "@/api/transactions";
import { warningCacheKey, type ApiWarning } from "@/lib/api-messages";

export type DashboardDiscountView = "native" | "normalized";
export type DashboardPeriodMode = "month" | "range" | "year";

export type TransactionsFilters = {
  query?: string;
  sourceId?: string;
  sourceKind?: string;
  weekday?: number;
  hour?: number;
  tzOffsetMinutes?: number;
  merchantName?: string;
  year?: number;
  month?: number;
  purchasedFrom?: string;
  purchasedTo?: string;
  sortBy?: "purchased_at" | "store_name" | "source_id" | "total_gross_cents" | "discount_total_cents";
  sortDir?: "asc" | "desc";
  minTotalCents?: number;
  maxTotalCents?: number;
  limit: number;
  offset: number;
};

export type AutomationExecutionsFilters = {
  status?: string;
  ruleType?: string;
  limit?: number;
  offset?: number;
};

export type ReviewQueueFilters = {
  status?: string;
  threshold?: number;
  limit?: number;
  offset?: number;
};

export type ReliabilitySloFilters = {
  windowHours?: number;
  syncP95TargetMs?: number;
  analyticsP95TargetMs?: number;
  minSuccessRate?: number;
};

export const queryKeys = {
  dashboardPanels: (
    year: number,
    periodMode: DashboardPeriodMode,
    month: number,
    startMonth: number,
    endMonth: number,
    view: DashboardDiscountView,
    sourceIds: string[]
  ) => ["dashboard", year, periodMode, month, startMonth, endMonth, view, sourceIds] as const,
  transactions: (filters: TransactionsFilters) => ["transactions", filters] as const,
  transactionDetail: (transactionId: string) => ["transaction-detail", transactionId] as const,
  reviewQueue: (filters: Required<ReviewQueueFilters>) =>
    ["review-queue", filters.status, filters.threshold, filters.limit, filters.offset] as const,
  reviewQueueDetail: (documentId: string) => ["review-queue-detail", documentId] as const,
  automationRules: (limit: number, offset: number) => ["automation-rules", limit, offset] as const,
  automationExecutions: (filters: Required<AutomationExecutionsFilters>) =>
    ["automation-executions", filters.status, filters.ruleType, filters.limit, filters.offset] as const,
  reliabilitySlo: (filters: Required<ReliabilitySloFilters>) =>
    [
      "reliability-slo",
      filters.windowHours,
      filters.syncP95TargetMs,
      filters.analyticsP95TargetMs,
      filters.minSuccessRate
    ] as const
};

export function dashboardPanelsQueryOptions(params: {
  year: number;
  periodMode: DashboardPeriodMode;
  month: number;
  startMonth: number;
  endMonth: number;
  view: DashboardDiscountView;
  sourceIds: string[];
}) {
  const { year, periodMode, month, startMonth, endMonth, view, sourceIds } = params;
  const normalizedSourceIds = Array.from(new Set(sourceIds.map((value) => value.trim()).filter(Boolean))).sort();

  function uniqueWarnings(values: Array<{ warnings: ApiWarning[] }>): ApiWarning[] {
    const deduped = new Map<string, ApiWarning>();
    for (const warning of values.flatMap((value) => value.warnings)) {
      deduped.set(warningCacheKey(warning), warning);
    }
    return Array.from(deduped.values());
  }

  function safeRatio(numerator: number, denominator: number): number {
    if (denominator <= 0) {
      return 0;
    }
    return Number((numerator / denominator).toFixed(6));
  }

  function centsToCurrency(cents: number): string {
    return (cents / 100).toFixed(2);
  }

  function monthBounds(targetYear: number, targetMonth: number): { fromDate: string; toDate: string } {
    const lastDay = new Date(Date.UTC(targetYear, targetMonth, 0)).getUTCDate();
    return {
      fromDate: `${targetYear}-${String(targetMonth).padStart(2, "0")}-01`,
      toDate: `${targetYear}-${String(targetMonth).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`
    };
  }

  function periodWindow(): { fromDate: string; toDate: string } {
    if (periodMode === "month") {
      return monthBounds(year, month);
    }
    if (periodMode === "range") {
      return {
        fromDate: monthBounds(year, startMonth).fromDate,
        toDate: monthBounds(year, endMonth).toDate
      };
    }
    return {
      fromDate: `${year}-01-01`,
      toDate: `${year}-12-31`
    };
  }

  return queryOptions({
    queryKey: queryKeys.dashboardPanels(
      year,
      periodMode,
      month,
      startMonth,
      endMonth,
      view,
      normalizedSourceIds
    ),
    queryFn: async () => {
      if (periodMode === "range") {
        const months = Array.from({ length: endMonth - startMonth + 1 }, (_, index) => startMonth + index);
        const cardsResponses = await Promise.all(
          months.map((monthValue) => fetchDashboardCardsWithWarnings(year, monthValue, normalizedSourceIds))
        );
        const breakdownResponses = await Promise.all(
          months.map((monthValue) =>
            fetchSavingsBreakdownWithWarnings(year, monthValue, view, normalizedSourceIds)
          )
        );
        const compositionResponses = await Promise.all(
          months.map((monthValue) =>
            fetchRetailerCompositionWithWarnings(year, monthValue, normalizedSourceIds)
          )
        );
        const trendsResponse = await fetchDashboardTrendsWithWarnings(
          year,
          months.length,
          endMonth,
          normalizedSourceIds
        );
        const deposit = await fetchDepositAnalytics({
          ...periodWindow(),
          sourceIds: normalizedSourceIds
        });

        const aggregatedReceiptCount = cardsResponses.reduce(
          (sum, response) => sum + response.result.totals.receipt_count,
          0
        );
        const aggregatedGrossCents = cardsResponses.reduce(
          (sum, response) => sum + response.result.totals.gross_cents,
          0
        );
        const aggregatedNetCents = cardsResponses.reduce(
          (sum, response) => sum + (response.result.totals.net_cents ?? response.result.totals.paid_cents),
          0
        );
        const aggregatedSavedCents = cardsResponses.reduce(
          (sum, response) =>
            sum +
            (response.result.totals.discount_total_cents ?? response.result.totals.saved_cents),
          0
        );
        const cards = {
          totals: {
            receipt_count: aggregatedReceiptCount,
            gross_cents: aggregatedGrossCents,
            gross_currency: centsToCurrency(aggregatedGrossCents),
            net_cents: aggregatedNetCents,
            net_currency: centsToCurrency(aggregatedNetCents),
            discount_total_cents: aggregatedSavedCents,
            discount_total_currency: centsToCurrency(aggregatedSavedCents),
            paid_cents: aggregatedNetCents,
            paid_currency: centsToCurrency(aggregatedNetCents),
            saved_cents: aggregatedSavedCents,
            saved_currency: centsToCurrency(aggregatedSavedCents),
            savings_rate: safeRatio(aggregatedSavedCents, aggregatedGrossCents)
          }
        };

        const breakdownByType = new Map<string, { discount_events: number; saved_cents: number }>();
        for (const response of breakdownResponses) {
          for (const row of response.result.by_type) {
            const existing = breakdownByType.get(row.type) ?? { discount_events: 0, saved_cents: 0 };
            existing.discount_events += row.discount_events;
            existing.saved_cents += row.saved_cents;
            breakdownByType.set(row.type, existing);
          }
        }
        const breakdown = {
          view,
          by_type: Array.from(breakdownByType.entries())
            .map(([type, values]) => ({
              type,
              discount_events: values.discount_events,
              saved_cents: values.saved_cents,
              saved_currency: centsToCurrency(values.saved_cents)
            }))
            .sort((left, right) => right.saved_cents - left.saved_cents)
        };

        const compositionByRetailer = new Map<
          string,
          {
            source_id: string;
            retailer: string;
            receipt_count: number;
            gross_cents: number;
            net_cents: number;
            discount_total_cents: number;
          }
        >();
        for (const response of compositionResponses) {
          for (const row of response.result.retailers) {
            const grossCents = row.gross_cents ?? row.paid_cents + row.saved_cents;
            const netCents = row.net_cents ?? row.paid_cents;
            const discountTotalCents = row.discount_total_cents ?? row.saved_cents;
            const existing = compositionByRetailer.get(row.source_id) ?? {
              source_id: row.source_id,
              retailer: row.retailer,
              receipt_count: 0,
              gross_cents: 0,
              net_cents: 0,
              discount_total_cents: 0
            };
            existing.receipt_count += row.receipt_count ?? 0;
            existing.gross_cents += grossCents;
            existing.net_cents += netCents;
            existing.discount_total_cents += discountTotalCents;
            compositionByRetailer.set(row.source_id, existing);
          }
        }
        const retailerTotals = Array.from(compositionByRetailer.values());
        const totalGrossCents = retailerTotals.reduce((sum, row) => sum + row.gross_cents, 0);
        const totalNetCents = retailerTotals.reduce((sum, row) => sum + row.net_cents, 0);
        const totalSavedCents = retailerTotals.reduce((sum, row) => sum + row.discount_total_cents, 0);
        const composition = {
          retailers: retailerTotals
            .map((row) => ({
              source_id: row.source_id,
              retailer: row.retailer,
              receipt_count: row.receipt_count,
              gross_cents: row.gross_cents,
              gross_currency: centsToCurrency(row.gross_cents),
              net_cents: row.net_cents,
              net_currency: centsToCurrency(row.net_cents),
              discount_total_cents: row.discount_total_cents,
              discount_total_currency: centsToCurrency(row.discount_total_cents),
              paid_cents: row.net_cents,
              paid_currency: centsToCurrency(row.net_cents),
              saved_cents: row.discount_total_cents,
              saved_currency: centsToCurrency(row.discount_total_cents),
              gross_share: safeRatio(row.gross_cents, totalGrossCents),
              net_share: safeRatio(row.net_cents, totalNetCents),
              paid_share: safeRatio(row.net_cents, totalNetCents),
              saved_share: safeRatio(row.discount_total_cents, totalSavedCents),
              savings_rate: safeRatio(row.discount_total_cents, row.gross_cents)
            }))
            .sort((left, right) => right.saved_cents - left.saved_cents)
        };

        const warnings = uniqueWarnings([
          ...cardsResponses,
          ...breakdownResponses,
          ...compositionResponses,
          trendsResponse
        ]);
        return {
          cards,
          trends: trendsResponse.result,
          breakdown,
          composition,
          deposit,
          warnings
        };
      }

      const selectedMonth = periodMode === "month" ? month : undefined;
      const trendMonthsBack = periodMode === "year" ? 12 : 6;
      const trendEndMonth = periodMode === "year" ? 12 : month;

      const [cardsResponse, trendsResponse, breakdownResponse, compositionResponse, deposit] = await Promise.all([
        fetchDashboardCardsWithWarnings(year, selectedMonth, normalizedSourceIds),
        fetchDashboardTrendsWithWarnings(year, trendMonthsBack, trendEndMonth, normalizedSourceIds),
        fetchSavingsBreakdownWithWarnings(year, selectedMonth, view, normalizedSourceIds),
        fetchRetailerCompositionWithWarnings(year, selectedMonth, normalizedSourceIds),
        fetchDepositAnalytics({
          ...periodWindow(),
          sourceIds: normalizedSourceIds
        })
      ]);
      const warnings = uniqueWarnings([
        cardsResponse,
        trendsResponse,
        breakdownResponse,
        compositionResponse
      ]);
      return {
        cards: cardsResponse.result,
        trends: trendsResponse.result,
        breakdown: breakdownResponse.result,
        composition: compositionResponse.result,
        deposit,
        warnings
      };
    }
  });
}

export function transactionsQueryOptions(filters: TransactionsFilters) {
  return queryOptions({
    queryKey: queryKeys.transactions(filters),
    queryFn: () => fetchTransactions(filters)
  });
}

export function transactionDetailQueryOptions(transactionId: string) {
  return queryOptions({
    queryKey: queryKeys.transactionDetail(transactionId),
    queryFn: async () => {
      const [detail, history] = await Promise.all([
        fetchTransactionDetail(transactionId),
        fetchTransactionHistory(transactionId)
      ]);
      return { detail, history };
    }
  });
}

export function reviewQueueQueryOptions(filters: ReviewQueueFilters) {
  const normalizedFilters: Required<ReviewQueueFilters> = {
    status: filters.status ?? "needs_review",
    threshold: filters.threshold ?? 0.85,
    limit: filters.limit ?? 50,
    offset: filters.offset ?? 0
  };
  return queryOptions({
    queryKey: queryKeys.reviewQueue(normalizedFilters),
    queryFn: () =>
      fetchReviewQueue({
        status: normalizedFilters.status || undefined,
        threshold: normalizedFilters.threshold,
        limit: normalizedFilters.limit,
        offset: normalizedFilters.offset
      })
  });
}

export function reviewQueueDetailQueryOptions(documentId: string) {
  return queryOptions({
    queryKey: queryKeys.reviewQueueDetail(documentId),
    queryFn: () => fetchReviewQueueDetail(documentId)
  });
}

export function automationRulesQueryOptions(limit = 200, offset = 0) {
  return queryOptions({
    queryKey: queryKeys.automationRules(limit, offset),
    queryFn: () => fetchAutomationRules(limit, offset)
  });
}

export function automationExecutionsQueryOptions(filters: AutomationExecutionsFilters) {
  const normalizedFilters: Required<AutomationExecutionsFilters> = {
    status: filters.status ?? "",
    ruleType: filters.ruleType ?? "",
    limit: filters.limit ?? 200,
    offset: filters.offset ?? 0
  };
  return queryOptions({
    queryKey: queryKeys.automationExecutions(normalizedFilters),
    queryFn: () =>
      fetchAutomationExecutions({
        status: normalizedFilters.status || undefined,
        ruleType: normalizedFilters.ruleType || undefined,
        limit: normalizedFilters.limit,
        offset: normalizedFilters.offset
      })
  });
}

export function reliabilitySloQueryOptions(filters: ReliabilitySloFilters) {
  const normalizedFilters: Required<ReliabilitySloFilters> = {
    windowHours: filters.windowHours ?? 24,
    syncP95TargetMs: filters.syncP95TargetMs ?? 2500,
    analyticsP95TargetMs: filters.analyticsP95TargetMs ?? 2000,
    minSuccessRate: filters.minSuccessRate ?? 0.97
  };
  return queryOptions({
    queryKey: queryKeys.reliabilitySlo(normalizedFilters),
    queryFn: () =>
      fetchReliabilitySlo({
        windowHours: normalizedFilters.windowHours,
        syncP95TargetMs: normalizedFilters.syncP95TargetMs,
        analyticsP95TargetMs: normalizedFilters.analyticsP95TargetMs,
        minSuccessRate: normalizedFilters.minSuccessRate
      })
  });
}
