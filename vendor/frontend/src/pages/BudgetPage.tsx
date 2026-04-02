import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createBudgetRule, fetchBudgetRules, fetchBudgetUtilization } from "@/api/analytics";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/shared/PageHeader";
import { useI18n } from "@/i18n";
import { formatEurFromCents, formatPercent } from "@/utils/format";
import { parseEuroInputToCents } from "@/utils/money-input";

export function BudgetPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [scopeType, setScopeType] = useState<"category" | "source_kind">("category");
  const [scopeValue, setScopeValue] = useState("");
  const [period, setPeriod] = useState<"monthly" | "annual">("monthly");
  const [amountInput, setAmountInput] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const rulesQuery = useQuery({
    queryKey: ["budget-rules"],
    queryFn: fetchBudgetRules
  });
  const utilizationQuery = useQuery({
    queryKey: ["budget-utilization"],
    queryFn: () => fetchBudgetUtilization()
  });
  const createMutation = useMutation({
    mutationFn: createBudgetRule,
    onSuccess: () => {
      setScopeValue("");
      setAmountInput("");
      setSubmitError(null);
      void queryClient.invalidateQueries({ queryKey: ["budget-rules"] });
      void queryClient.invalidateQueries({ queryKey: ["budget-utilization"] });
    }
  });

  function submitRule(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!scopeValue.trim()) {
      return;
    }
    const amountCents = parseEuroInputToCents(amountInput);
    if (amountCents === null || amountCents <= 0) {
      setSubmitError(t("pages.budget.validation.amountRequired"));
      return;
    }
    setSubmitError(null);
    void createMutation.mutateAsync({
      scope_type: scopeType,
      scope_value: scopeValue.trim(),
      period,
      amount_cents: amountCents,
      currency: "EUR",
      active: true
    });
  }

  const rules = rulesQuery.data?.items ?? [];
  const utilizationRows = utilizationQuery.data?.rows ?? [];

  return (
    <section className="space-y-6">
      <PageHeader title={t("nav.item.budget")} />
      {submitError ? <p className="text-sm text-destructive">{submitError}</p> : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Budget Rules</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={submitRule}>
            <div className="space-y-2">
              <Label htmlFor="budget-scope-type">Scope type</Label>
              <Select
                value={scopeType}
                onValueChange={(value) => setScopeType(value as "category" | "source_kind")}
              >
                <SelectTrigger id="budget-scope-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="category">Category</SelectItem>
                  <SelectItem value="source_kind">Source kind</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget-scope-value">Scope value</Label>
              <Input
                id="budget-scope-value"
                value={scopeValue}
                onChange={(event) => {
                  setScopeValue(event.target.value);
                  setSubmitError(null);
                }}
                placeholder={scopeType === "category" ? "Dairy" : "lidl_de"}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget-period">Period</Label>
              <Select
                value={period}
                onValueChange={(value) => setPeriod(value as "monthly" | "annual")}
              >
                <SelectTrigger id="budget-period">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">Monthly</SelectItem>
                  <SelectItem value="annual">Annual</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="budget-amount">{t("pages.budget.form.amountEur")}</Label>
              <Input
                id="budget-amount"
                type="text"
                inputMode="decimal"
                value={amountInput}
                onChange={(event) => {
                  setAmountInput(event.target.value);
                  setSubmitError(null);
                }}
                placeholder="12,99"
              />
            </div>
            <div className="md:col-span-2 xl:col-span-4">
              <Button type="submit" disabled={createMutation.isPending}>
                Add budget rule
              </Button>
            </div>
          </form>

          <div className="grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-3 text-sm font-medium">Configured Rules</h3>
              {rules.length === 0 ? (
                <EmptyState
                  title="No budget rules configured"
                  description="Create your first budget rule above to start tracking spending limits."
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
                    {rules.map((rule) => (
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
              <h3 className="mb-3 text-sm font-medium">Budget Utilization</h3>
              {utilizationRows.length === 0 ? (
                <EmptyState
                  title="No utilization data"
                  description="Budget utilization will appear here once you have rules and matching transactions."
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
                      <TableHead className="text-right">Projected</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {utilizationRows.map((row) => (
                      <TableRow key={row.rule_id}>
                        <TableCell>
                          {row.scope_type}:{row.scope_value}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{formatEurFromCents(row.budget_cents)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatEurFromCents(row.spent_cents)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatEurFromCents(row.remaining_cents)}</TableCell>
                        <TableCell className="text-right tabular-nums">{formatPercent(row.utilization)}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatEurFromCents(row.projected_spent_cents)} ({formatPercent(row.projected_utilization)})
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
