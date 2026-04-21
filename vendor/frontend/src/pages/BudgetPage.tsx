import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CalendarClock, CircleAlert, PiggyBank, ReceiptText, TrendingDown, TrendingUp, Wallet } from "lucide-react";

import {
  createBudgetRule,
  fetchBudgetRules,
  fetchBudgetUtilization
} from "@/api/analytics";
import {
  createCashflowEntry,
  deleteCashflowEntry,
  fetchBudgetMonth,
  fetchBudgetSummary,
  fetchCashflowEntries,
  updateBudgetMonth,
  updateCashflowEntry,
  type BudgetMonth,
  type BudgetSummary,
  type CashflowEntry
} from "@/api/budget";
import { fetchTransactions, type TransactionListItem } from "@/api/transactions";
import { EmptyState } from "@/components/shared/EmptyState";
import { MetricCard } from "@/components/shared/MetricCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { formatDate, formatEurFromCents, formatMonthYear, formatPercent } from "@/utils/format";

type MonthFormState = {
  plannedIncome: string;
  targetSavings: string;
  openingBalance: string;
  notes: string;
};

type CashflowFormState = {
  effectiveDate: string;
  direction: "inflow" | "outflow";
  category: string;
  amount: string;
  description: string;
  sourceType: string;
  notes: string;
};

type BudgetRuleFormState = {
  scopeType: "category" | "source_kind";
  scopeValue: string;
  period: "monthly" | "annual";
  amount: string;
};

type CashflowFilterState = {
  direction: "all" | "inflow" | "outflow";
  status: "all" | "open" | "reconciled";
  category: string;
};

type FeedbackState = {
  kind: "success" | "error";
  message: string;
} | null;

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function monthDisplayValue(monthValue: string): { year: number; month: number } {
  const [yearRaw, monthRaw] = monthValue.split("-");
  const year = Number(yearRaw);
  const month = Number(monthRaw);
  if (!Number.isFinite(year) || !Number.isFinite(month)) {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  }
  return { year, month };
}

function monthStartDateValue(year: number, month: number): string {
  const date = new Date(year, month - 1, 1);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function parseEuroAmountToCents(raw: string): number | null {
  const normalized = raw.trim().replace(",", ".");
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.round(parsed * 100);
}

function centsToInputValue(value: number | null): string {
  if (value === null) {
    return "";
  }
  return String((value / 100).toFixed(2));
}

function budgetMonthToFormState(month: BudgetMonth): MonthFormState {
  return {
    plannedIncome: centsToInputValue(month.planned_income_cents),
    targetSavings: centsToInputValue(month.target_savings_cents),
    openingBalance: centsToInputValue(month.opening_balance_cents),
    notes: month.notes ?? ""
  };
}

function cashflowToFormState(entry: CashflowEntry): CashflowFormState {
  return {
    effectiveDate: entry.effective_date,
    direction: entry.direction,
    category: entry.category,
    amount: centsToInputValue(entry.amount_cents),
    description: entry.description ?? "",
    sourceType: entry.source_type,
    notes: entry.notes ?? ""
  };
}

function emptyCashflowFormState(defaultDate: string): CashflowFormState {
  return {
    effectiveDate: defaultDate,
    direction: "outflow",
    category: "groceries",
    amount: "",
    description: "",
    sourceType: "manual",
    notes: ""
  };
}

function emptyBudgetRuleFormState(): BudgetRuleFormState {
  return {
    scopeType: "category",
    scopeValue: "",
    period: "monthly",
    amount: ""
  };
}

function emptyCashflowFilterState(): CashflowFilterState {
  return {
    direction: "all",
    status: "all",
    category: ""
  };
}

function summaryBasisLabel(summary: BudgetSummary): string {
  const { income_basis, income_basis_cents } = summary.totals;
  return income_basis_cents > 0 ? `${income_basis} (${formatEurFromCents(income_basis_cents)})` : income_basis;
}

function recurringPaidAmount(item: BudgetSummary["recurring"]["items"][number]): number {
  if (item.actual_amount_cents !== null) {
    return item.actual_amount_cents;
  }
  if (item.status === "paid" && item.expected_amount_cents !== null) {
    return item.expected_amount_cents;
  }
  return 0;
}

const passthroughTranslate = (key: string) => key;

const CASHFLOW_PRESETS: Array<{
  key: string;
  label: string;
  hint: string;
  values: Pick<CashflowFormState, "direction" | "category" | "description" | "sourceType">;
}> = [
  {
    key: "cash-expense",
    label: "Cash expense",
    hint: "Missed purchase or small cash charge",
    values: {
      direction: "outflow",
      category: "cash",
      description: "Cash expense",
      sourceType: "manual_cash"
    }
  },
  {
    key: "income",
    label: "Income",
    hint: "Salary, transfer, or side income",
    values: {
      direction: "inflow",
      category: "salary",
      description: "Income",
      sourceType: "manual_income"
    }
  },
  {
    key: "refund",
    label: "Refund",
    hint: "Refund, reimbursement, or returned item",
    values: {
      direction: "inflow",
      category: "refund",
      description: "Refund",
      sourceType: "manual_refund"
    }
  }
];

const COMMON_CASHFLOW_CATEGORIES = [
  "cash",
  "transport",
  "eating_out",
  "rent",
  "utilities",
  "medical",
  "salary",
  "refund",
  "misc",
  "groceries"
];

export function BudgetPage() {
  const queryClient = useQueryClient();
  const [monthValue, setMonthValue] = useState(currentMonthValue());
  const { year, month } = monthDisplayValue(monthValue);
  const defaultDate = monthStartDateValue(year, month);

  const [monthForm, setMonthForm] = useState<MonthFormState>({
    plannedIncome: "",
    targetSavings: "",
    openingBalance: "",
    notes: ""
  });
  const [cashflowForm, setCashflowForm] = useState<CashflowFormState>(emptyCashflowFormState(defaultDate));
  const [editingCashflowId, setEditingCashflowId] = useState<string | null>(null);
  const [cashflowFilters, setCashflowFilters] = useState<CashflowFilterState>(emptyCashflowFilterState());
  const [reconcileEntryId, setReconcileEntryId] = useState<string | null>(null);
  const [receiptSearch, setReceiptSearch] = useState("");
  const [budgetRuleForm, setBudgetRuleForm] = useState<BudgetRuleFormState>(emptyBudgetRuleFormState());
  const [feedback, setFeedback] = useState<FeedbackState>(null);

  useEffect(() => {
    setCashflowForm((previous) => {
      if (editingCashflowId) {
        return previous;
      }
      return {
        ...previous,
        effectiveDate: defaultDate
      };
    });
  }, [defaultDate, editingCashflowId]);

  const budgetMonthQuery = useQuery({
    queryKey: ["budget-month", year, month],
    queryFn: () => fetchBudgetMonth(year, month)
  });

  const budgetSummaryQuery = useQuery({
    queryKey: ["budget-summary", year, month],
    queryFn: () => fetchBudgetSummary(year, month)
  });

  const cashflowQuery = useQuery({
    queryKey: [
      "cashflow-entries",
      year,
      month,
      cashflowFilters.direction,
      cashflowFilters.status,
      cashflowFilters.category.trim().toLowerCase()
    ],
    queryFn: () =>
      fetchCashflowEntries(year, month, {
        direction: cashflowFilters.direction === "all" ? undefined : cashflowFilters.direction,
        category: cashflowFilters.category.trim() || undefined,
        reconciled:
          cashflowFilters.status === "all"
            ? undefined
            : cashflowFilters.status === "reconciled"
      })
  });

  const receiptCandidatesQuery = useQuery({
    enabled: reconcileEntryId !== null,
    queryKey: [
      "budget-receipt-candidates",
      year,
      month,
      reconcileEntryId,
      receiptSearch.trim().toLowerCase()
    ],
    queryFn: () =>
      fetchTransactions({
        year,
        month,
        query: receiptSearch.trim() || undefined,
        minTotalCents: reconcileEntry ? Math.max(reconcileEntry.amount_cents - 5_000, 0) : undefined,
        maxTotalCents: reconcileEntry ? reconcileEntry.amount_cents + 5_000 : undefined,
        sortBy: "purchased_at",
        sortDir: "desc",
        limit: 8,
        offset: 0
      })
  });

  const budgetRulesQuery = useQuery({
    queryKey: ["budget-rules"],
    queryFn: fetchBudgetRules
  });

  const budgetUtilizationQuery = useQuery({
    queryKey: ["budget-utilization", year, month],
    queryFn: () => fetchBudgetUtilization({ year, month })
  });

  useEffect(() => {
    if (budgetMonthQuery.data) {
      setMonthForm(budgetMonthToFormState(budgetMonthQuery.data));
    }
  }, [budgetMonthQuery.data]);

  useEffect(() => {
    setFeedback(null);
  }, [monthValue]);

  useEffect(() => {
    setReceiptSearch("");
    setReconcileEntryId(null);
  }, [monthValue]);

  const saveMonthMutation = useMutation({
    mutationFn: async (payload: MonthFormState) =>
      updateBudgetMonth(year, month, {
        planned_income_cents: parseEuroAmountToCents(payload.plannedIncome),
        target_savings_cents: parseEuroAmountToCents(payload.targetSavings),
        opening_balance_cents: parseEuroAmountToCents(payload.openingBalance),
        currency: budgetMonthQuery.data?.currency ?? "EUR",
        notes: payload.notes.trim() || null
      }),
    onSuccess: (result) => {
      setFeedback({ kind: "success", message: `Saved budget for ${formatMonthYear(`${year}-${String(month).padStart(2, "0")}-01T00:00:00`)}` });
      setMonthForm(budgetMonthToFormState(result));
      void queryClient.invalidateQueries({ queryKey: ["budget-month", year, month] });
      void queryClient.invalidateQueries({ queryKey: ["budget-summary", year, month] });
    },
    onError: (error) => {
      setFeedback({ kind: "error", message: resolveApiErrorMessage(error, passthroughTranslate, "Failed to save month budget") });
    }
  });

  const saveCashflowMutation = useMutation({
    mutationFn: async (payload: CashflowFormState) => {
      const amountCents = parseEuroAmountToCents(payload.amount);
      if (amountCents === null || amountCents <= 0) {
        throw new Error("Amount must be a valid euro value");
      }
      const request = {
        effective_date: payload.effectiveDate,
        direction: payload.direction,
        category: payload.category.trim() || "misc",
        amount_cents: amountCents,
        currency: budgetMonthQuery.data?.currency ?? "EUR",
        description: payload.description.trim(),
        source_type: payload.sourceType.trim() || "manual",
        notes: payload.notes.trim() || null
      };
      if (editingCashflowId) {
        return updateCashflowEntry(editingCashflowId, request);
      }
      return createCashflowEntry(request);
    },
    onSuccess: () => {
      setFeedback({
        kind: "success",
        message: editingCashflowId ? "Updated cash-flow entry." : "Created cash-flow entry."
      });
      setEditingCashflowId(null);
      setCashflowForm(emptyCashflowFormState(defaultDate));
      void queryClient.invalidateQueries({ queryKey: ["cashflow-entries", year, month] });
      void queryClient.invalidateQueries({ queryKey: ["budget-summary", year, month] });
    },
    onError: (error) => {
      setFeedback({ kind: "error", message: resolveApiErrorMessage(error, passthroughTranslate, "Failed to save cash-flow entry") });
    }
  });

  const deleteCashflowMutation = useMutation({
    mutationFn: deleteCashflowEntry,
    onSuccess: () => {
      setFeedback({ kind: "success", message: "Deleted cash-flow entry." });
      void queryClient.invalidateQueries({ queryKey: ["cashflow-entries", year, month] });
      void queryClient.invalidateQueries({ queryKey: ["budget-summary", year, month] });
    },
    onError: (error) => {
      setFeedback({ kind: "error", message: resolveApiErrorMessage(error, passthroughTranslate, "Failed to delete cash-flow entry") });
    }
  });

  const reconcileCashflowMutation = useMutation({
    mutationFn: async (payload: { entryId: string; linkedTransactionId: string | null }) =>
      updateCashflowEntry(payload.entryId, { linked_transaction_id: payload.linkedTransactionId }),
    onSuccess: (_, variables) => {
      setFeedback({
        kind: "success",
        message: variables.linkedTransactionId ? "Linked cash-flow entry to receipt." : "Removed receipt link."
      });
      setReconcileEntryId(null);
      setReceiptSearch("");
      void queryClient.invalidateQueries({ queryKey: ["cashflow-entries"] });
      void queryClient.invalidateQueries({ queryKey: ["budget-summary", year, month] });
    },
    onError: (error) => {
      setFeedback({
        kind: "error",
        message: resolveApiErrorMessage(error, passthroughTranslate, "Failed to reconcile cash-flow entry")
      });
    }
  });

  const budgetRuleMutation = useMutation({
    mutationFn: async (payload: BudgetRuleFormState) => {
      const amountCents = parseEuroAmountToCents(payload.amount);
      if (amountCents === null || amountCents <= 0) {
        throw new Error("Budget rule amount must be greater than zero");
      }
      return createBudgetRule({
        scope_type: payload.scopeType,
        scope_value: payload.scopeValue.trim(),
        period: payload.period,
        amount_cents: amountCents,
        currency: budgetMonthQuery.data?.currency ?? "EUR",
        active: true
      });
    },
    onSuccess: () => {
      setBudgetRuleForm(emptyBudgetRuleFormState());
      void queryClient.invalidateQueries({ queryKey: ["budget-rules"] });
      void queryClient.invalidateQueries({ queryKey: ["budget-utilization"] });
      void queryClient.invalidateQueries({ queryKey: ["budget-summary", year, month] });
    },
    onError: (error) => {
      setFeedback({ kind: "error", message: resolveApiErrorMessage(error, passthroughTranslate, "Failed to create budget rule") });
    }
  });

  const summary = budgetSummaryQuery.data;
  const cashflowEntries = cashflowQuery.data?.items ?? [];
  const receiptCandidates = receiptCandidatesQuery.data?.items ?? [];
  const budgetRules = budgetRulesQuery.data?.items ?? [];
  const utilizationRows = budgetUtilizationQuery.data?.rows ?? [];
  const reconcileEntry = cashflowEntries.find((entry) => entry.id === reconcileEntryId) ?? null;

  const displayBudgetMonth = summary?.month ?? budgetMonthQuery.data;
  const currency = displayBudgetMonth?.currency ?? "EUR";
  const summaryMetrics = useMemo(() => {
    const recurringItems = summary?.recurring.items ?? [];
    const recurringExpectedFallback = recurringItems.reduce(
      (total, item) => total + (item.expected_amount_cents ?? 0),
      0
    );
    const recurringPaidFallback = recurringItems.reduce(
      (total, item) => total + recurringPaidAmount(item),
      0
    );
    const recurringPaidCountFallback = recurringItems.filter(
      (item) => item.status === "paid" || item.actual_amount_cents !== null
    ).length;
    const recurringUnpaidCountFallback = Math.max(recurringItems.length - recurringPaidCountFallback, 0);

    const inflowFallback = cashflowEntries
      .filter((entry) => entry.direction === "inflow")
      .reduce((total, entry) => total + entry.amount_cents, 0);
    const manualOutflowFallback = cashflowEntries
      .filter((entry) => entry.direction === "outflow" && !entry.is_reconciled)
      .reduce((total, entry) => total + entry.amount_cents, 0);
    const reconciledFallback = cashflowEntries.filter((entry) => entry.is_reconciled).length;

    const plannedIncomeFallback = displayBudgetMonth?.planned_income_cents ?? null;
    const openingBalanceFallback = displayBudgetMonth?.opening_balance_cents ?? null;
    const targetSavingsFallback = displayBudgetMonth?.target_savings_cents ?? null;
    const receiptSpendValue = summary?.totals.receipt_spend_cents ?? 0;
    const actualIncomeValue = Math.max(summary?.totals.actual_income_cents ?? 0, inflowFallback);
    const plannedIncomeValue = summary?.totals.planned_income_cents ?? plannedIncomeFallback;
    const recurringExpectedValue = Math.max(summary?.totals.recurring_expected_cents ?? 0, recurringExpectedFallback);
    const recurringPaidValue = Math.max(summary?.totals.recurring_paid_cents ?? 0, recurringPaidFallback);
    const manualOutflowValue = Math.max(summary?.totals.manual_outflow_cents ?? 0, manualOutflowFallback);
    const totalOutflowValue = Math.max(
      summary?.totals.total_outflow_cents ?? 0,
      receiptSpendValue + manualOutflowValue
    );
    const incomeBasisCentsValue = Math.max(
      summary?.totals.income_basis_cents ?? 0,
      plannedIncomeValue ?? 0,
      actualIncomeValue
    );
    const availableValue = Math.max(
      summary?.totals.available_cents ?? 0,
      incomeBasisCentsValue + (openingBalanceFallback ?? 0)
    );
    const remainingValue = Math.max(summary?.totals.remaining_cents ?? 0, availableValue - totalOutflowValue);
    const savedValue = Math.max(summary?.totals.saved_cents ?? 0, incomeBasisCentsValue - totalOutflowValue);
    const savingsDeltaValue =
      summary?.totals.savings_delta_cents ??
      (targetSavingsFallback !== null ? savedValue - targetSavingsFallback : savedValue);

    const incomeBasisLabelValue = summary
      ? summaryBasisLabel(summary)
      : incomeBasisCentsValue > 0
        ? `${plannedIncomeValue !== null ? "planned_income" : "actual_income"} (${formatEurFromCents(incomeBasisCentsValue)})`
        : "—";

    return {
      plannedIncome: plannedIncomeValue,
      actualIncome: actualIncomeValue,
      remaining: remainingValue,
      available: availableValue,
      recurringExpected: recurringExpectedValue,
      recurringPaid: recurringPaidValue,
      receiptSpend: receiptSpendValue,
      manualOutflow: manualOutflowValue,
      totalOutflow: totalOutflowValue,
      saved: savedValue,
      reconciledCount: Math.max(summary?.cashflow.reconciled_count ?? 0, reconciledFallback),
      openAdjustmentCount: Math.max(
        Math.max(summary?.cashflow.count ?? 0, cashflowEntries.length) -
          Math.max(summary?.cashflow.reconciled_count ?? 0, reconciledFallback),
        0
      ),
      recurringPaidCount: Math.max(summary?.recurring.paid_count ?? 0, recurringPaidCountFallback),
      recurringUnpaidCount: Math.max(summary?.recurring.unpaid_count ?? 0, recurringUnpaidCountFallback),
      incomeBasisLabel: incomeBasisLabelValue,
      savingsDelta: savingsDeltaValue
    };
  }, [cashflowEntries, displayBudgetMonth, summary]);
  const plannedIncome = summaryMetrics.plannedIncome;
  const actualIncome = summaryMetrics.actualIncome;
  const remaining = summaryMetrics.remaining;
  const available = summaryMetrics.available;
  const recurringExpected = summaryMetrics.recurringExpected;
  const recurringPaid = summaryMetrics.recurringPaid;
  const receiptSpend = summaryMetrics.receiptSpend;
  const manualOutflow = summaryMetrics.manualOutflow;
  const totalOutflow = summaryMetrics.totalOutflow;
  const saved = summaryMetrics.saved;
  const reconciledCount = summaryMetrics.reconciledCount;
  const openAdjustmentCount = summaryMetrics.openAdjustmentCount;

  function handleMonthSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void saveMonthMutation.mutateAsync(monthForm);
  }

  function handleCashflowSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!cashflowForm.description.trim()) {
      setFeedback({ kind: "error", message: "Cash-flow description is required." });
      return;
    }
    void saveCashflowMutation.mutateAsync(cashflowForm);
  }

  function startCashflowEdit(entry: CashflowEntry): void {
    setReconcileEntryId(null);
    setReceiptSearch("");
    setEditingCashflowId(entry.id);
    setCashflowForm(cashflowToFormState(entry));
  }

  function cancelCashflowEdit(): void {
    setEditingCashflowId(null);
    setCashflowForm(emptyCashflowFormState(defaultDate));
  }

  function applyCashflowPreset(
    preset: Pick<CashflowFormState, "direction" | "category" | "description" | "sourceType">
  ): void {
    setEditingCashflowId(null);
    setCashflowForm({
      ...emptyCashflowFormState(defaultDate),
      effectiveDate: cashflowForm.effectiveDate || defaultDate,
      ...preset
    });
  }

  function formatReceiptCandidateLabel(transaction: TransactionListItem): string {
    return transaction.store_name?.trim() || "Unknown merchant";
  }

  return (
    <section className="space-y-6">
      <PageHeader title="Budget" description="Track monthly income, recurring bills, receipt spend, and savings." />

      {feedback ? (
        <p className={feedback.kind === "error" ? "text-sm text-destructive" : "text-sm text-success"}>
          {feedback.message}
        </p>
      ) : null}

      <div className="flex flex-col gap-3 md:flex-row md:items-end">
        <div className="space-y-2">
          <Label htmlFor="budget-month">Month</Label>
          <Input
            id="budget-month"
            type="month"
            value={monthValue}
            onChange={(event) => setMonthValue(event.target.value)}
          />
        </div>
        <div className="flex-1 space-y-1">
          <p className="text-xs text-muted-foreground">
            {displayBudgetMonth?.notes?.trim() ? displayBudgetMonth.notes : "No notes set for this month yet."}
          </p>
        </div>
      </div>

      <section className="rounded-xl border border-border/60 app-dashboard-surface grid divide-y lg:divide-y-0 lg:divide-x divide-border/40 lg:grid-cols-3">
        <MetricCard
          title="Income"
          value={formatEurFromCents(actualIncome)}
          subtitle={plannedIncome !== null ? `Planned ${formatEurFromCents(plannedIncome)}` : "No planned income yet"}
          icon={<Wallet className="h-3.5 w-3.5" />}
          iconClassName="bg-primary/10 text-primary"
        />
        <MetricCard
          title="Outflow"
          value={formatEurFromCents(totalOutflow)}
          subtitle={`Receipts ${formatEurFromCents(receiptSpend)} · manual ${formatEurFromCents(manualOutflow)} · ${reconciledCount} reconciled`}
          icon={<TrendingDown className="h-3.5 w-3.5" />}
          iconClassName="bg-destructive/10 text-destructive"
        />
        <MetricCard
          title="Remaining"
          value={formatEurFromCents(remaining)}
          subtitle={`Available ${formatEurFromCents(available)} · saved ${formatEurFromCents(saved)}`}
          icon={<PiggyBank className="h-3.5 w-3.5" />}
          iconClassName="bg-success/10 text-success"
        />
        <MetricCard
          title="Recurring"
          value={formatEurFromCents(recurringExpected)}
          subtitle={`${summaryMetrics.recurringPaidCount} paid / ${summaryMetrics.recurringUnpaidCount} unpaid`}
          icon={<CalendarCheck className="h-3.5 w-3.5" />}
          iconClassName="bg-chart-2/10 text-chart-2"
        />
        <MetricCard
          title="Income basis"
          value={summaryMetrics.incomeBasisLabel}
          subtitle={`Savings delta ${formatEurFromCents(summaryMetrics.savingsDelta)}`}
          icon={<TrendingUp className="h-3.5 w-3.5" />}
          iconClassName="bg-amber-500/10 text-amber-600"
        />
        <MetricCard
          title="Recurring bills"
          value={formatEurFromCents(recurringPaid)}
          subtitle={`Forecast ${formatEurFromCents(recurringExpected)}`}
          icon={<ReceiptText className="h-3.5 w-3.5" />}
          iconClassName="bg-muted text-muted-foreground"
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Monthly Budget Settings</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 md:grid-cols-2" onSubmit={handleMonthSubmit}>
              <div className="space-y-2">
                <Label htmlFor="planned-income">Planned income (EUR)</Label>
                <Input
                  id="planned-income"
                  value={monthForm.plannedIncome}
                  onChange={(event) => setMonthForm((previous) => ({ ...previous, plannedIncome: event.target.value }))}
                  placeholder="3200.00"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="target-savings">Target savings (EUR)</Label>
                <Input
                  id="target-savings"
                  value={monthForm.targetSavings}
                  onChange={(event) => setMonthForm((previous) => ({ ...previous, targetSavings: event.target.value }))}
                  placeholder="300.00"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="opening-balance">Opening balance (EUR)</Label>
                <Input
                  id="opening-balance"
                  value={monthForm.openingBalance}
                  onChange={(event) => setMonthForm((previous) => ({ ...previous, openingBalance: event.target.value }))}
                  placeholder="1250.00"
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="month-notes">Notes</Label>
                <Textarea
                  id="month-notes"
                  value={monthForm.notes}
                  onChange={(event) => setMonthForm((previous) => ({ ...previous, notes: event.target.value }))}
                  placeholder="Monthly priorities, one-off expenses, savings goals..."
                />
              </div>
              <div className="md:col-span-2 flex items-center gap-3">
                <Button type="submit" disabled={saveMonthMutation.isPending}>
                  Save month settings
                </Button>
                <span className="text-sm text-muted-foreground">
                  Current currency: {currency}
                </span>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Recurring Commitments</CardTitle>
            <CircleAlert className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {(summary?.recurring.items ?? []).length === 0 ? (
              <EmptyState
                title="No recurring items"
                description="Recurring bills will appear here once they are configured and matched."
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Due</TableHead>
                    <TableHead>Bill</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Expected</TableHead>
                    <TableHead className="text-right">Actual</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(summary?.recurring.items ?? []).map((item) => (
                    <TableRow key={item.occurrence_id}>
                      <TableCell>{formatDate(item.due_date)}</TableCell>
                      <TableCell>{item.bill_name}</TableCell>
                      <TableCell className="capitalize">{item.status}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {item.expected_amount_cents === null ? "Variable" : formatEurFromCents(item.expected_amount_cents)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {item.actual_amount_cents === null ? "—" : formatEurFromCents(item.actual_amount_cents)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cash-Flow Entries</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-3 lg:grid-cols-3">
            {CASHFLOW_PRESETS.map((preset) => (
              <Button
                key={preset.key}
                type="button"
                variant="outline"
                className="h-auto justify-start px-4 py-3 text-left"
                onClick={() => applyCashflowPreset(preset.values)}
              >
                <span className="block">
                  <span className="block font-medium">{preset.label}</span>
                  <span className="block text-xs text-muted-foreground">{preset.hint}</span>
                </span>
              </Button>
            ))}
          </div>

          <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={handleCashflowSubmit}>
            <div className="space-y-2">
              <Label htmlFor="cashflow-date">Date</Label>
              <Input
                id="cashflow-date"
                type="date"
                value={cashflowForm.effectiveDate}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, effectiveDate: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-direction">Direction</Label>
              <Select
                value={cashflowForm.direction}
                onValueChange={(value) => setCashflowForm((previous) => ({ ...previous, direction: value as "inflow" | "outflow" }))}
              >
                <SelectTrigger id="cashflow-direction">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="inflow">Inflow</SelectItem>
                  <SelectItem value="outflow">Outflow</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-category">Category</Label>
              <Input
                id="cashflow-category"
                list="cashflow-category-options"
                value={cashflowForm.category}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, category: event.target.value }))}
                placeholder="salary, groceries, rent, refund"
              />
              <datalist id="cashflow-category-options">
                {COMMON_CASHFLOW_CATEGORIES.map((category) => (
                  <option key={category} value={category} />
                ))}
              </datalist>
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-amount">Amount (EUR)</Label>
              <Input
                id="cashflow-amount"
                value={cashflowForm.amount}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, amount: event.target.value }))}
                placeholder="1200.00"
              />
            </div>
            <div className="space-y-2 md:col-span-2 xl:col-span-2">
              <Label htmlFor="cashflow-description">Description</Label>
              <Input
                id="cashflow-description"
                value={cashflowForm.description}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, description: event.target.value }))}
                placeholder="Salary payout, supermarket cash spend, refund"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-source-type">Source type</Label>
              <Input
                id="cashflow-source-type"
                value={cashflowForm.sourceType}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, sourceType: event.target.value }))}
                placeholder="manual"
              />
            </div>
            <div className="space-y-2 md:col-span-2 xl:col-span-2">
              <Label htmlFor="cashflow-notes">Notes</Label>
              <Textarea
                id="cashflow-notes"
                value={cashflowForm.notes}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, notes: event.target.value }))}
                placeholder="Optional context"
              />
            </div>
            <div className="flex flex-wrap items-center gap-3 md:col-span-2 xl:col-span-4">
              <Button type="submit" disabled={saveCashflowMutation.isPending}>
                {editingCashflowId ? "Update entry" : "Add entry"}
              </Button>
              {editingCashflowId ? (
                <Button type="button" variant="outline" onClick={cancelCashflowEdit}>
                  Cancel edit
                </Button>
              ) : null}
              <span className="text-sm text-muted-foreground">
                Open adjustments {openAdjustmentCount} · reconciled {reconciledCount}
              </span>
            </div>
          </form>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="cashflow-filter-direction">Direction</Label>
              <Select
                value={cashflowFilters.direction}
                onValueChange={(value) =>
                  setCashflowFilters((previous) => ({
                    ...previous,
                    direction: value as CashflowFilterState["direction"]
                  }))
                }
              >
                <SelectTrigger id="cashflow-filter-direction">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All directions</SelectItem>
                  <SelectItem value="inflow">Inflow</SelectItem>
                  <SelectItem value="outflow">Outflow</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-filter-status">Status</Label>
              <Select
                value={cashflowFilters.status}
                onValueChange={(value) =>
                  setCashflowFilters((previous) => ({
                    ...previous,
                    status: value as CashflowFilterState["status"]
                  }))
                }
              >
                <SelectTrigger id="cashflow-filter-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="open">Open corrections</SelectItem>
                  <SelectItem value="reconciled">Reconciled to receipt</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-filter-category">Category filter</Label>
              <Input
                id="cashflow-filter-category"
                list="cashflow-category-options"
                value={cashflowFilters.category}
                onChange={(event) =>
                  setCashflowFilters((previous) => ({ ...previous, category: event.target.value }))
                }
                placeholder="Filter by category"
              />
            </div>
          </div>

          <p className="text-sm text-muted-foreground">
            Manual outflows linked to a real receipt stay visible here, but they stop counting as extra spend in the month summary.
          </p>

          {cashflowEntries.length === 0 ? (
            <EmptyState
              title="No cash-flow entries"
              description="Add salary, refunds, and manual expenses to round out the monthly budget."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {cashflowEntries.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>{formatDate(entry.effective_date)}</TableCell>
                    <TableCell className="capitalize">{entry.direction}</TableCell>
                    <TableCell>{entry.category}</TableCell>
                    <TableCell className="max-w-[280px]">
                      <div className="truncate">{entry.description ?? "—"}</div>
                      {entry.notes ? (
                        <div className="truncate text-xs text-muted-foreground">{entry.notes}</div>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1 text-sm">
                        <div>{entry.is_reconciled ? "Reconciled" : "Open"}</div>
                        <div className="text-xs text-muted-foreground">{entry.source_type}</div>
                        {entry.linked_transaction ? (
                          <div className="text-xs text-muted-foreground">
                            {entry.linked_transaction.merchant_name ?? "Receipt"} · {formatDate(entry.linked_transaction.purchased_at)}
                          </div>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {entry.direction === "outflow" ? "-" : "+"}
                      {formatEurFromCents(entry.amount_cents)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button type="button" variant="ghost" size="sm" onClick={() => startCashflowEdit(entry)}>
                          Edit
                        </Button>
                        {entry.direction === "outflow" ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              if (entry.is_reconciled) {
                                reconcileCashflowMutation.mutate({
                                  entryId: entry.id,
                                  linkedTransactionId: null
                                });
                                return;
                              }
                              setEditingCashflowId(null);
                              setReconcileEntryId((previous) => (previous === entry.id ? null : entry.id));
                              setReceiptSearch("");
                            }}
                            disabled={reconcileCashflowMutation.isPending}
                          >
                            {entry.is_reconciled ? "Unlink receipt" : "Link receipt"}
                          </Button>
                        ) : null}
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => deleteCashflowMutation.mutate(entry.id)}
                          disabled={deleteCashflowMutation.isPending}
                        >
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {reconcileEntry ? (
            <div className="space-y-4 rounded-lg border border-primary/20 bg-primary/5 p-4">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <h3 className="text-sm font-medium">Link receipt to {reconcileEntry.description ?? "manual entry"}</h3>
                  <p className="text-sm text-muted-foreground">
                    Match this manual expense to a scraped receipt so it no longer counts twice.
                  </p>
                </div>
                <Button type="button" variant="outline" onClick={() => setReconcileEntryId(null)}>
                  Close
                </Button>
              </div>
              <div className="space-y-2">
                <Label htmlFor="receipt-search">Receipt search</Label>
                <Input
                  id="receipt-search"
                  value={receiptSearch}
                  onChange={(event) => setReceiptSearch(event.target.value)}
                  placeholder="Search merchant or receipt text"
                />
              </div>
              {receiptCandidatesQuery.isPending ? (
                <p className="text-sm text-muted-foreground">Searching receipts…</p>
              ) : null}
              {receiptCandidates.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No receipts found for this month. Try another search term or keep the manual entry open for now.
                </p>
              ) : (
                <div className="space-y-2">
                  {receiptCandidates.map((transaction) => (
                    <div
                      key={transaction.id}
                      className="app-soft-surface flex flex-col gap-3 rounded-md border p-3 md:flex-row md:items-center md:justify-between"
                    >
                      <div className="space-y-1">
                        <div className="font-medium">{formatReceiptCandidateLabel(transaction)}</div>
                        <div className="text-sm text-muted-foreground">
                          {formatDate(transaction.purchased_at)} · {formatEurFromCents(transaction.total_gross_cents)}
                        </div>
                      </div>
                      <Button
                        type="button"
                        onClick={() =>
                          reconcileCashflowMutation.mutate({
                            entryId: reconcileEntry.id,
                            linkedTransactionId: transaction.id
                          })
                        }
                        disabled={reconcileCashflowMutation.isPending}
                      >
                        Use receipt
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Budget Rules</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={(event) => {
            event.preventDefault();
            if (!budgetRuleForm.scopeValue.trim()) {
              setFeedback({ kind: "error", message: "Scope value is required for budget rules." });
              return;
            }
            void budgetRuleMutation.mutateAsync(budgetRuleForm);
          }}>
            <div className="space-y-2">
              <Label htmlFor="budget-rule-scope-type">Scope type</Label>
              <Select
                value={budgetRuleForm.scopeType}
                onValueChange={(value) => setBudgetRuleForm((previous) => ({ ...previous, scopeType: value as "category" | "source_kind" }))}
              >
                <SelectTrigger id="budget-rule-scope-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="category">Category</SelectItem>
                  <SelectItem value="source_kind">Source kind</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget-rule-scope-value">Scope value</Label>
              <Input
                id="budget-rule-scope-value"
                value={budgetRuleForm.scopeValue}
                onChange={(event) => setBudgetRuleForm((previous) => ({ ...previous, scopeValue: event.target.value }))}
                placeholder="groceries"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget-rule-period">Period</Label>
              <Select
                value={budgetRuleForm.period}
                onValueChange={(value) => setBudgetRuleForm((previous) => ({ ...previous, period: value as "monthly" | "annual" }))}
              >
                <SelectTrigger id="budget-rule-period">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">Monthly</SelectItem>
                  <SelectItem value="annual">Annual</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget-rule-amount">Amount (EUR)</Label>
              <Input
                id="budget-rule-amount"
                value={budgetRuleForm.amount}
                onChange={(event) => setBudgetRuleForm((previous) => ({ ...previous, amount: event.target.value }))}
                placeholder="450.00"
              />
            </div>
            <div className="md:col-span-2 xl:col-span-4">
              <Button type="submit" disabled={budgetRuleMutation.isPending}>
                Add budget rule
              </Button>
            </div>
          </form>

          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-3 text-sm font-medium">Rules</h3>
              {budgetRules.length === 0 ? (
                <EmptyState
                  title="No budget rules configured"
                  description="Create category or source limits to track overages."
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Scope</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Period</TableHead>
                      <TableHead className="text-right">Amount</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {budgetRules.map((rule) => (
                      <TableRow key={rule.rule_id}>
                        <TableCell>{rule.scope_type}</TableCell>
                        <TableCell>{rule.scope_value}</TableCell>
                        <TableCell>{rule.period}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatEurFromCents(rule.amount_cents)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
            <div>
              <h3 className="mb-3 text-sm font-medium">Utilization</h3>
              {utilizationRows.length === 0 ? (
                <EmptyState
                  title="No utilization data"
                  description="Budget utilization will appear after transactions match the configured rules."
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Scope</TableHead>
                      <TableHead className="text-right">Budget</TableHead>
                      <TableHead className="text-right">Spent</TableHead>
                      <TableHead className="text-right">Remaining</TableHead>
                      <TableHead className="text-right">Utilization</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {utilizationRows.map((row) => (
                      <TableRow key={row.rule_id}>
                        <TableCell>{row.scope_type}:{row.scope_value}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatEurFromCents(row.budget_cents)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatEurFromCents(row.spent_cents)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatEurFromCents(row.remaining_cents)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatPercent(row.utilization)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Budget rules remain a secondary control surface. The month summary above is the main planning view.
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
