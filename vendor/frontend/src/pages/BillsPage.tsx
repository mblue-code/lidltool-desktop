import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CalendarClock, CircleAlert, Wallet } from "lucide-react";

import {
  createRecurringBill,
  deleteRecurringBill,
  fetchBillOccurrences,
  fetchRecurringBills,
  fetchRecurringCalendar,
  fetchRecurringOverview,
  generateBillOccurrences,
  reconcileOccurrence,
  runBillMatching,
  skipOccurrence,
  updateRecurringBill,
  updateOccurrenceStatus,
  type RecurringBill
} from "@/api/recurringBills";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { formatEurFromCents } from "@/utils/format";

type BillFormState = {
  name: string;
  merchantCanonical: string;
  merchantAliasPattern: string;
  category: string;
  frequency: "weekly" | "biweekly" | "monthly" | "quarterly" | "yearly";
  intervalValue: string;
  amountMode: "fixed" | "variable";
  amountCents: string;
  amountTolerancePct: string;
  anchorDate: string;
  active: boolean;
  notes: string;
};

const EMPTY_FORM: BillFormState = {
  name: "",
  merchantCanonical: "",
  merchantAliasPattern: "",
  category: "subscriptions",
  frequency: "monthly",
  intervalValue: "1",
  amountMode: "fixed",
  amountCents: "",
  amountTolerancePct: "0.10",
  anchorDate: new Date().toISOString().slice(0, 10),
  active: true,
  notes: ""
};

function statusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "paid") {
    return "default";
  }
  if (status === "overdue" || status === "unmatched") {
    return "destructive";
  }
  if (status === "due") {
    return "secondary";
  }
  return "outline";
}

function amountLabel(amountCents: number | null): string {
  return amountCents === null ? "Variable" : formatEurFromCents(amountCents);
}

function frequencyLabel(bill: Pick<RecurringBill, "frequency" | "interval_value">): string {
  if (bill.interval_value <= 1) {
    return bill.frequency;
  }
  return `${bill.frequency} x${bill.interval_value}`;
}

function toFormState(bill: RecurringBill): BillFormState {
  return {
    name: bill.name,
    merchantCanonical: bill.merchant_canonical ?? "",
    merchantAliasPattern: bill.merchant_alias_pattern ?? "",
    category: bill.category,
    frequency: bill.frequency,
    intervalValue: String(bill.interval_value),
    amountMode: bill.amount_cents === null ? "variable" : "fixed",
    amountCents: bill.amount_cents === null ? "" : String(bill.amount_cents),
    amountTolerancePct: String(bill.amount_tolerance_pct),
    anchorDate: bill.anchor_date,
    active: bill.active,
    notes: bill.notes ?? ""
  };
}

export function BillsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const today = new Date();

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingBillId, setEditingBillId] = useState<string | null>(null);
  const [formState, setFormState] = useState<BillFormState>(EMPTY_FORM);
  const [expandedBillId, setExpandedBillId] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const billsQuery = useQuery({
    queryKey: ["recurring-bills"],
    queryFn: () => fetchRecurringBills({ includeInactive: true, limit: 200, offset: 0 })
  });
  const overviewQuery = useQuery({
    queryKey: ["recurring-overview"],
    queryFn: fetchRecurringOverview
  });
  const calendarQuery = useQuery({
    queryKey: ["recurring-calendar", today.getFullYear(), today.getMonth() + 1],
    queryFn: () => fetchRecurringCalendar({ year: today.getFullYear(), month: today.getMonth() + 1 })
  });
  const occurrencesQuery = useQuery({
    queryKey: ["recurring-occurrences", expandedBillId],
    queryFn: () => fetchBillOccurrences(expandedBillId!, { limit: 100, offset: 0 }),
    enabled: Boolean(expandedBillId)
  });

  const saveBillMutation = useMutation({
    mutationFn: async (payload: BillFormState) => {
      const amountCents = payload.amountMode === "variable" ? null : Number(payload.amountCents);
      const sharedPayload = {
        name: payload.name.trim(),
        merchant_canonical: payload.merchantCanonical.trim() || null,
        merchant_alias_pattern: payload.merchantAliasPattern.trim() || null,
        category: payload.category.trim() || "uncategorized",
        frequency: payload.frequency,
        interval_value: Math.max(1, Number(payload.intervalValue)),
        amount_cents: amountCents,
        amount_tolerance_pct: Math.max(0, Number(payload.amountTolerancePct || "0.1")),
        currency: "EUR",
        anchor_date: payload.anchorDate,
        active: payload.active,
        notes: payload.notes.trim() || null
      } as const;

      if (editingBillId) {
        return updateRecurringBill(editingBillId, sharedPayload);
      }
      return createRecurringBill(sharedPayload);
    },
    onSuccess: () => {
      setEditorOpen(false);
      setEditingBillId(null);
      setFormState(EMPTY_FORM);
      setActionError(null);
      setActionStatus(editingBillId ? "Bill updated." : "Bill created.");
      void queryClient.invalidateQueries({ queryKey: ["recurring-bills"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : "Failed to save bill");
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (billId: string) => deleteRecurringBill(billId),
    onSuccess: () => {
      setActionStatus("Bill archived.");
      void queryClient.invalidateQueries({ queryKey: ["recurring-bills"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : "Failed to archive bill");
    }
  });

  const mutateOccurrenceMutation = useMutation({
    mutationFn: async (args: { kind: "skip" | "status" | "reconcile"; occurrenceId: string; status?: string; transactionId?: string }) => {
      if (args.kind === "skip") {
        return skipOccurrence(args.occurrenceId, null);
      }
      if (args.kind === "status" && args.status) {
        return updateOccurrenceStatus(args.occurrenceId, {
          status: args.status as "upcoming" | "due" | "paid" | "overdue" | "skipped" | "unmatched"
        });
      }
      return reconcileOccurrence(args.occurrenceId, {
        transaction_id: args.transactionId || "",
        match_method: "manual"
      });
    },
    onSuccess: () => {
      setActionStatus("Occurrence updated.");
      void queryClient.invalidateQueries({ queryKey: ["recurring-occurrences", expandedBillId] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : "Failed to update occurrence");
    }
  });

  const generateMutation = useMutation({
    mutationFn: (billId: string) => generateBillOccurrences(billId, { horizon_months: 6 }),
    onSuccess: () => {
      setActionStatus("Occurrences generated.");
      void queryClient.invalidateQueries({ queryKey: ["recurring-occurrences", expandedBillId] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : "Failed to generate occurrences");
    }
  });

  const matchMutation = useMutation({
    mutationFn: (billId: string) => runBillMatching(billId),
    onSuccess: (result) => {
      setActionStatus(`Matching complete: ${result.auto_matched} auto-matches.`);
      void queryClient.invalidateQueries({ queryKey: ["recurring-occurrences", expandedBillId] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(error instanceof Error ? error.message : "Failed to run matching");
    }
  });

  const bills = billsQuery.data?.items ?? [];
  const activeBills = bills.filter((bill) => bill.active);
  const selectedBill = useMemo(
    () => bills.find((bill) => bill.id === expandedBillId) ?? null,
    [bills, expandedBillId]
  );

  const dayCountsByDate = useMemo(() => {
    const map = new Map<string, number>();
    for (const day of calendarQuery.data?.days ?? []) {
      map.set(day.date, day.count);
    }
    return map;
  }, [calendarQuery.data?.days]);

  function openCreateDialog(): void {
    setEditingBillId(null);
    setFormState(EMPTY_FORM);
    setEditorOpen(true);
    setActionError(null);
  }

  function openEditDialog(bill: RecurringBill): void {
    setEditingBillId(bill.id);
    setFormState(toFormState(bill));
    setEditorOpen(true);
    setActionError(null);
  }

  function submitEditor(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    setActionStatus(null);
    setActionError(null);
    if (!formState.name.trim()) {
      setActionError("Bill name is required.");
      return;
    }
    if (!formState.anchorDate) {
      setActionError("Anchor date is required.");
      return;
    }
    if (formState.amountMode === "fixed") {
      const amount = Number(formState.amountCents);
      if (!Number.isFinite(amount) || amount <= 0) {
        setActionError("Amount cents must be a positive number for fixed bills.");
        return;
      }
    }
    void saveBillMutation.mutateAsync(formState);
  }

  function toggleOccurrencesForBill(billId: string): void {
    setExpandedBillId((current) => (current === billId ? null : billId));
  }

  function monthGridCells(): Array<
    { kind: "blank"; key: string } | { kind: "day"; isoDate: string; day: number; count: number }
  > {
    const year = today.getFullYear();
    const monthIndex = today.getMonth();
    const firstWeekday = new Date(year, monthIndex, 1).getDay();
    const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
    const cells: Array<
      { kind: "blank"; key: string } | { kind: "day"; isoDate: string; day: number; count: number }
    > = [];
    for (let index = 0; index < firstWeekday; index += 1) {
      cells.push({ kind: "blank", key: `blank-start-${index}` });
    }
    for (let day = 1; day <= daysInMonth; day += 1) {
      const isoDate = `${year}-${String(monthIndex + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      cells.push({
        kind: "day",
        isoDate,
        day,
        count: dayCountsByDate.get(isoDate) ?? 0
      });
    }
    while (cells.length % 7 !== 0) {
      cells.push({ kind: "blank", key: `blank-end-${cells.length}` });
    }
    return cells;
  }

  async function reconcileFromPrompt(occurrenceId: string): Promise<void> {
    const transactionId = window.prompt("Enter transaction ID to reconcile:");
    if (!transactionId || !transactionId.trim()) {
      return;
    }
    setActionStatus(null);
    setActionError(null);
    await mutateOccurrenceMutation.mutateAsync({
      kind: "reconcile",
      occurrenceId,
      transactionId: transactionId.trim()
    });
  }

  const monthName = today.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Recurring Bills</h2>
          <p className="text-sm text-muted-foreground">Track expected due dates, payment status, and matched transactions.</p>
        </div>
        <Button onClick={openCreateDialog}>Add bill</Button>
      </div>

      {actionStatus ? <p className="text-sm text-muted-foreground">{actionStatus}</p> : null}
      {actionError ? <p className="text-sm text-destructive">{actionError}</p> : null}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">Monthly committed</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold tabular-nums">
              {overviewQuery.data ? formatEurFromCents(overviewQuery.data.monthly_committed_cents) : "-"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">Active bills</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between">
            <p className="text-2xl font-semibold tabular-nums">{overviewQuery.data?.active_bills ?? activeBills.length}</p>
            <Wallet className="h-4 w-4 text-muted-foreground" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">Due this week</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between">
            <p className="text-2xl font-semibold tabular-nums">{overviewQuery.data?.due_this_week ?? 0}</p>
            <CalendarClock className="h-4 w-4 text-muted-foreground" />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs uppercase tracking-wide text-muted-foreground">Overdue</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-between">
            <p className="text-2xl font-semibold tabular-nums">{overviewQuery.data?.overdue ?? 0}</p>
            <CircleAlert className="h-4 w-4 text-destructive" />
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Bill list</CardTitle>
        </CardHeader>
        <CardContent>
          {billsQuery.isPending ? (
            <p className="text-sm text-muted-foreground">Loading bills...</p>
          ) : bills.length === 0 ? (
            <p className="text-sm text-muted-foreground">No recurring bills yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Frequency</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Merchant hint</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {bills.map((bill) => (
                  <TableRow key={bill.id}>
                    <TableCell>
                      <div className="font-medium">{bill.name}</div>
                      <div className="text-xs text-muted-foreground">{bill.category}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={bill.active ? "default" : "secondary"}>{bill.active ? "active" : "paused"}</Badge>
                    </TableCell>
                    <TableCell className="capitalize">{frequencyLabel(bill)}</TableCell>
                    <TableCell>{amountLabel(bill.amount_cents)}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {bill.merchant_canonical ?? bill.merchant_alias_pattern ?? "-"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => toggleOccurrencesForBill(bill.id)}
                        >
                          {expandedBillId === bill.id ? "Hide" : "Occurrences"}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => openEditDialog(bill)}>
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setActionStatus(null);
                            setActionError(null);
                            void generateMutation.mutateAsync(bill.id);
                          }}
                        >
                          Generate
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setActionStatus(null);
                            setActionError(null);
                            void matchMutation.mutateAsync(bill.id);
                          }}
                        >
                          Match
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => {
                            setActionStatus(null);
                            setActionError(null);
                            void deleteMutation.mutateAsync(bill.id);
                          }}
                        >
                          Archive
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {selectedBill ? (
        <Card>
          <CardHeader>
            <CardTitle>Occurrences: {selectedBill.name}</CardTitle>
          </CardHeader>
          <CardContent>
            {occurrencesQuery.isPending ? (
              <p className="text-sm text-muted-foreground">Loading occurrences...</p>
            ) : (occurrencesQuery.data?.items ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No generated occurrences for this bill.</p>
            ) : (
              <div className="space-y-2">
                {(occurrencesQuery.data?.items ?? []).map((occurrence) => (
                  <div
                    key={occurrence.id}
                    className="flex flex-col gap-2 rounded-md border p-3 md:flex-row md:items-center md:justify-between"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{occurrence.due_date}</span>
                        <Badge variant={statusBadgeVariant(occurrence.status)}>{occurrence.status}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Expected {amountLabel(occurrence.expected_amount_cents)}
                        {occurrence.actual_amount_cents !== null
                          ? ` • Actual ${formatEurFromCents(occurrence.actual_amount_cents)}`
                          : ""}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {occurrence.status !== "paid" ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setActionStatus(null);
                            setActionError(null);
                            void mutateOccurrenceMutation.mutateAsync({
                              kind: "status",
                              occurrenceId: occurrence.id,
                              status: "paid"
                            });
                          }}
                        >
                          Mark paid
                        </Button>
                      ) : null}
                      {occurrence.status !== "skipped" ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setActionStatus(null);
                            setActionError(null);
                            void mutateOccurrenceMutation.mutateAsync({ kind: "skip", occurrenceId: occurrence.id });
                          }}
                        >
                          Skip
                        </Button>
                      ) : null}
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setActionStatus(null);
                          setActionError(null);
                          void reconcileFromPrompt(occurrence.id);
                        }}
                      >
                        Reconcile
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CalendarCheck className="h-4 w-4" />
            Calendar strip ({monthName})
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-2 grid grid-cols-7 gap-2 text-center text-xs uppercase tracking-wide text-muted-foreground">
            <span>Sun</span>
            <span>Mon</span>
            <span>Tue</span>
            <span>Wed</span>
            <span>Thu</span>
            <span>Fri</span>
            <span>Sat</span>
          </div>
          <div className="grid grid-cols-7 gap-2">
            {monthGridCells().map((cell) =>
              cell.kind === "blank" ? (
                <div key={cell.key} className="rounded-md border border-dashed bg-muted/10 p-2" />
              ) : (
                <div key={cell.isoDate} className="rounded-md border bg-background p-2 text-center">
                  <p className="text-sm font-medium">{cell.day}</p>
                  {cell.count > 0 ? (
                    <Badge variant={cell.count > 2 ? "destructive" : "secondary"} className="mt-2">
                      {cell.count} due
                    </Badge>
                  ) : (
                    <p className="mt-2 text-xs text-muted-foreground">-</p>
                  )}
                </div>
              )
            )}
          </div>
        </CardContent>
      </Card>

      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingBillId ? "Edit recurring bill" : "Create recurring bill"}</DialogTitle>
          </DialogHeader>

          <form className="grid gap-3" onSubmit={submitEditor}>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="bill-name">Name</Label>
                <Input
                  id="bill-name"
                  value={formState.name}
                  onChange={(event) => setFormState((prev) => ({ ...prev, name: event.target.value }))}
                  placeholder="Netflix"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-category">Category</Label>
                <Input
                  id="bill-category"
                  value={formState.category}
                  onChange={(event) => setFormState((prev) => ({ ...prev, category: event.target.value }))}
                  placeholder="subscriptions"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-frequency">Frequency</Label>
                <select
                  id="bill-frequency"
                  className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                  value={formState.frequency}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      frequency: event.target.value as BillFormState["frequency"]
                    }))
                  }
                >
                  <option value="weekly">Weekly</option>
                  <option value="biweekly">Biweekly</option>
                  <option value="monthly">Monthly</option>
                  <option value="quarterly">Quarterly</option>
                  <option value="yearly">Yearly</option>
                </select>
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-interval">Interval</Label>
                <Input
                  id="bill-interval"
                  type="number"
                  min={1}
                  value={formState.intervalValue}
                  onChange={(event) => setFormState((prev) => ({ ...prev, intervalValue: event.target.value }))}
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-anchor-date">Anchor date</Label>
                <Input
                  id="bill-anchor-date"
                  type="date"
                  value={formState.anchorDate}
                  onChange={(event) => setFormState((prev) => ({ ...prev, anchorDate: event.target.value }))}
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-amount-mode">Amount mode</Label>
                <select
                  id="bill-amount-mode"
                  className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                  value={formState.amountMode}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      amountMode: event.target.value as "fixed" | "variable"
                    }))
                  }
                >
                  <option value="fixed">Fixed</option>
                  <option value="variable">Variable</option>
                </select>
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-amount-cents">Amount (cents)</Label>
                <Input
                  id="bill-amount-cents"
                  type="number"
                  value={formState.amountCents}
                  disabled={formState.amountMode === "variable"}
                  onChange={(event) => setFormState((prev) => ({ ...prev, amountCents: event.target.value }))}
                  placeholder="1299"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-tolerance">Amount tolerance</Label>
                <Input
                  id="bill-tolerance"
                  type="number"
                  step="0.01"
                  min={0}
                  value={formState.amountTolerancePct}
                  onChange={(event) =>
                    setFormState((prev) => ({ ...prev, amountTolerancePct: event.target.value }))
                  }
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-merchant-canonical">Merchant (canonical)</Label>
                <Input
                  id="bill-merchant-canonical"
                  value={formState.merchantCanonical}
                  onChange={(event) =>
                    setFormState((prev) => ({ ...prev, merchantCanonical: event.target.value }))
                  }
                  placeholder="netflix"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-merchant-pattern">Merchant alias pattern</Label>
                <Input
                  id="bill-merchant-pattern"
                  value={formState.merchantAliasPattern}
                  onChange={(event) =>
                    setFormState((prev) => ({ ...prev, merchantAliasPattern: event.target.value }))
                  }
                  placeholder="NETFLIX|NET FLIX"
                />
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor="bill-notes">Notes</Label>
              <Textarea
                id="bill-notes"
                value={formState.notes}
                onChange={(event) => setFormState((prev) => ({ ...prev, notes: event.target.value }))}
                placeholder="Auto-debit on card ending 1288"
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditorOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saveBillMutation.isPending}>
                {editingBillId ? "Save changes" : "Create bill"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
