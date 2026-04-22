import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Target, Trash2 } from "lucide-react";

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

export function GoalsPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const { locale, tText } = useI18n();
  const [formState, setFormState] = useState<GoalFormState>(DEFAULT_FORM);
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
        title={tText("Goals")}
        description={tText("Set savings and spend targets that stay visible from the dashboard instead of living in notes or spreadsheets.")}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="app-dashboard-surface border-border/60">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">{tText("Active goals")}</p>
            <p className="mt-2 text-3xl font-semibold">{topSummary.total}</p>
          </CardContent>
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">{tText("Completed")}</p>
            <p className="mt-2 text-3xl font-semibold">{topSummary.completed}</p>
          </CardContent>
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <CardContent className="p-5">
            <p className="text-sm text-muted-foreground">{tText("At risk")}</p>
            <p className="mt-2 text-3xl font-semibold">{topSummary.atRisk}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
        <Card className="app-dashboard-surface border-border/60">
          <CardHeader>
            <CardTitle>{tText("Create goal")}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="goal-name">{tText("Name")}</Label>
              <Input id="goal-name" value={formState.name} onChange={(event) => setFormState((previous) => ({ ...previous, name: event.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-type">{tText("Goal type")}</Label>
              <select
                id="goal-type"
                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={formState.goalType}
                onChange={(event) => setFormState((previous) => ({ ...previous, goalType: event.target.value }))}
              >
                <option value="monthly_spend_cap">{goalTypeLabel("monthly_spend_cap", locale)}</option>
                <option value="category_spend_cap">{goalTypeLabel("category_spend_cap", locale)}</option>
                <option value="savings_target">{goalTypeLabel("savings_target", locale)}</option>
                <option value="recurring_bill_reduction">{goalTypeLabel("recurring_bill_reduction", locale)}</option>
              </select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-target">{tText("Target amount (EUR)")}</Label>
              <Input id="goal-target" value={formState.targetAmount} onChange={(event) => setFormState((previous) => ({ ...previous, targetAmount: event.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-period">{tText("Period")}</Label>
              <select
                id="goal-period"
                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={formState.period}
                onChange={(event) => setFormState((previous) => ({ ...previous, period: event.target.value }))}
              >
                <option value="current_window">{tText("Current dashboard window")}</option>
                <option value="current_month">{tText("Current month")}</option>
              </select>
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="goal-category">{tText("Category")}</Label>
                <Input id="goal-category" value={formState.category} onChange={(event) => setFormState((previous) => ({ ...previous, category: event.target.value }))} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="goal-merchant">{tText("Merchant")}</Label>
                <Input id="goal-merchant" value={formState.merchantName} onChange={(event) => setFormState((previous) => ({ ...previous, merchantName: event.target.value }))} />
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-recurring-bill">{tText("Recurring bill")}</Label>
              <select
                id="goal-recurring-bill"
                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={formState.recurringBillId}
                onChange={(event) => setFormState((previous) => ({ ...previous, recurringBillId: event.target.value }))}
              >
                <option value="">{tText("None")}</option>
                {(recurringBillsQuery.data?.items ?? []).map((bill) => (
                  <option key={bill.id} value={bill.id}>
                    {bill.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-target-date">{tText("Target date")}</Label>
              <Input id="goal-target-date" type="date" value={formState.targetDate} onChange={(event) => setFormState((previous) => ({ ...previous, targetDate: event.target.value }))} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="goal-notes">{tText("Notes")}</Label>
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
                  category: formState.category || null,
                  merchant_name: formState.merchantName || null,
                  recurring_bill_id: formState.recurringBillId || null,
                  target_date: formState.targetDate || null,
                  notes: formState.notes || null
                })
              }
              disabled={!formState.name.trim() || !Number.isFinite(Number(formState.targetAmount))}
            >
              <Target className="mr-2 h-4 w-4" />
              {tText("Save goal")}
            </Button>
          </CardContent>
        </Card>

        <Card className="app-dashboard-surface border-border/60">
          <CardHeader>
            <CardTitle>{tText("Goal board")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {(goalsQuery.data?.items ?? []).map((goal) => {
              const progress = goal.progress;
              const percent = progress ? Math.min(100, Math.round(progress.progress_ratio * 100)) : 0;
              return (
                <div key={goal.id} className="rounded-[24px] border border-border/60 bg-white/70 p-4">
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
                        {goal.active ? tText("Pause") : tText("Resume")}
                      </Button>
                      <Button type="button" variant="ghost" size="icon" onClick={() => deleteGoalMutation.mutate(goal.id)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center justify-between gap-3 text-sm">
                    <span className="text-muted-foreground">
                      {progress ? formatEurFromCents(progress.current_amount_cents) : formatEurFromCents(0)} / {formatEurFromCents(goal.target_amount_cents)}
                    </span>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium">{tText((progress?.status || "unknown").replace(/_/g, " "))}</span>
                  </div>
                  <div className="mt-3 h-2.5 rounded-full bg-slate-100">
                    <div className="h-2.5 rounded-full bg-sky-500" style={{ width: `${percent}%` }} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
                    {goal.target_date ? <span>{locale === "de" ? `Ziel ${formatDate(goal.target_date)}` : `Target ${formatDate(goal.target_date)}`}</span> : null}
                    {goal.category ? <span>{locale === "de" ? `Kategorie ${goal.category}` : `Category ${goal.category}`}</span> : null}
                    {goal.merchant_name ? <span>{locale === "de" ? `Händler ${goal.merchant_name}` : `Merchant ${goal.merchant_name}`}</span> : null}
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
