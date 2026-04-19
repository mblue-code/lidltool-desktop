import { type FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CircleAlert, PiggyBank, ReceiptText, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import { Link } from "react-router-dom";

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
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { type TranslationKey, useI18n } from "@/i18n";
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

const CASHFLOW_PRESETS: Array<{
  key: string;
  labelKey: TranslationKey;
  hintKey: TranslationKey;
  descriptionKey: TranslationKey;
  values: Pick<CashflowFormState, "direction" | "category" | "sourceType">;
}> = [
  {
    key: "cash-expense",
    labelKey: "pages.budget.cashflow.preset.cashExpense.label",
    hintKey: "pages.budget.cashflow.preset.cashExpense.hint",
    descriptionKey: "pages.budget.cashflow.preset.cashExpense.label",
    values: {
      direction: "outflow",
      category: "cash",
      sourceType: "manual_cash"
    }
  },
  {
    key: "income",
    labelKey: "pages.budget.cashflow.preset.income.label",
    hintKey: "pages.budget.cashflow.preset.income.hint",
    descriptionKey: "pages.budget.cashflow.preset.income.label",
    values: {
      direction: "inflow",
      category: "salary",
      sourceType: "manual_income"
    }
  },
  {
    key: "refund",
    labelKey: "pages.budget.cashflow.preset.refund.label",
    hintKey: "pages.budget.cashflow.preset.refund.hint",
    descriptionKey: "pages.budget.cashflow.preset.refund.label",
    values: {
      direction: "inflow",
      category: "refund",
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

const COMMON_CASHFLOW_SOURCE_TYPES = [
  { value: "manual", labelKey: "pages.budget.cashflow.sourceTypeOption.manual" },
  { value: "manual_cash", labelKey: "pages.budget.cashflow.sourceTypeOption.manualCash" },
  { value: "manual_income", labelKey: "pages.budget.cashflow.sourceTypeOption.manualIncome" },
  { value: "manual_refund", labelKey: "pages.budget.cashflow.sourceTypeOption.manualRefund" },
  { value: "manual_transfer", labelKey: "pages.budget.cashflow.sourceTypeOption.manualTransfer" }
] as const satisfies ReadonlyArray<{ value: string; labelKey: TranslationKey }>;

function buildBillLinkTarget(billId: string, dueDate: string): string {
  return `/bills?bill=${encodeURIComponent(billId)}&month=${encodeURIComponent(dueDate.slice(0, 7))}`;
}

export function BudgetPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
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
      setFeedback({
        kind: "success",
        message: t("pages.budget.feedback.monthSaved", {
          month: formatMonthYear(`${year}-${String(month).padStart(2, "0")}-01T00:00:00`)
        })
      });
      setMonthForm(budgetMonthToFormState(result));
      void queryClient.invalidateQueries({ queryKey: ["budget-month", year, month] });
      void queryClient.invalidateQueries({ queryKey: ["budget-summary", year, month] });
    },
    onError: (error) => {
      setFeedback({
        kind: "error",
        message: resolveApiErrorMessage(error, t, t("pages.budget.feedback.monthSaveFailed"))
      });
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
        message: editingCashflowId
          ? t("pages.budget.feedback.cashflowUpdated")
          : t("pages.budget.feedback.cashflowCreated")
      });
      setEditingCashflowId(null);
      setCashflowForm(emptyCashflowFormState(defaultDate));
      void queryClient.invalidateQueries({ queryKey: ["cashflow-entries", year, month] });
      void queryClient.invalidateQueries({ queryKey: ["budget-summary", year, month] });
    },
    onError: (error) => {
      setFeedback({
        kind: "error",
        message: resolveApiErrorMessage(error, t, t("pages.budget.feedback.cashflowSaveFailed"))
      });
    }
  });

  const deleteCashflowMutation = useMutation({
    mutationFn: deleteCashflowEntry,
    onSuccess: () => {
      setFeedback({ kind: "success", message: t("pages.budget.feedback.cashflowDeleted") });
      void queryClient.invalidateQueries({ queryKey: ["cashflow-entries", year, month] });
      void queryClient.invalidateQueries({ queryKey: ["budget-summary", year, month] });
    },
    onError: (error) => {
      setFeedback({
        kind: "error",
        message: resolveApiErrorMessage(error, t, t("pages.budget.feedback.cashflowDeleteFailed"))
      });
    }
  });

  const reconcileCashflowMutation = useMutation({
    mutationFn: async (payload: { entryId: string; linkedTransactionId: string | null }) =>
      updateCashflowEntry(payload.entryId, { linked_transaction_id: payload.linkedTransactionId }),
    onSuccess: (_, variables) => {
      setFeedback({
        kind: "success",
        message: variables.linkedTransactionId
          ? t("pages.budget.feedback.cashflowLinked")
          : t("pages.budget.feedback.cashflowUnlinked")
      });
      setReconcileEntryId(null);
      setReceiptSearch("");
      void queryClient.invalidateQueries({ queryKey: ["cashflow-entries"] });
      void queryClient.invalidateQueries({ queryKey: ["budget-summary", year, month] });
    },
    onError: (error) => {
      setFeedback({
        kind: "error",
        message: resolveApiErrorMessage(error, t, t("pages.budget.feedback.cashflowReconcileFailed"))
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
      setFeedback({
        kind: "error",
        message: resolveApiErrorMessage(error, t, t("pages.budget.feedback.ruleCreateFailed"))
      });
    }
  });

  const summary = budgetSummaryQuery.data;
  const cashflowEntries = cashflowQuery.data?.items ?? [];
  const receiptCandidates = receiptCandidatesQuery.data?.items ?? [];
  const budgetRules = budgetRulesQuery.data?.items ?? [];
  const utilizationRows = budgetUtilizationQuery.data?.rows ?? [];
  const reconcileEntry = cashflowEntries.find((entry) => entry.id === reconcileEntryId) ?? null;

  const persistedBudgetMonth = budgetMonthQuery.data;
  const displayBudgetMonth = {
    ...(summary?.month ?? {}),
    ...(persistedBudgetMonth ?? {})
  };
  const currency = displayBudgetMonth.currency ?? "EUR";
  const plannedIncome = displayBudgetMonth.planned_income_cents ?? summary?.totals.planned_income_cents ?? null;
  const targetSavings = displayBudgetMonth.target_savings_cents ?? summary?.totals.target_savings_cents ?? null;
  const openingBalance = displayBudgetMonth.opening_balance_cents ?? summary?.totals.opening_balance_cents ?? null;
  const actualIncome = summary?.totals.actual_income_cents ?? 0;
  const recurringExpected = summary?.totals.recurring_expected_cents ?? 0;
  const recurringPaid = summary?.totals.recurring_paid_cents ?? 0;
  const receiptSpend = summary?.totals.receipt_spend_cents ?? 0;
  const manualOutflow = summary?.totals.manual_outflow_cents ?? 0;
  const totalOutflow = summary?.totals.total_outflow_cents ?? 0;
  const reconciledCount = summary?.cashflow.reconciled_count ?? 0;
  const openAdjustmentCount = Math.max((summary?.cashflow.count ?? 0) - reconciledCount, 0);
  const incomeBasis = actualIncome > 0 ? "actual" : "planned";
  const incomeBasisCents = actualIncome > 0 ? actualIncome : (plannedIncome ?? 0);
  const available = (openingBalance ?? 0) + incomeBasisCents;
  const remaining = available - totalOutflow;
  const saved = incomeBasisCents - totalOutflow;
  const savingsDelta = saved - (targetSavings ?? 0);

  function handleMonthSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void saveMonthMutation.mutateAsync(monthForm);
  }

  function handleCashflowSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!cashflowForm.description.trim()) {
      setFeedback({ kind: "error", message: t("pages.budget.cashflow.validation.descriptionRequired") });
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
    preset: Pick<CashflowFormState, "direction" | "category" | "sourceType"> & { descriptionKey: TranslationKey }
  ): void {
    setEditingCashflowId(null);
    setCashflowForm({
      ...emptyCashflowFormState(defaultDate),
      effectiveDate: cashflowForm.effectiveDate || defaultDate,
      ...preset,
      description: t(preset.descriptionKey)
    });
  }

  function formatReceiptCandidateLabel(transaction: TransactionListItem): string {
    return transaction.store_name?.trim() || t("pages.budget.cashflow.receiptCandidateUnknownMerchant");
  }

  function recurringStatusLabel(status: string): string {
    if (status === "paid") {
      return t("pages.budget.recurring.status.paid");
    }
    if (status === "due") {
      return t("pages.budget.recurring.status.due");
    }
    if (status === "overdue") {
      return t("pages.budget.recurring.status.overdue");
    }
    if (status === "skipped") {
      return t("pages.budget.recurring.status.skipped");
    }
    if (status === "unmatched") {
      return t("pages.budget.recurring.status.unmatched");
    }
    return t("pages.budget.recurring.status.upcoming");
  }

  return (
    <section className="space-y-6">
      <PageHeader title={t("pages.budget.title")} description={t("pages.budget.description")}>
        <Button asChild variant="outline">
          <Link to="/bills">{t("pages.budget.openBills")}</Link>
        </Button>
      </PageHeader>

      {feedback ? (
        <p className={feedback.kind === "error" ? "text-sm text-destructive" : "text-sm text-success"}>
          {feedback.message}
        </p>
      ) : null}

      <div className="flex flex-col gap-3 md:flex-row md:items-end">
        <div className="space-y-2">
          <Label htmlFor="budget-month">{t("pages.budget.month")}</Label>
          <Input
            id="budget-month"
            type="month"
            value={monthValue}
            onChange={(event) => setMonthValue(event.target.value)}
          />
        </div>
        <div className="flex-1 space-y-1">
          <p className="text-sm font-medium">{t("pages.budget.planTitle", { month: formatMonthYear(`${year}-${String(month).padStart(2, "0")}-01T00:00:00`) })}</p>
          <p className="text-xs text-muted-foreground">
            {displayBudgetMonth.notes?.trim() ? displayBudgetMonth.notes : t("pages.budget.noNotes")}
          </p>
        </div>
      </div>

      <Card className="app-soft-surface border-border/60">
        <CardContent className="grid gap-3 p-4 md:grid-cols-3">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">1</p>
            <p className="font-medium">{t("pages.budget.guide.stepOne.title")}</p>
            <p className="text-sm text-muted-foreground">{t("pages.budget.guide.stepOne.body")}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">2</p>
            <p className="font-medium">{t("pages.budget.guide.stepTwo.title")}</p>
            <p className="text-sm text-muted-foreground">{t("pages.budget.guide.stepTwo.body")}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">3</p>
            <p className="font-medium">{t("pages.budget.guide.stepThree.title")}</p>
            <p className="text-sm text-muted-foreground">{t("pages.budget.guide.stepThree.body")}</p>
          </div>
        </CardContent>
      </Card>

      <section className="rounded-xl border border-border/60 app-dashboard-surface grid divide-y lg:divide-y-0 lg:divide-x divide-border/40 lg:grid-cols-3">
        <MetricCard
          title={t("pages.budget.metrics.income")}
          value={formatEurFromCents(actualIncome)}
          subtitle={
            plannedIncome !== null
              ? t("pages.budget.metrics.incomeSubtitle", { amount: formatEurFromCents(plannedIncome) })
              : t("pages.budget.metrics.incomeEmpty")
          }
          icon={<Wallet className="h-3.5 w-3.5" />}
          iconClassName="bg-primary/10 text-primary"
        />
        <MetricCard
          title={t("pages.budget.metrics.outflow")}
          value={formatEurFromCents(totalOutflow)}
          subtitle={t("pages.budget.metrics.outflowSubtitle", {
            receipts: formatEurFromCents(receiptSpend),
            manual: formatEurFromCents(manualOutflow),
            reconciled: reconciledCount
          })}
          icon={<TrendingDown className="h-3.5 w-3.5" />}
          iconClassName="bg-destructive/10 text-destructive"
        />
        <MetricCard
          title={t("pages.budget.metrics.remaining")}
          value={formatEurFromCents(remaining)}
          subtitle={t("pages.budget.metrics.remainingSubtitle", {
            available: formatEurFromCents(available),
            saved: formatEurFromCents(saved)
          })}
          icon={<PiggyBank className="h-3.5 w-3.5" />}
          iconClassName="bg-success/10 text-success"
        />
        <MetricCard
          title={t("pages.budget.metrics.recurring")}
          value={formatEurFromCents(recurringExpected)}
          subtitle={t("pages.budget.metrics.recurringSubtitle", {
            paid: summary?.recurring.paid_count ?? 0,
            unpaid: summary?.recurring.unpaid_count ?? 0
          })}
          icon={<CalendarCheck className="h-3.5 w-3.5" />}
          iconClassName="bg-chart-2/10 text-chart-2"
        />
        <MetricCard
          title={t("pages.budget.metrics.incomeBasis")}
          value={t(
            incomeBasis === "actual"
              ? "pages.budget.metrics.incomeBasisActual"
              : "pages.budget.metrics.incomeBasisPlanned",
            { amount: formatEurFromCents(incomeBasisCents) }
          )}
          subtitle={t("pages.budget.metrics.savingsDelta", {
            amount: formatEurFromCents(savingsDelta)
          })}
          icon={<TrendingUp className="h-3.5 w-3.5" />}
          iconClassName="bg-amber-500/10 text-amber-600"
        />
        <MetricCard
          title={t("pages.budget.metrics.recurringPaid")}
          value={formatEurFromCents(recurringPaid)}
          subtitle={t("pages.budget.metrics.recurringPaidSubtitle", {
            amount: formatEurFromCents(recurringExpected)
          })}
          icon={<ReceiptText className="h-3.5 w-3.5" />}
          iconClassName="bg-muted text-muted-foreground"
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t("pages.budget.monthSettings.title")}</CardTitle>
            <p className="text-sm text-muted-foreground">{t("pages.budget.monthSettings.description")}</p>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 md:grid-cols-2" onSubmit={handleMonthSubmit}>
              <div className="space-y-2">
                <Label htmlFor="planned-income">{t("pages.budget.monthSettings.plannedIncome")}</Label>
                <Input
                  id="planned-income"
                  value={monthForm.plannedIncome}
                  onChange={(event) => setMonthForm((previous) => ({ ...previous, plannedIncome: event.target.value }))}
                  placeholder={t("pages.budget.monthSettings.plannedIncomePlaceholder")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="target-savings">{t("pages.budget.monthSettings.targetSavings")}</Label>
                <Input
                  id="target-savings"
                  value={monthForm.targetSavings}
                  onChange={(event) => setMonthForm((previous) => ({ ...previous, targetSavings: event.target.value }))}
                  placeholder={t("pages.budget.monthSettings.targetSavingsPlaceholder")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="opening-balance">{t("pages.budget.monthSettings.openingBalance")}</Label>
                <Input
                  id="opening-balance"
                  value={monthForm.openingBalance}
                  onChange={(event) => setMonthForm((previous) => ({ ...previous, openingBalance: event.target.value }))}
                  placeholder={t("pages.budget.monthSettings.openingBalancePlaceholder")}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="month-notes">{t("pages.budget.monthSettings.notes")}</Label>
                <Textarea
                  id="month-notes"
                  value={monthForm.notes}
                  onChange={(event) => setMonthForm((previous) => ({ ...previous, notes: event.target.value }))}
                  placeholder={t("pages.budget.monthSettings.notesPlaceholder")}
                />
              </div>
              <div className="md:col-span-2 flex items-center gap-3">
                <Button type="submit" disabled={saveMonthMutation.isPending}>
                  {t("pages.budget.monthSettings.save")}
                </Button>
                <span className="text-sm text-muted-foreground">
                  {t("pages.budget.monthSettings.currency", { currency })}
                </span>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div className="space-y-1">
              <CardTitle className="text-base">{t("pages.budget.recurring.title")}</CardTitle>
              <p className="text-sm text-muted-foreground">{t("pages.budget.recurring.description")}</p>
            </div>
            <TooltipProvider delayDuration={150}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t("pages.budget.recurring.infoLabel")}
                    className="h-8 w-8"
                  >
                    <CircleAlert className="h-4 w-4 text-muted-foreground" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="left" className="max-w-xs">
                  {t("pages.budget.recurring.infoBody")}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </CardHeader>
          <CardContent>
            {(summary?.recurring.items ?? []).length === 0 ? (
              <EmptyState
                title={t("pages.budget.recurring.emptyTitle")}
                description={t("pages.budget.recurring.emptyDescription")}
                action={{ label: t("pages.budget.openBills"), href: "/bills" }}
              />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("pages.budget.recurring.col.due")}</TableHead>
                    <TableHead>{t("pages.budget.recurring.col.bill")}</TableHead>
                    <TableHead>{t("pages.budget.recurring.col.status")}</TableHead>
                    <TableHead className="text-right">{t("pages.budget.recurring.col.expected")}</TableHead>
                    <TableHead className="text-right">{t("pages.budget.recurring.col.actual")}</TableHead>
                    <TableHead className="text-right">{t("common.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(summary?.recurring.items ?? []).map((item) => (
                    <TableRow key={item.occurrence_id}>
                      <TableCell>
                        <Link className="font-medium text-primary hover:underline" to={buildBillLinkTarget(item.bill_id, item.due_date)}>
                          {formatDate(item.due_date)}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link className="font-medium text-primary hover:underline" to={buildBillLinkTarget(item.bill_id, item.due_date)}>
                          {item.bill_name}
                        </Link>
                      </TableCell>
                      <TableCell>{recurringStatusLabel(item.status)}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {item.expected_amount_cents === null
                          ? t("pages.budget.recurring.variableAmount")
                          : formatEurFromCents(item.expected_amount_cents)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {item.actual_amount_cents === null ? "—" : formatEurFromCents(item.actual_amount_cents)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button asChild size="sm" variant="ghost">
                          <Link to={buildBillLinkTarget(item.bill_id, item.due_date)}>
                            {t("pages.budget.recurring.openBill")}
                          </Link>
                        </Button>
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
          <CardTitle className="text-base">{t("pages.budget.cashflow.title")}</CardTitle>
          <p className="text-sm text-muted-foreground">{t("pages.budget.cashflow.description")}</p>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-3 lg:grid-cols-3">
            {CASHFLOW_PRESETS.map((preset) => (
              <Button
                key={preset.key}
                type="button"
                variant="outline"
                className="h-auto justify-start px-4 py-3 text-left"
                onClick={() => applyCashflowPreset({ ...preset.values, descriptionKey: preset.descriptionKey })}
              >
                <span className="block">
                  <span className="block font-medium">{t(preset.labelKey)}</span>
                  <span className="block text-xs text-muted-foreground">{t(preset.hintKey)}</span>
                </span>
              </Button>
            ))}
          </div>

          <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={handleCashflowSubmit}>
            <div className="space-y-2">
              <Label htmlFor="cashflow-date">{t("pages.budget.cashflow.date")}</Label>
              <Input
                id="cashflow-date"
                type="date"
                value={cashflowForm.effectiveDate}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, effectiveDate: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-direction">{t("pages.budget.cashflow.direction")}</Label>
              <Select
                value={cashflowForm.direction}
                onValueChange={(value) => setCashflowForm((previous) => ({ ...previous, direction: value as "inflow" | "outflow" }))}
              >
                <SelectTrigger id="cashflow-direction">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="inflow">{t("pages.budget.cashflow.directionInflow")}</SelectItem>
                  <SelectItem value="outflow">{t("pages.budget.cashflow.directionOutflow")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-category">{t("pages.budget.cashflow.category")}</Label>
              <Input
                id="cashflow-category"
                list="cashflow-category-options"
                value={cashflowForm.category}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, category: event.target.value }))}
                placeholder={t("pages.budget.cashflow.categoryPlaceholder")}
              />
              <datalist id="cashflow-category-options">
                {COMMON_CASHFLOW_CATEGORIES.map((category) => (
                  <option key={category} value={category} />
                ))}
              </datalist>
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-amount">{t("pages.budget.cashflow.amount")}</Label>
              <Input
                id="cashflow-amount"
                value={cashflowForm.amount}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, amount: event.target.value }))}
                placeholder={t("pages.budget.cashflow.amountPlaceholder")}
              />
            </div>
            <div className="space-y-2 md:col-span-2 xl:col-span-2">
              <Label htmlFor="cashflow-description">{t("pages.budget.cashflow.entryDescription")}</Label>
              <Input
                id="cashflow-description"
                value={cashflowForm.description}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, description: event.target.value }))}
                placeholder={t("pages.budget.cashflow.entryDescriptionPlaceholder")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-source-type">{t("pages.budget.cashflow.sourceType")}</Label>
              <Select
                value={cashflowForm.sourceType}
                onValueChange={(value) => setCashflowForm((previous) => ({ ...previous, sourceType: value }))}
              >
                <SelectTrigger id="cashflow-source-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {COMMON_CASHFLOW_SOURCE_TYPES.map((sourceType) => (
                    <SelectItem key={sourceType.value} value={sourceType.value}>
                      {t(sourceType.labelKey)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 md:col-span-2 xl:col-span-2">
              <Label htmlFor="cashflow-notes">{t("pages.budget.cashflow.notes")}</Label>
              <Textarea
                id="cashflow-notes"
                value={cashflowForm.notes}
                onChange={(event) => setCashflowForm((previous) => ({ ...previous, notes: event.target.value }))}
                placeholder={t("pages.budget.cashflow.notesPlaceholder")}
              />
            </div>
            <div className="flex flex-wrap items-center gap-3 md:col-span-2 xl:col-span-4">
              <Button type="submit" disabled={saveCashflowMutation.isPending}>
                {editingCashflowId ? t("pages.budget.cashflow.update") : t("pages.budget.cashflow.add")}
              </Button>
              {editingCashflowId ? (
                <Button type="button" variant="outline" onClick={cancelCashflowEdit}>
                  {t("pages.budget.cashflow.cancelEdit")}
                </Button>
              ) : null}
              <span className="text-sm text-muted-foreground">
                {t("pages.budget.cashflow.summary", {
                  open: openAdjustmentCount,
                  reconciled: reconciledCount
                })}
              </span>
            </div>
          </form>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="cashflow-filter-direction">{t("pages.budget.cashflow.filterDirection")}</Label>
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
                  <SelectItem value="all">{t("pages.budget.cashflow.filterDirectionAll")}</SelectItem>
                  <SelectItem value="inflow">{t("pages.budget.cashflow.directionInflow")}</SelectItem>
                  <SelectItem value="outflow">{t("pages.budget.cashflow.directionOutflow")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-filter-status">{t("pages.budget.cashflow.filterStatus")}</Label>
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
                  <SelectItem value="all">{t("pages.budget.cashflow.filterStatusAll")}</SelectItem>
                  <SelectItem value="open">{t("pages.budget.cashflow.filterStatusOpen")}</SelectItem>
                  <SelectItem value="reconciled">{t("pages.budget.cashflow.filterStatusReconciled")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="cashflow-filter-category">{t("pages.budget.cashflow.filterCategory")}</Label>
              <Input
                id="cashflow-filter-category"
                list="cashflow-category-options"
                value={cashflowFilters.category}
                onChange={(event) =>
                  setCashflowFilters((previous) => ({ ...previous, category: event.target.value }))
                }
                placeholder={t("pages.budget.cashflow.filterCategoryPlaceholder")}
              />
            </div>
          </div>

          <p className="text-sm text-muted-foreground">
            {t("pages.budget.cashflow.helper")}
          </p>

          {cashflowEntries.length === 0 ? (
            <EmptyState
              title={t("pages.budget.cashflow.emptyTitle")}
              description={t("pages.budget.cashflow.emptyDescription")}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("pages.budget.cashflow.col.date")}</TableHead>
                  <TableHead>{t("pages.budget.cashflow.col.direction")}</TableHead>
                  <TableHead>{t("pages.budget.cashflow.col.category")}</TableHead>
                  <TableHead>{t("pages.budget.cashflow.col.description")}</TableHead>
                  <TableHead>{t("pages.budget.cashflow.col.status")}</TableHead>
                  <TableHead className="text-right">{t("pages.budget.cashflow.col.amount")}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {cashflowEntries.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>{formatDate(entry.effective_date)}</TableCell>
                    <TableCell>{t(entry.direction === "inflow" ? "pages.budget.cashflow.directionInflow" : "pages.budget.cashflow.directionOutflow")}</TableCell>
                    <TableCell>{entry.category}</TableCell>
                    <TableCell className="max-w-[280px]">
                      <div className="truncate">{entry.description ?? "—"}</div>
                      {entry.notes ? (
                        <div className="truncate text-xs text-muted-foreground">{entry.notes}</div>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1 text-sm">
                        <div>{entry.is_reconciled ? t("pages.budget.cashflow.statusReconciled") : t("pages.budget.cashflow.statusOpen")}</div>
                        <div className="text-xs text-muted-foreground">{entry.source_type}</div>
                        {entry.linked_transaction ? (
                          <div className="text-xs text-muted-foreground">
                            {entry.linked_transaction.merchant_name ?? t("pages.budget.cashflow.receiptLabel")} · {formatDate(entry.linked_transaction.purchased_at)}
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
                          {t("common.edit")}
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
                            {entry.is_reconciled ? t("pages.budget.cashflow.unlinkReceipt") : t("pages.budget.cashflow.linkReceipt")}
                          </Button>
                        ) : null}
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => deleteCashflowMutation.mutate(entry.id)}
                          disabled={deleteCashflowMutation.isPending}
                        >
                          {t("common.delete")}
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
                  <h3 className="text-sm font-medium">
                    {t("pages.budget.cashflow.reconcileTitle", {
                      entry: reconcileEntry.description ?? t("pages.budget.cashflow.manualEntry")
                    })}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {t("pages.budget.cashflow.reconcileDescription")}
                  </p>
                </div>
                <Button type="button" variant="outline" onClick={() => setReconcileEntryId(null)}>
                  {t("common.close")}
                </Button>
              </div>
              <div className="space-y-2">
                <Label htmlFor="receipt-search">{t("pages.budget.cashflow.receiptSearch")}</Label>
                <Input
                  id="receipt-search"
                  value={receiptSearch}
                  onChange={(event) => setReceiptSearch(event.target.value)}
                  placeholder={t("pages.budget.cashflow.receiptSearchPlaceholder")}
                />
              </div>
              {receiptCandidatesQuery.isPending ? (
                <p className="text-sm text-muted-foreground">{t("pages.budget.cashflow.searchingReceipts")}</p>
              ) : null}
              {receiptCandidates.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {t("pages.budget.cashflow.noReceiptMatches")}
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
                        {t("pages.budget.cashflow.useReceipt")}
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
          <CardTitle className="text-base">{t("pages.budget.rules.title")}</CardTitle>
          <p className="text-sm text-muted-foreground">{t("pages.budget.rules.description")}</p>
        </CardHeader>
        <CardContent className="space-y-6">
          <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={(event) => {
            event.preventDefault();
            if (!budgetRuleForm.scopeValue.trim()) {
              setFeedback({ kind: "error", message: t("pages.budget.rules.validation.scopeRequired") });
              return;
            }
            void budgetRuleMutation.mutateAsync(budgetRuleForm);
          }}>
            <div className="space-y-2">
              <Label htmlFor="budget-rule-scope-type">{t("pages.budget.rules.scopeType")}</Label>
              <Select
                value={budgetRuleForm.scopeType}
                onValueChange={(value) => setBudgetRuleForm((previous) => ({ ...previous, scopeType: value as "category" | "source_kind" }))}
              >
                <SelectTrigger id="budget-rule-scope-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="category">{t("pages.budget.rules.scopeTypeCategory")}</SelectItem>
                  <SelectItem value="source_kind">{t("pages.budget.rules.scopeTypeSourceKind")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget-rule-scope-value">{t("pages.budget.rules.scopeValue")}</Label>
              <Input
                id="budget-rule-scope-value"
                value={budgetRuleForm.scopeValue}
                onChange={(event) => setBudgetRuleForm((previous) => ({ ...previous, scopeValue: event.target.value }))}
                placeholder={t("pages.budget.rules.scopeValuePlaceholder")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget-rule-period">{t("pages.budget.rules.period")}</Label>
              <Select
                value={budgetRuleForm.period}
                onValueChange={(value) => setBudgetRuleForm((previous) => ({ ...previous, period: value as "monthly" | "annual" }))}
              >
                <SelectTrigger id="budget-rule-period">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">{t("pages.budget.rules.periodMonthly")}</SelectItem>
                  <SelectItem value="annual">{t("pages.budget.rules.periodAnnual")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget-rule-amount">{t("pages.budget.rules.amount")}</Label>
              <Input
                id="budget-rule-amount"
                value={budgetRuleForm.amount}
                onChange={(event) => setBudgetRuleForm((previous) => ({ ...previous, amount: event.target.value }))}
                placeholder={t("pages.budget.rules.amountPlaceholder")}
              />
            </div>
            <div className="md:col-span-2 xl:col-span-4">
              <Button type="submit" disabled={budgetRuleMutation.isPending}>
                {t("pages.budget.rules.add")}
              </Button>
            </div>
          </form>

          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-3 text-sm font-medium">{t("pages.budget.rules.rulesList")}</h3>
              {budgetRules.length === 0 ? (
                <EmptyState
                  title={t("pages.budget.rules.emptyTitle")}
                  description={t("pages.budget.rules.emptyDescription")}
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("pages.budget.rules.col.scope")}</TableHead>
                      <TableHead>{t("pages.budget.rules.col.value")}</TableHead>
                      <TableHead>{t("pages.budget.rules.col.period")}</TableHead>
                      <TableHead className="text-right">{t("pages.budget.rules.col.amount")}</TableHead>
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
              <h3 className="mb-3 text-sm font-medium">{t("pages.budget.rules.utilizationTitle")}</h3>
              {utilizationRows.length === 0 ? (
                <EmptyState
                  title={t("pages.budget.rules.utilizationEmptyTitle")}
                  description={t("pages.budget.rules.utilizationEmptyDescription")}
                />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("pages.budget.rules.utilization.col.scope")}</TableHead>
                      <TableHead className="text-right">{t("pages.budget.rules.utilization.col.budget")}</TableHead>
                      <TableHead className="text-right">{t("pages.budget.rules.utilization.col.spent")}</TableHead>
                      <TableHead className="text-right">{t("pages.budget.rules.utilization.col.remaining")}</TableHead>
                      <TableHead className="text-right">{t("pages.budget.rules.utilization.col.utilization")}</TableHead>
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
            {t("pages.budget.rules.footer")}
          </p>
        </CardContent>
      </Card>
    </section>
  );
}
