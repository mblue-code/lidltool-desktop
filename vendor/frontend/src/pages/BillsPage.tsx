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
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { MetricCard } from "@/components/shared/MetricCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { SearchInput } from "@/components/shared/SearchInput";
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
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { formatDate, formatEurFromCents, formatMonthYear } from "@/utils/format";

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

export function BillsPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const today = new Date();

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingBillId, setEditingBillId] = useState<string | null>(null);
  const [formState, setFormState] = useState<BillFormState>(EMPTY_FORM);
  const [expandedBillId, setExpandedBillId] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [archiveConfirmBillId, setArchiveConfirmBillId] = useState<string | null>(null);
  const [billSearch, setBillSearch] = useState("");

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
      setActionStatus(editingBillId ? t("pages.bills.updated") : t("pages.bills.created"));
      void queryClient.invalidateQueries({ queryKey: ["recurring-bills"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(resolveApiErrorMessage(error, t, t("pages.bills.saveFailed")));
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (billId: string) => deleteRecurringBill(billId),
    onSuccess: () => {
      setActionStatus(t("pages.bills.archived"));
      void queryClient.invalidateQueries({ queryKey: ["recurring-bills"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(resolveApiErrorMessage(error, t, t("pages.bills.archiveFailed")));
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
      setActionStatus(t("pages.bills.occurrenceUpdated"));
      void queryClient.invalidateQueries({ queryKey: ["recurring-occurrences", expandedBillId] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(resolveApiErrorMessage(error, t, t("pages.bills.occurrenceFailed")));
    }
  });

  const generateMutation = useMutation({
    mutationFn: (billId: string) => generateBillOccurrences(billId, { horizon_months: 6 }),
    onSuccess: () => {
      setActionStatus(t("pages.bills.occurrencesGenerated"));
      void queryClient.invalidateQueries({ queryKey: ["recurring-occurrences", expandedBillId] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(resolveApiErrorMessage(error, t, t("pages.bills.generateFailed")));
    }
  });

  const matchMutation = useMutation({
    mutationFn: (billId: string) => runBillMatching(billId),
    onSuccess: (result) => {
      setActionStatus(t("pages.bills.matchingComplete", { count: result.auto_matched }));
      void queryClient.invalidateQueries({ queryKey: ["recurring-occurrences", expandedBillId] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-overview"] });
      void queryClient.invalidateQueries({ queryKey: ["recurring-calendar"] });
    },
    onError: (error) => {
      setActionError(resolveApiErrorMessage(error, t, t("pages.bills.matchFailed")));
    }
  });

  const bills = billsQuery.data?.items ?? [];
  const activeBills = bills.filter((bill) => bill.active);
  const filteredBills = billSearch
    ? bills.filter((bill) => bill.name.toLowerCase().includes(billSearch.toLowerCase()))
    : bills;
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
      setActionError(t("pages.bills.validation.nameRequired"));
      return;
    }
    if (!formState.anchorDate) {
      setActionError(t("pages.bills.validation.anchorRequired"));
      return;
    }
    if (formState.amountMode === "fixed") {
      const amount = Number(formState.amountCents);
      if (!Number.isFinite(amount) || amount <= 0) {
        setActionError(t("pages.bills.validation.amountRequired"));
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
    const transactionId = window.prompt(t("pages.bills.reconcilePrompt"));
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

  const monthName = formatMonthYear(today);

  return (
    <section className="space-y-4">
      <PageHeader title={t("pages.bills.title")} description={t("pages.bills.subtitle")}>
        <Button onClick={openCreateDialog}>{t("pages.bills.add")}</Button>
      </PageHeader>

      {actionStatus ? <p className="text-sm text-muted-foreground">{actionStatus}</p> : null}
      {actionError ? <p className="text-sm text-destructive">{actionError}</p> : null}

      <section className="rounded-xl border border-border/60 app-dashboard-surface grid divide-y sm:divide-y-0 sm:divide-x divide-border/40 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title={t("pages.bills.metric.monthlyCommitted")}
          value={overviewQuery.data ? formatEurFromCents(overviewQuery.data.monthly_committed_cents) : "-"}
        />
        <MetricCard
          title={t("pages.bills.metric.activeBills")}
          value={String(overviewQuery.data?.active_bills ?? activeBills.length)}
          icon={<Wallet className="h-4 w-4" />}
          iconClassName="text-muted-foreground"
        />
        <MetricCard
          title={t("pages.bills.metric.dueThisWeek")}
          value={String(overviewQuery.data?.due_this_week ?? 0)}
          icon={<CalendarClock className="h-4 w-4" />}
          iconClassName="text-muted-foreground"
        />
        <MetricCard
          title={t("pages.bills.metric.overdue")}
          value={String(overviewQuery.data?.overdue ?? 0)}
          icon={<CircleAlert className="h-4 w-4" />}
          iconClassName="text-destructive"
        />
      </section>

      <Card>
        <CardHeader>
          <CardTitle>{t("pages.bills.listTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Label htmlFor="bills-search" className="sr-only">
            {t("pages.bills.searchBills")}
          </Label>
          <SearchInput
            id="bills-search"
            value={billSearch}
            onChange={setBillSearch}
            placeholder={t("pages.bills.searchBills")}
            className="max-w-sm"
          />
          {billsQuery.isPending ? (
            <p className="text-sm text-muted-foreground">{t("pages.bills.loading")}</p>
          ) : filteredBills.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("pages.bills.empty")}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("pages.bills.col.name")}</TableHead>
                  <TableHead>{t("pages.bills.col.status")}</TableHead>
                  <TableHead>{t("pages.bills.col.frequency")}</TableHead>
                  <TableHead>{t("pages.bills.col.amount")}</TableHead>
                  <TableHead>{t("pages.bills.col.merchantHint")}</TableHead>
                  <TableHead className="text-right">{t("common.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredBills.map((bill) => (
                  <TableRow key={bill.id}>
                    <TableCell>
                      <div className="font-medium">{bill.name}</div>
                      <div className="text-xs text-muted-foreground">{bill.category}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={bill.active ? "default" : "secondary"}>{bill.active ? t("pages.bills.active") : t("pages.bills.paused")}</Badge>
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
                          {expandedBillId === bill.id ? t("pages.bills.hideOccurrences") : t("pages.bills.showOccurrences")}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => openEditDialog(bill)}>
                          {t("common.edit")}
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
                          {t("pages.bills.generate")}
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
                          {t("pages.bills.match")}
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => setArchiveConfirmBillId(bill.id)}
                        >
                          {t("pages.bills.archive")}
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
            <CardTitle>{t("pages.bills.occurrencesTitle", { name: selectedBill.name })}</CardTitle>
          </CardHeader>
          <CardContent>
            {occurrencesQuery.isPending ? (
              <p className="text-sm text-muted-foreground">{t("pages.bills.loadingOccurrences")}</p>
            ) : (occurrencesQuery.data?.items ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("pages.bills.noOccurrences")}</p>
            ) : (
              <div className="divide-y divide-border/40">
                {(occurrencesQuery.data?.items ?? []).map((occurrence) => (
                  <div
                    key={occurrence.id}
                    className="flex flex-col gap-2 py-3 md:flex-row md:items-center md:justify-between"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{formatDate(occurrence.due_date)}</span>
                        <Badge variant={statusBadgeVariant(occurrence.status)}>{occurrence.status}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {t("pages.bills.expectedAmount", {
                          amount: amountLabel(occurrence.expected_amount_cents),
                          actualSuffix:
                            occurrence.actual_amount_cents !== null
                              ? ` • ${t("pages.bills.actualAmount", {
                                  amount: formatEurFromCents(occurrence.actual_amount_cents)
                                })}`
                              : ""
                        })}
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
                          {t("pages.bills.markPaid")}
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
                          {t("pages.bills.skip")}
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
                        {t("pages.bills.reconcile")}
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
              {t("pages.bills.calendarTitle", { month: monthName })}
            </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="hidden md:block">
            <div className="mb-2 grid grid-cols-7 gap-2 text-center text-xs uppercase tracking-wide text-muted-foreground">
              <span>{t("pages.bills.day.sun")}</span>
              <span>{t("pages.bills.day.mon")}</span>
              <span>{t("pages.bills.day.tue")}</span>
              <span>{t("pages.bills.day.wed")}</span>
              <span>{t("pages.bills.day.thu")}</span>
              <span>{t("pages.bills.day.fri")}</span>
              <span>{t("pages.bills.day.sat")}</span>
            </div>
            <div className="grid grid-cols-7 gap-2">
              {monthGridCells().map((cell) =>
                cell.kind === "blank" ? (
                  <div key={cell.key} className="rounded-md border border-dashed bg-muted/10 p-2" />
                ) : (
                  <div key={cell.isoDate} className="app-soft-surface rounded-md border p-2 text-center">
                    <p className="text-sm font-medium">{cell.day}</p>
                    {cell.count > 0 ? (
                      <Badge variant={cell.count > 2 ? "destructive" : "secondary"} className="mt-2">
                        {t("pages.bills.dayDue", { count: cell.count })}
                      </Badge>
                    ) : (
                      <p className="mt-2 text-xs text-muted-foreground">-</p>
                    )}
                  </div>
                )
              )}
            </div>
          </div>
          <div className="md:hidden space-y-2">
            {monthGridCells()
              .filter((cell): cell is Extract<typeof cell, { kind: "day" }> => cell.kind === "day" && cell.count > 0)
              .map((cell) => (
                <div key={cell.isoDate} className="flex items-center justify-between rounded-md border px-3 py-2">
                  <span className="text-sm font-medium">{cell.isoDate}</span>
                  <Badge variant={cell.count > 2 ? "destructive" : "secondary"}>
                    {t("pages.bills.dayDue", { count: cell.count })}
                  </Badge>
                </div>
              ))}
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={archiveConfirmBillId !== null}
        onOpenChange={(open) => { if (!open) setArchiveConfirmBillId(null); }}
        title={t("pages.bills.confirmArchiveTitle")}
        description={t("pages.bills.confirmArchiveDescription")}
        variant="destructive"
        confirmLabel={t("pages.bills.archive")}
        onConfirm={() => {
          if (archiveConfirmBillId) {
            setActionStatus(null);
            setActionError(null);
            void deleteMutation.mutateAsync(archiveConfirmBillId);
          }
        }}
      />

      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingBillId ? t("pages.bills.dialog.editTitle") : t("pages.bills.dialog.createTitle")}</DialogTitle>
          </DialogHeader>

          <form className="grid gap-3" onSubmit={submitEditor}>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="bill-name">{t("pages.bills.form.name")}</Label>
                <Input
                  id="bill-name"
                  value={formState.name}
                  onChange={(event) => setFormState((prev) => ({ ...prev, name: event.target.value }))}
                  placeholder="Netflix"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-category">{t("pages.bills.form.category")}</Label>
                <Input
                  id="bill-category"
                  value={formState.category}
                  onChange={(event) => setFormState((prev) => ({ ...prev, category: event.target.value }))}
                  placeholder="subscriptions"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-frequency">{t("pages.bills.form.frequency")}</Label>
                <select
                  id="bill-frequency"
                  className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
                  value={formState.frequency}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      frequency: event.target.value as BillFormState["frequency"]
                    }))
                  }
                >
                  <option value="weekly">{t("pages.bills.form.frequency.weekly")}</option>
                  <option value="biweekly">{t("pages.bills.form.frequency.biweekly")}</option>
                  <option value="monthly">{t("pages.bills.form.frequency.monthly")}</option>
                  <option value="quarterly">{t("pages.bills.form.frequency.quarterly")}</option>
                  <option value="yearly">{t("pages.bills.form.frequency.yearly")}</option>
                </select>
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-interval">{t("pages.bills.form.interval")}</Label>
                <Input
                  id="bill-interval"
                  type="number"
                  min={1}
                  value={formState.intervalValue}
                  onChange={(event) => setFormState((prev) => ({ ...prev, intervalValue: event.target.value }))}
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-anchor-date">{t("pages.bills.form.anchorDate")}</Label>
                <Input
                  id="bill-anchor-date"
                  type="date"
                  value={formState.anchorDate}
                  onChange={(event) => setFormState((prev) => ({ ...prev, anchorDate: event.target.value }))}
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-amount-mode">{t("pages.bills.form.amountMode")}</Label>
                <select
                  id="bill-amount-mode"
                  className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
                  value={formState.amountMode}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      amountMode: event.target.value as "fixed" | "variable"
                    }))
                  }
                >
                  <option value="fixed">{t("pages.bills.form.amountMode.fixed")}</option>
                  <option value="variable">{t("pages.bills.form.amountMode.variable")}</option>
                </select>
              </div>

              <div className="space-y-1">
                <Label htmlFor="bill-amount-cents">{t("pages.bills.form.amountCents")}</Label>
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
                <Label htmlFor="bill-tolerance">{t("pages.bills.form.amountTolerance")}</Label>
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
                <Label htmlFor="bill-merchant-canonical">{t("pages.bills.form.merchantCanonical")}</Label>
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
                <Label htmlFor="bill-merchant-pattern">{t("pages.bills.form.merchantPattern")}</Label>
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
              <Label htmlFor="bill-notes">{t("pages.bills.form.notes")}</Label>
              <Textarea
                id="bill-notes"
                value={formState.notes}
                onChange={(event) => setFormState((prev) => ({ ...prev, notes: event.target.value }))}
                placeholder="Auto-debit on card ending 1288"
              />
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditorOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={saveBillMutation.isPending}>
                {editingBillId ? t("pages.bills.form.saveChanges") : t("pages.bills.form.create")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
