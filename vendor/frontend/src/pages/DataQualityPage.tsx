import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import {
  fetchLowConfidenceOcr,
  fetchQualityRecategorizeStatus,
  fetchUnmatchedItems,
  startQualityRecategorize
} from "@/api/quality";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/i18n";
import { formatEurFromCents } from "@/utils/format";

export function DataQualityPage() {
  const { t } = useI18n();
  const [threshold, setThreshold] = useState("0.85");
  const [recategorizeJobId, setRecategorizeJobId] = useState<string | null>(null);

  const unmatchedQuery = useQuery({
    queryKey: ["quality-unmatched"],
    queryFn: () => fetchUnmatchedItems(200)
  });
  const lowConfidenceQuery = useQuery({
    queryKey: ["quality-low-confidence", threshold],
    queryFn: () => fetchLowConfidenceOcr({ threshold: Number(threshold), limit: 200 })
  });
  const recategorizeMutation = useMutation({
    mutationFn: () =>
      startQualityRecategorize({
        only_fallback_other: true,
        include_suspect_model_items: true,
        max_transactions: 500
      }),
    onSuccess: (job) => {
      setRecategorizeJobId(job.job_id);
    }
  });
  const recategorizeStatusQuery = useQuery({
    queryKey: ["quality-recategorize-status", recategorizeJobId],
    queryFn: () => fetchQualityRecategorizeStatus(recategorizeJobId ?? ""),
    enabled: Boolean(recategorizeJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1500 : false;
    }
  });

  const recategorizeJob = recategorizeStatusQuery.data;
  const recategorizeRunning =
    recategorizeMutation.isPending ||
    recategorizeJob?.status === "queued" ||
    recategorizeJob?.status === "running";

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.dataQuality")} />
      <div className="flex flex-wrap items-end gap-6">
        <div>
          <p className="text-sm text-muted-foreground">Unmatched items</p>
          <p className="text-2xl font-semibold">{unmatchedQuery.data?.count ?? 0}</p>
        </div>
        <div>
          <p className="text-sm text-muted-foreground">Low-confidence OCR docs</p>
          <p className="text-2xl font-semibold">{lowConfidenceQuery.data?.count ?? 0}</p>
        </div>
        <div className="space-y-1">
          <Label htmlFor="quality-threshold">OCR threshold</Label>
          <div className="flex gap-2">
            <Input
              id="quality-threshold"
              value={threshold}
              onChange={(event) => setThreshold(event.target.value)}
              type="number"
              min="0"
              max="1"
              step="0.01"
            />
            <Button variant="outline" onClick={() => lowConfidenceQuery.refetch()}>
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Tools</CardTitle>
          <Button onClick={() => recategorizeMutation.mutate()} disabled={recategorizeRunning}>
            {recategorizeRunning ? "Repairing categories..." : "Repair item categories"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Re-run categorization for items that are still in <code>other</code>, were assigned via
            <code> fallback_other</code>, or were previously labeled by the local model and look suspicious in context.
            This uses the configured categorization runtime and writes results back into the normal transaction path.
          </p>
          {recategorizeMutation.isError ? (
            <p className="text-destructive">Failed to start recategorization.</p>
          ) : null}
          {recategorizeJob ? (
            <div className="rounded-md border p-3 text-foreground">
              <p>Status: {recategorizeJob.status}</p>
              <p>Transactions scanned: {recategorizeJob.transaction_count}</p>
              <p>Candidate items: {recategorizeJob.candidate_item_count}</p>
              <p>Updated items: {recategorizeJob.updated_item_count}</p>
              <p>Updated transactions: {recategorizeJob.updated_transaction_count}</p>
              {recategorizeJob.error ? <p className="text-destructive">Error: {recategorizeJob.error}</p> : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Unmatched Items</CardTitle>
        </CardHeader>
        <CardContent>
          {unmatchedQuery.data?.items.length ? (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Raw name</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Purchases</TableHead>
                  <TableHead>Total spend</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {unmatchedQuery.data.items.map((item) => (
                  <TableRow key={`${item.source_kind}-${item.raw_name}`}>
                    <TableCell>{item.raw_name}</TableCell>
                    <TableCell>{item.source_kind}</TableCell>
                    <TableCell>{item.purchase_count}</TableCell>
                    <TableCell>{formatEurFromCents(item.total_spend_cents)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          ) : (
            <EmptyState title={t("pages.dataQuality.emptyUnmatched")} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Low-confidence OCR</CardTitle>
          {(lowConfidenceQuery.data?.items.length ?? 0) > 0 ? (
            <Button variant="outline" size="sm" asChild>
              <Link to="/review-queue">{t("pages.dataQuality.reviewThem")}</Link>
            </Button>
          ) : null}
        </CardHeader>
        <CardContent>
          {lowConfidenceQuery.data?.items.length ? (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Document</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Review status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lowConfidenceQuery.data.items.map((item) => (
                  <TableRow key={item.document_id}>
                    <TableCell>{item.file_name ?? item.document_id}</TableCell>
                    <TableCell>{item.source_id ?? "-"}</TableCell>
                    <TableCell>{item.ocr_confidence ?? "-"}</TableCell>
                    <TableCell>{item.review_status ?? "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          ) : (
            <EmptyState
              title={t("pages.dataQuality.emptyLowConfidence")}
              action={{ label: t("pages.dataQuality.reviewThem"), href: "/review-queue" }}
            />
          )}
        </CardContent>
      </Card>
    </section>
  );
}
