import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createBudgetRule, fetchBudgetRules, fetchBudgetUtilization } from "@/api/analytics";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatEurFromCents, formatPercent } from "@/utils/format";

export function BudgetPage() {
  const queryClient = useQueryClient();
  const [scopeType, setScopeType] = useState<"category" | "source_kind">("category");
  const [scopeValue, setScopeValue] = useState("");
  const [period, setPeriod] = useState<"monthly" | "annual">("monthly");
  const [amountCents, setAmountCents] = useState("");

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
      setAmountCents("");
      void queryClient.invalidateQueries({ queryKey: ["budget-rules"] });
      void queryClient.invalidateQueries({ queryKey: ["budget-utilization"] });
    }
  });

  function submitRule(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const amount = Number(amountCents);
    if (!scopeValue.trim() || !Number.isFinite(amount) || amount <= 0) {
      return;
    }
    void createMutation.mutateAsync({
      scope_type: scopeType,
      scope_value: scopeValue.trim(),
      period,
      amount_cents: Math.floor(amount),
      currency: "EUR",
      active: true
    });
  }

  const rules = rulesQuery.data?.items ?? [];
  const utilizationRows = utilizationQuery.data?.rows ?? [];

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Budget Rules</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-4" onSubmit={submitRule}>
            <div className="space-y-1">
              <Label htmlFor="budget-scope-type">Scope type</Label>
              <select
                id="budget-scope-type"
                className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                value={scopeType}
                onChange={(event) => setScopeType(event.target.value as "category" | "source_kind")}
              >
                <option value="category">Category</option>
                <option value="source_kind">Source kind</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="budget-scope-value">Scope value</Label>
              <Input
                id="budget-scope-value"
                value={scopeValue}
                onChange={(event) => setScopeValue(event.target.value)}
                placeholder={scopeType === "category" ? "Dairy" : "lidl_de"}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="budget-period">Period</Label>
              <select
                id="budget-period"
                className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                value={period}
                onChange={(event) => setPeriod(event.target.value as "monthly" | "annual")}
              >
                <option value="monthly">Monthly</option>
                <option value="annual">Annual</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="budget-amount">Amount (cents)</Label>
              <Input
                id="budget-amount"
                type="number"
                value={amountCents}
                onChange={(event) => setAmountCents(event.target.value)}
                placeholder="10000"
              />
            </div>
            <Button type="submit" className="md:col-span-4 w-fit" disabled={createMutation.isPending}>
              Add budget rule
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Configured Rules</CardTitle>
        </CardHeader>
        <CardContent>
          {rules.length === 0 ? (
            <p className="text-sm text-muted-foreground">No budget rules configured.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scope</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Amount</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rules.map((rule) => (
                  <TableRow key={rule.rule_id}>
                    <TableCell>{rule.scope_type}</TableCell>
                    <TableCell>{rule.scope_value}</TableCell>
                    <TableCell>{rule.period}</TableCell>
                    <TableCell>{formatEurFromCents(rule.amount_cents)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Budget Utilization</CardTitle>
        </CardHeader>
        <CardContent>
          {utilizationRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No utilization rows available.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scope</TableHead>
                  <TableHead>Budget</TableHead>
                  <TableHead>Spent</TableHead>
                  <TableHead>Remaining</TableHead>
                  <TableHead>Utilization</TableHead>
                  <TableHead>Projected</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {utilizationRows.map((row) => (
                  <TableRow key={row.rule_id}>
                    <TableCell>
                      {row.scope_type}:{row.scope_value}
                    </TableCell>
                    <TableCell>{formatEurFromCents(row.budget_cents)}</TableCell>
                    <TableCell>{formatEurFromCents(row.spent_cents)}</TableCell>
                    <TableCell>{formatEurFromCents(row.remaining_cents)}</TableCell>
                    <TableCell>{formatPercent(row.utilization)}</TableCell>
                    <TableCell>
                      {formatEurFromCents(row.projected_spent_cents)} ({formatPercent(row.projected_utilization)})
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
