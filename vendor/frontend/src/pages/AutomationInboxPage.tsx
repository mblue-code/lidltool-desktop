import { useQuery } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { automationExecutionsQueryOptions } from "@/app/queries";
import { AutomationExecution } from "@/api/automations";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import {
  STICKY_TABLE_COLUMN_CLASS,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "@/components/ui/table";
import { useI18n } from "@/i18n";
import { formatDateTime } from "../utils/format";

const PAGE_SIZE = 25;

function parseOffset(raw: string | null): number {
  const value = Number(raw ?? "0");
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.floor(value));
}

function statusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "success") {
    return "default";
  }
  if (status === "skipped") {
    return "secondary";
  }
  if (status === "failed") {
    return "destructive";
  }
  return "outline";
}

function resultSummary(execution: AutomationExecution): string {
  if (execution.status === "failed") {
    return "Execution failed";
  }
  const template = execution.result?.template;
  if (typeof template === "string" && template.trim()) {
    return template;
  }
  if (execution.status === "skipped") {
    return "Skipped by rule conditions";
  }
  return "Completed";
}

function buildPayloadJson(execution: AutomationExecution): string {
  return JSON.stringify(
    {
      id: execution.id,
      rule_id: execution.rule_id,
      rule_name: execution.rule_name,
      rule_type: execution.rule_type,
      status: execution.status,
      triggered_at: execution.triggered_at,
      executed_at: execution.executed_at,
      result: execution.result,
      error: execution.error
    },
    null,
    2
  );
}

export function AutomationInboxPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const appliedStatusFilter = searchParams.get("status") ?? "";
  const appliedRuleTypeFilter = searchParams.get("rule_type") ?? "";
  const offset = parseOffset(searchParams.get("offset"));

  const [statusFilter, setStatusFilter] = useState(appliedStatusFilter);
  const [ruleTypeFilter, setRuleTypeFilter] = useState(appliedRuleTypeFilter);
  const [selectedExecution, setSelectedExecution] = useState<AutomationExecution | null>(null);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const { t } = useI18n();

  useEffect(() => {
    setStatusFilter(appliedStatusFilter);
    setRuleTypeFilter(appliedRuleTypeFilter);
  }, [appliedRuleTypeFilter, appliedStatusFilter]);

  const { data, error, isPending, isFetching } = useQuery(
    automationExecutionsQueryOptions({
      status: appliedStatusFilter || undefined,
      ruleType: appliedRuleTypeFilter || undefined,
      limit: PAGE_SIZE,
      offset
    })
  );
  const executions = data?.items ?? [];
  const total = data?.total ?? 0;
  const canGoPrevious = offset > 0;
  const canGoNext = offset + PAGE_SIZE < total;
  const loading = isPending || isFetching;
  const errorMessage = error instanceof Error ? error.message : null;
  const selectedPayload = useMemo(
    () => (selectedExecution ? buildPayloadJson(selectedExecution) : ""),
    [selectedExecution]
  );

  function submitFilters(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const next = new URLSearchParams(searchParams);
    if (statusFilter) {
      next.set("status", statusFilter);
    } else {
      next.delete("status");
    }
    if (ruleTypeFilter) {
      next.set("rule_type", ruleTypeFilter);
    } else {
      next.delete("rule_type");
    }
    next.set("offset", "0");
    setSearchParams(next);
  }

  function clearFilters(): void {
    setStatusFilter("");
    setRuleTypeFilter("");
    const next = new URLSearchParams(searchParams);
    next.delete("status");
    next.delete("rule_type");
    next.set("offset", "0");
    setSearchParams(next);
  }

  function movePage(delta: number): void {
    const next = new URLSearchParams(searchParams);
    next.set("offset", String(Math.max(0, offset + delta)));
    setSearchParams(next);
  }

  async function copyPayload(): Promise<void> {
    if (!selectedPayload) {
      return;
    }
    if (!navigator.clipboard) {
      setCopyStatus("Clipboard unavailable in this browser.");
      return;
    }
    try {
      await navigator.clipboard.writeText(selectedPayload);
      setCopyStatus("Payload copied.");
    } catch (_error) {
      setCopyStatus("Failed to copy payload.");
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.automations")} description={t("pages.automationInbox.title")} />
      <Card>
        <CardContent className="pt-6">
          <form className="grid gap-3 md:grid-cols-3" onSubmit={submitFilters}>
            <div className="space-y-2">
              <Label htmlFor="inbox-status-filter">Status</Label>
              <Select
                value={statusFilter || "all"}
                onValueChange={(value) => setStatusFilter(value === "all" ? "" : value)}
              >
                <SelectTrigger id="inbox-status-filter">
                  <SelectValue placeholder="Any" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any</SelectItem>
                  <SelectItem value="success">Success</SelectItem>
                  <SelectItem value="skipped">Skipped</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="inbox-template-filter">Template</Label>
              <Select
                value={ruleTypeFilter || "all"}
                onValueChange={(value) => setRuleTypeFilter(value === "all" ? "" : value)}
              >
                <SelectTrigger id="inbox-template-filter">
                  <SelectValue placeholder="Any" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any</SelectItem>
                  <SelectItem value="category_auto_tagging">Category auto-tagging</SelectItem>
                  <SelectItem value="budget_alert">Budget alert</SelectItem>
                  <SelectItem value="weekly_summary">Weekly summary</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 self-end">
              <Button type="submit">Apply filters</Button>
              <Button type="button" variant="outline" onClick={clearFilters}>
                Clear
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {loading ? <p className="text-sm text-muted-foreground">Loading execution history...</p> : null}
      {errorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>Failed to load automation inbox</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className={STICKY_TABLE_COLUMN_CLASS}>Triggered</TableHead>
                <TableHead>Rule</TableHead>
                <TableHead>Template</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Outcome</TableHead>
                <TableHead>Error</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {executions.map((execution) => (
                <TableRow key={execution.id}>
                  <TableCell className={STICKY_TABLE_COLUMN_CLASS}>{formatDateTime(execution.triggered_at)}</TableCell>
                  <TableCell>{execution.rule_name || execution.rule_id}</TableCell>
                  <TableCell>{execution.rule_type || "-"}</TableCell>
                  <TableCell>
                    <Badge variant={statusBadgeVariant(execution.status)}>
                      {execution.status}
                    </Badge>
                  </TableCell>
                  <TableCell>{resultSummary(execution)}</TableCell>
                  <TableCell>{execution.error || "-"}</TableCell>
                  <TableCell className="text-right">
                    <Button type="button" variant="outline" size="sm" onClick={() => setSelectedExecution(execution)}>
                      View payload
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {executions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7}>
                    <EmptyState
                      title={t("pages.automationInbox.emptyTitle")}
                      description={t("pages.automationInbox.emptyDescription")}
                      action={{ label: t("pages.automationInbox.emptyAction"), href: "/automations" }}
                    />
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-muted-foreground">
              Showing {total === 0 ? 0 : offset + 1}-{Math.min(offset + PAGE_SIZE, total)} of {total}
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={!canGoPrevious}
                onClick={() => movePage(-PAGE_SIZE)}
              >
                Previous
              </Button>
              <Button type="button" variant="outline" disabled={!canGoNext} onClick={() => movePage(PAGE_SIZE)}>
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={selectedExecution !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedExecution(null);
            setCopyStatus(null);
          }
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Execution payload</DialogTitle>
            <DialogDescription>
              Inspect the full execution payload for troubleshooting and audit review.
            </DialogDescription>
            {selectedExecution?.rule_id ? (
              <Link to="/automations" className="text-sm text-primary underline">
                {t("pages.automationInbox.editRule")}
              </Link>
            ) : null}
          </DialogHeader>

          <div className="rounded-md border bg-muted/20 p-3">
            <pre className="max-h-[50vh] overflow-auto text-xs">{selectedPayload || "{}"}</pre>
          </div>

          {copyStatus ? <p className="text-sm text-muted-foreground">{copyStatus}</p> : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setSelectedExecution(null)}>
              Close
            </Button>
            <Button type="button" onClick={() => void copyPayload()}>
              Copy payload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
