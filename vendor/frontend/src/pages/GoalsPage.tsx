import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Target, Trash2 } from "lucide-react";

import { createGoal, deleteGoal, fetchGoals, fetchGoalsSummary, updateGoal } from "@/api/goals";
import { fetchRecurringBills } from "@/api/recurringBills";
import { useDateRangeContext } from "@/app/date-range-context";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/i18n";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { formatDate, formatEurFromCents } from "@/utils/format";

type GoalFormState = {
  name: string;
  goalType: string;
  targetAmount: string;
  period: string;
  category: string;
  merchantName: string;
  recurringBillId: string;
  targetDate: string;
  notes: string;
};

const DEFAULT_FORM: GoalFormState = {
  name: "",
  goalType: "monthly_spend_cap",
  targetAmount: "",
  period: "current_window",
  category: "",
  merchantName: "",
  recurringBillId: "",
  targetDate: "",
  notes: ""
};

function goalTypeLabel(goalType: string, locale: "en" | "de"): string {
  if (goalType === "monthly_spend_cap") return locale === "de" ? "Monatliches Ausgabenlimit" : "Monthly spend cap";
  if (goalType === "category_spend_cap") return locale === "de" ? "Kategorienlimit" : "Category spend cap";
  if (goalType === "savings_target") return locale === "de" ? "Sparziel" : "Savings target";
  if (goalType === "recurring_bill_reduction") return locale === "de" ? "Wiederkehrende Kosten senken" : "Recurring bill reduction";
  return goalType;
}

function goalProgressStatusLabel(status: string, locale: "en" | "de"): string {
  if (status === "completed") return locale === "de" ? "Abgeschlossen" : "Completed";
  if (status === "at_risk") return locale === "de" ? "Gefährdet" : "At risk";
  if (status === "on_track") return locale === "de" ? "Im Plan" : "On track";
  if (status === "paused") return locale === "de" ? "Pausiert" : "Paused";
  if (status === "over_target") return locale === "de" ? "Über Ziel" : "Over target";
  return status.replace(/_/g, " ");
}

function goalUnitLabel(unitLabel: string | undefined, locale: "en" | "de"): string {
  if (unitLabel === "saved") return locale === "de" ? "gespart" : "saved";
  return locale === "de" ? "verbraucht" : "spent";
}

function goalStatusChipClass(status: string | undefined): string {
  if (status === "completed") {
    return "border border-emerald-500/25 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300";
  }
  if (status === "at_risk" || status === "over_target") {
    return "border border-amber-500/25 bg-amber-500/12 text-amber-700 dark:text-amber-300";
  }
  if (status === "paused") {
    return "border border-border/70 bg-muted/60 text-muted-foreground";
  }
  return "border border-sky-500/25 bg-sky-500/12 text-sky-700 dark:text-sky-300";
}

export function GoalsPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const { locale } = useI18n();
  const copy = locale === "de"
    ? {
        pageTitle: "Ziele",
        description: "Lege Spar- und Ausgabenziele fest, die auf dem Dashboard sichtbar bleiben, statt nur in Notizen oder Tabellen zu leben.",
        activeGoals: "Aktive Ziele",
        completed: "Abgeschlossen",
        atRisk: "Gefährdet",
        createGoal: "Ziel erstellen",
        goalBoard: "Zielübersicht",
        pause: "Pausieren",
        resume: "Fortsetzen",
        target: "Ziel",
        category: "Kategorie",
        merchant: "Händler",
        recurringBill: "Wiederkehrende Rechnung",
        none: "Keine",
        saveGoal: "Ziel speichern",
        name: "Name",
        goalType: "Zieltyp",
        targetAmount: "Zielbetrag (EUR)",
        period: "Zeitraum",
        currentWindow: "Aktuelles Dashboard-Fenster",
        currentMonth: "Aktueller Monat",
        categoryLabel: "Kategorie",
        merchantLabel: "Händler",
	        targetDate: "Zieldatum",
	        notes: "Notizen",
	        savingsHelp: "Sparziele messen den Netto-Cashflow im gewählten Zeitraum: Einnahmen minus Ausgaben, niemals unter 0 EUR. Kategorie, Händler und Rechnung beeinflussen dieses Ziel nicht.",
	        spendCapHelp: "Dieses Ziel überwacht die gesamten Ausgaben im gewählten Zeitraum.",
	        categoryCapHelp: "Dieses Ziel begrenzt Ausgaben für eine Kategorie. Ein Händler kann zusätzlich eingegrenzt werden.",
	        recurringHelp: "Dieses Ziel überwacht die tatsächlichen Kosten der ausgewählten wiederkehrenden Rechnung.",
	        progressWindow: "Fortschritt im Fenster",
	        scope: "Umfang"
	      }
	    : {
        pageTitle: "Goals",
        description: "Set savings and spend targets that stay visible from the dashboard instead of living in notes or spreadsheets.",
        activeGoals: "Active goals",
        completed: "Completed",
        atRisk: "At risk",
        createGoal: "Create goal",
        goalBoard: "Goal board",
        pause: "Pause",
        resume: "Resume",
        target: "Target",
        category: "Category",
        merchant: "Merchant",
        recurringBill: "Recurring bill",
        none: "None",
        saveGoal: "Save goal",
        name: "Name",
        goalType: "Goal type",
        targetAmount: "Target amount (EUR)",
        period: "Period",
        currentWindow: "Current dashboard window",
        currentMonth: "Current month",
        categoryLabel: "Category",
        merchantLabel: "Merchant",
	        targetDate: "Target date",
	        notes: "Notes",
	        savingsHelp: "Savings targets measure net cash flow in the selected period: inflow minus outflow, never below 0 EUR. Category, merchant, and bill fields do not affect this goal.",
	        spendCapHelp: "This goal tracks total spending in the selected period.",
	        categoryCapHelp: "This goal caps spending for one category. A merchant can narrow the scope further.",
	        recurringHelp: "This goal tracks actual cost for the selected recurring bill.",
	        progressWindow: "Progress window",
	        scope: "Scope"
	      };
  const [formState, setFormState] = useState<GoalFormState>(DEFAULT_FORM);
  const isCategorySpendCap = formState.goalType === "category_spend_cap";
  const isRecurringReduction = formState.goalType === "recurring_bill_reduction";
  const updateGoalType = (goalType: string) => {
    setFormState((previous) => ({ ...previous, goalType }));
  };
  const goalTypeOptions = [
    "monthly_spend_cap",
    "category_spend_cap",
    "savings_target",
    "recurring_bill_reduction"
  ];
  const goalTypeHelp =
    formState.goalType === "savings_target"
      ? copy.savingsHelp
      : formState.goalType === "category_spend_cap"
        ? copy.categoryCapHelp
        : formState.goalType === "recurring_bill_reduction"
          ? copy.recurringHelp
          : copy.spendCapHelp;
  const queryClient = useQueryClient();
  const goalsQuery = useQuery({
    queryKey: ["goals-page", fromDate, toDate],
    queryFn: () => fetchGoals(fromDate, toDate, true)
  });
  const summaryQuery = useQuery({
    queryKey: ["goals-page", "summary", fromDate, toDate],
    queryFn: () => fetchGoalsSummary(fromDate, toDate)
  });
  const recurringBillsQuery = useQuery({
    queryKey: ["goals-page", "recurring-bills"],
    queryFn: () => fetchRecurringBills()
  });

  const invalidateGoals = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["goals-page"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] })
    ]);

  const createGoalMutation = useMutation({
    mutationFn: createGoal,
    onSuccess: async () => {
      setFormState(DEFAULT_FORM);
      await invalidateGoals();
    }
  });
  const updateGoalMutation = useMutation({
    mutationFn: ({ goalId, active }: { goalId: string; active: boolean }) => updateGoal(goalId, { active }),
    onSuccess: invalidateGoals
  });
  const deleteGoalMutation = useMutation({
    mutationFn: deleteGoal,
    onSuccess: invalidateGoals
  });

  const topSummary = useMemo(
    () => ({
      total: summaryQuery.data?.count ?? 0,
      completed: summaryQuery.data?.completed_count ?? 0,
      atRisk: summaryQuery.data?.at_risk_count ?? 0
    }),
    [summaryQuery.data]
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={copy.pageTitle}
        description={copy.description}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="app-dashboard-surface border-border/60">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">{copy.activeGoals}</p>
            <p className="mt-2 text-3xl font-semibold">{topSummary.total}</p>
          </CardContent>
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">{copy.completed}</p>
            <p className="mt-2 text-3xl font-semibold">{topSummary.completed}</p>
          </CardContent>
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">{copy.atRisk}</p>
            <p className="mt-2 text-3xl font-semibold">{topSummary.atRisk}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
        <Card className="app-dashboard-surface border-border/60">
          <CardHeader>
            <CardTitle>{copy.createGoal}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="goal-name">{copy.name}</Label>
              <Input id="goal-name" value={formState.name} onChange={(event) => setFormState((previous) => ({ ...previous, name: event.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label>{copy.goalType}</Label>
              <div id="goal-type" role="group" aria-label={copy.goalType} className="grid gap-2 sm:grid-cols-2">
                {goalTypeOptions.map((goalType) => (
                  <Button
                    key={goalType}
                    type="button"
                    variant={formState.goalType === goalType ? "default" : "outline"}
                    className="h-auto min-h-10 justify-start whitespace-normal text-left"
                    aria-pressed={formState.goalType === goalType}
                    onClick={() => updateGoalType(goalType)}
                  >
                    {goalTypeLabel(goalType, locale)}
                  </Button>
                ))}
              </div>
	            </div>
	            <div className="app-soft-surface flex gap-3 rounded-lg border border-border/60 p-3 text-sm text-muted-foreground">
	              <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-500" />
	              <p key={formState.goalType} className="leading-6">{goalTypeHelp}</p>
	            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-target">{copy.targetAmount}</Label>
              <Input id="goal-target" value={formState.targetAmount} onChange={(event) => setFormState((previous) => ({ ...previous, targetAmount: event.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-period">{copy.period}</Label>
              <select
                id="goal-period"
                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={formState.period}
                onChange={(event) => setFormState((previous) => ({ ...previous, period: event.target.value }))}
              >
                <option value="current_window">{copy.currentWindow}</option>
                <option value="current_month">{copy.currentMonth}</option>
              </select>
            </div>
	            {isCategorySpendCap ? (
	              <div className="grid gap-2 md:grid-cols-2">
	                <div className="grid gap-2">
	                  <Label htmlFor="goal-category">{copy.categoryLabel}</Label>
	                  <Input id="goal-category" value={formState.category} onChange={(event) => setFormState((previous) => ({ ...previous, category: event.target.value }))} />
	                </div>
	                <div className="grid gap-2">
	                  <Label htmlFor="goal-merchant">{copy.merchantLabel}</Label>
	                  <Input id="goal-merchant" value={formState.merchantName} onChange={(event) => setFormState((previous) => ({ ...previous, merchantName: event.target.value }))} />
	                </div>
	              </div>
	            ) : null}
	            {isRecurringReduction ? (
	              <div className="grid gap-2">
	                <Label htmlFor="goal-recurring-bill">{copy.recurringBill}</Label>
	                <select
	                  id="goal-recurring-bill"
	                  className="h-10 rounded-md border border-input bg-background px-3 text-sm"
	                  value={formState.recurringBillId}
	                  onChange={(event) => setFormState((previous) => ({ ...previous, recurringBillId: event.target.value }))}
	                >
	                  <option value="">{copy.none}</option>
	                  {(recurringBillsQuery.data?.items ?? []).map((bill) => (
	                    <option key={bill.id} value={bill.id}>
	                      {bill.name}
	                    </option>
	                  ))}
	                </select>
	              </div>
	            ) : null}
            <div className="grid gap-2">
              <Label htmlFor="goal-target-date">{copy.targetDate}</Label>
              <Input id="goal-target-date" type="date" value={formState.targetDate} onChange={(event) => setFormState((previous) => ({ ...previous, targetDate: event.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-notes">{copy.notes}</Label>
              <Textarea id="goal-notes" value={formState.notes} onChange={(event) => setFormState((previous) => ({ ...previous, notes: event.target.value }))} />
            </div>
            <Button
              type="button"
              onClick={() =>
                createGoalMutation.mutate({
                  name: formState.name,
                  goal_type: formState.goalType,
                  target_amount_cents: Math.round(Number(formState.targetAmount || "0") * 100),
                  period: formState.period,
	                  category: isCategorySpendCap ? formState.category || null : null,
	                  merchant_name: isCategorySpendCap ? formState.merchantName || null : null,
	                  recurring_bill_id: isRecurringReduction ? formState.recurringBillId || null : null,
                  target_date: formState.targetDate || null,
                  notes: formState.notes || null
                })
              }
              disabled={!formState.name.trim() || !Number.isFinite(Number(formState.targetAmount))}
            >
              <Target className="mr-2 h-4 w-4" />
              {copy.saveGoal}
            </Button>
          </CardContent>
        </Card>

        <Card className="app-dashboard-surface border-border/60">
          <CardHeader>
            <CardTitle>{copy.goalBoard}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {(goalsQuery.data?.items ?? []).map((goal) => {
              const progress = goal.progress;
              const percent = progress ? Math.min(100, Math.round(progress.progress_ratio * 100)) : 0;
              return (
	                <div key={goal.id} className="app-soft-surface rounded-lg border border-border/60 p-4 text-foreground">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-semibold">{goal.name}</p>
                      <p className="text-sm text-muted-foreground">{goalTypeLabel(goal.goal_type, locale)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => updateGoalMutation.mutate({ goalId: goal.id, active: !goal.active })}
                      >
                        {goal.active ? copy.pause : copy.resume}
                      </Button>
                      <Button type="button" variant="ghost" size="icon" onClick={() => deleteGoalMutation.mutate(goal.id)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
	                  <div className="mt-4 flex items-center justify-between gap-3 text-sm">
	                    <span className="text-muted-foreground">
	                      {progress ? formatEurFromCents(progress.current_amount_cents) : formatEurFromCents(0)} / {formatEurFromCents(goal.target_amount_cents)}
	                      <span className="ml-1">({goalUnitLabel(progress?.unit_label, locale)})</span>
	                    </span>
	                    <span className={`rounded-full px-2.5 py-1 font-medium ${goalStatusChipClass(progress?.status)}`}>{goalProgressStatusLabel(progress?.status || "unknown", locale)}</span>
	                  </div>
	                  <div className="mt-3 h-2.5 rounded-full bg-muted">
	                    <div className="h-2.5 rounded-full bg-sky-500" style={{ width: `${percent}%` }} />
	                  </div>
	                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
	                    {progress ? <span>{`${copy.progressWindow} ${formatDate(progress.window_from)} - ${formatDate(progress.window_to)}`}</span> : null}
	                    {goal.target_date ? <span>{locale === "de" ? `${copy.target} ${formatDate(goal.target_date)}` : `${copy.target} ${formatDate(goal.target_date)}`}</span> : null}
                    {goal.category ? <span>{locale === "de" ? `${copy.categoryLabel} ${goal.category}` : `${copy.categoryLabel} ${goal.category}`}</span> : null}
                    {goal.merchant_name ? <span>{locale === "de" ? `${copy.merchantLabel} ${goal.merchant_name}` : `${copy.merchantLabel} ${goal.merchant_name}`}</span> : null}
                    {goal.notes ? <span>{goal.notes}</span> : null}
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
