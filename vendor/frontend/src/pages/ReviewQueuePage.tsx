import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { reviewQueueDetailQueryOptions, reviewQueueQueryOptions } from "@/app/queries";
import {
  approveReviewDocument,
  patchReviewItem,
  patchReviewTransaction,
  rejectReviewDocument,
  ReviewCorrectionRequest,
  ReviewDecisionRequest
} from "@/api/reviewQueue";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle
} from "@/components/ui/sheet";
import {
  STICKY_TABLE_COLUMN_CLASS,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { jsonObjectStringSchema } from "@/lib/json-object-field";
import { formatDateTime, formatEurFromCents } from "@/utils/format";

const PAGE_SIZE = 25;
const EMPTY_ITEM_VALUE = "__empty_item__";

const reviewQueueFormSchema = z.object({
  actorId: z.string().trim().max(120, "Actor ID must be 120 characters or less."),
  reason: z.string().trim().max(280, "Reason must be 280 characters or less."),
  transactionCorrectionsJson: z.string(),
  selectedItemId: z.string(),
  itemCorrectionsJson: z.string()
});

const decisionFormSchema = z.object({
  actorId: reviewQueueFormSchema.shape.actorId,
  reason: reviewQueueFormSchema.shape.reason
});

const transactionPatchFormSchema = z.object({
  actorId: reviewQueueFormSchema.shape.actorId,
  reason: reviewQueueFormSchema.shape.reason,
  transactionCorrectionsJson: jsonObjectStringSchema("Transaction corrections")
});

const itemPatchFormSchema = z.object({
  actorId: reviewQueueFormSchema.shape.actorId,
  reason: reviewQueueFormSchema.shape.reason,
  selectedItemId: z.string().trim().min(1, "Choose an item before applying item corrections."),
  itemCorrectionsJson: jsonObjectStringSchema("Item corrections")
});

type ReviewQueueFormValues = z.input<typeof reviewQueueFormSchema>;

function reviewStatusClass(status: string): string {
  switch (status) {
    case "approved": return "border-transparent bg-success/15 text-success";
    case "rejected": return "border-transparent bg-destructive/15 text-destructive";
    case "needs_review": return "border-transparent bg-chart-3/15 text-chart-3";
    default: return "";
  }
}

function ocrStatusClass(status: string): string {
  switch (status) {
    case "completed": return "border-transparent bg-success/15 text-success";
    case "failed": return "border-transparent bg-destructive/15 text-destructive";
    default: return "border-transparent bg-muted text-muted-foreground";
  }
}

function parsePositiveInt(rawValue: string | null, fallback: number): number {
  if (!rawValue) {
    return fallback;
  }
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(0, Math.floor(parsed));
}

function parseThreshold(rawValue: string | null, fallback = 0.85): number {
  if (!rawValue) {
    return fallback;
  }
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(1, Math.max(0, parsed));
}

export function ReviewQueuePage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { t } = useI18n();
  const { documentId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  const statusFromQuery = searchParams.get("status") || "needs_review";
  const thresholdFromQuery = parseThreshold(searchParams.get("threshold"), 0.85);
  const offset = parsePositiveInt(searchParams.get("offset"), 0);

  const [statusFilter, setStatusFilter] = useState<string>(statusFromQuery);
  const [thresholdFilter, setThresholdFilter] = useState<string>(thresholdFromQuery.toString());
  const [mutationStatus, setMutationStatus] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [batchApproveOpen, setBatchApproveOpen] = useState(false);

  const form = useForm<ReviewQueueFormValues>({
    resolver: zodResolver(reviewQueueFormSchema),
    defaultValues: {
      actorId: "reviewer-ui",
      reason: "",
      transactionCorrectionsJson: "{}",
      selectedItemId: "",
      itemCorrectionsJson: '{"category":"uncategorized"}'
    }
  });

  const queueQuery = useQuery(
    reviewQueueQueryOptions({
      status: statusFromQuery,
      threshold: thresholdFromQuery,
      limit: PAGE_SIZE,
      offset
    })
  );

  const detailQuery = useQuery({
    ...reviewQueueDetailQueryOptions(documentId ?? ""),
    enabled: Boolean(documentId)
  });

  const queueItems = queueQuery.data?.items ?? [];
  const total = queueQuery.data?.total ?? 0;
  const canGoNext = offset + PAGE_SIZE < total;
  const canGoPrevious = offset > 0;
  const detail = detailQuery.data ?? null;

  const selectedItemId = form.watch("selectedItemId");
  const hasDetailItems = (detail?.items.length ?? 0) > 0;
  const selectedItemInDetail = detail?.items.some((item) => item.id === selectedItemId) ?? false;

  useEffect(() => {
    if (!detail) {
      if (selectedItemId) {
        form.setValue("selectedItemId", "", {
          shouldDirty: false,
          shouldValidate: true
        });
      }
      return;
    }
    if (!selectedItemInDetail) {
      form.setValue("selectedItemId", detail.items[0]?.id ?? "", {
        shouldDirty: false,
        shouldValidate: true
      });
    }
  }, [detail, form, selectedItemId, selectedItemInDetail]);

  const paginationLabel =
    total === 0
      ? t("pages.reviewQueue.pagination.empty")
      : t("pages.reviewQueue.pagination.summary", {
          start: offset + 1,
          end: Math.min(offset + PAGE_SIZE, total),
          total
        });

  const decisionMutation = useMutation({
    mutationFn: async ({
      action,
      payload
    }: {
      action: "approve" | "reject";
      payload: ReviewDecisionRequest;
    }) => {
      if (!documentId) {
        throw new Error(t("pages.reviewQueue.detail.title"));
      }
      if (action === "approve") {
        return approveReviewDocument(documentId, payload);
      }
      return rejectReviewDocument(documentId, payload);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review-queue"] }),
        queryClient.invalidateQueries({ queryKey: ["review-queue-detail", documentId] })
      ]);
    }
  });

  const patchTransactionMutation = useMutation({
    mutationFn: async (payload: ReviewCorrectionRequest) => {
      if (!documentId) {
        throw new Error(t("pages.reviewQueue.detail.title"));
      }
      return patchReviewTransaction(documentId, payload);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review-queue"] }),
        queryClient.invalidateQueries({ queryKey: ["review-queue-detail", documentId] })
      ]);
    }
  });

  const patchItemMutation = useMutation({
    mutationFn: async ({
      itemId,
      payload
    }: {
      itemId: string;
      payload: ReviewCorrectionRequest;
    }) => {
      if (!documentId) {
        throw new Error(t("pages.reviewQueue.detail.title"));
      }
      return patchReviewItem(documentId, itemId, payload);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["review-queue"] }),
        queryClient.invalidateQueries({ queryKey: ["review-queue-detail", documentId] })
      ]);
    }
  });

  function applyValidationIssues(issues: z.ZodIssue[]): void {
    for (const issue of issues) {
      const field = issue.path[0];
      if (
        field === "actorId" ||
        field === "reason" ||
        field === "transactionCorrectionsJson" ||
        field === "selectedItemId" ||
        field === "itemCorrectionsJson"
      ) {
        form.setError(field, { message: issue.message });
      }
    }
  }

  function toDecisionPayload(values: { actorId: string; reason: string }): ReviewDecisionRequest {
    return {
      actor_id: values.actorId || undefined,
      reason: values.reason || undefined
    };
  }

  async function handleDecision(action: "approve" | "reject"): Promise<void> {
    setMutationStatus(null);
    setMutationError(null);
    form.clearErrors(["actorId", "reason"]);

    const parsed = decisionFormSchema.safeParse(form.getValues());
    if (!parsed.success) {
      applyValidationIssues(parsed.error.issues);
      return;
    }

    try {
      const result = await decisionMutation.mutateAsync({
        action,
        payload: toDecisionPayload(parsed.data)
      });
      setMutationStatus(t("pages.reviewQueue.statusUpdated", { status: result.review_status }));
    } catch (error) {
      setMutationError(resolveApiErrorMessage(error, t, t("pages.reviewQueue.patchStatusFailed")));
    }
  }

  async function handlePatchTransaction(): Promise<void> {
    setMutationStatus(null);
    setMutationError(null);
    form.clearErrors(["actorId", "reason", "transactionCorrectionsJson"]);

    const parsed = transactionPatchFormSchema.safeParse(form.getValues());
    if (!parsed.success) {
      applyValidationIssues(parsed.error.issues);
      return;
    }

    try {
      const result = await patchTransactionMutation.mutateAsync({
        ...toDecisionPayload(parsed.data),
        corrections: parsed.data.transactionCorrectionsJson
      });
      setMutationStatus(
        result.updated_fields.length > 0
          ? t("pages.reviewQueue.transactionUpdated", { fields: result.updated_fields.join(", ") })
          : t("pages.reviewQueue.transactionNoChanges")
      );
    } catch (error) {
      setMutationError(resolveApiErrorMessage(error, t, t("pages.reviewQueue.patchTransactionFailed")));
    }
  }

  async function handlePatchItem(): Promise<void> {
    setMutationStatus(null);
    setMutationError(null);
    form.clearErrors(["actorId", "reason", "selectedItemId", "itemCorrectionsJson"]);

    const parsed = itemPatchFormSchema.safeParse(form.getValues());
    if (!parsed.success) {
      applyValidationIssues(parsed.error.issues);
      return;
    }

    if (!detail || detail.items.length === 0) {
      setMutationError(t("pages.reviewQueue.noItems"));
      return;
    }

    const selectedItemExists = detail.items.some((item) => item.id === parsed.data.selectedItemId);
    if (!selectedItemExists) {
      const message = t("pages.reviewQueue.itemUnavailable");
      form.setError("selectedItemId", { message });
      setMutationError(message);
      return;
    }

    try {
      const result = await patchItemMutation.mutateAsync({
        itemId: parsed.data.selectedItemId,
        payload: {
          ...toDecisionPayload(parsed.data),
          corrections: parsed.data.itemCorrectionsJson
        }
      });
      setMutationStatus(
        result.updated_fields.length > 0
          ? t("pages.reviewQueue.itemUpdated", { fields: result.updated_fields.join(", ") })
          : t("pages.reviewQueue.itemNoChanges")
      );
    } catch (error) {
      setMutationError(resolveApiErrorMessage(error, t, t("pages.reviewQueue.patchItemFailed")));
    }
  }

  const highConfidenceItems = queueItems.filter(
    (item) => typeof item.transaction_confidence === "number" && item.transaction_confidence > 0.95
  );

  async function handleBatchApprove(): Promise<void> {
    setMutationStatus(null);
    setMutationError(null);
    if (highConfidenceItems.length === 0) {
      setMutationStatus(t("pages.reviewQueue.batchApproveNone"));
      return;
    }
    let count = 0;
    for (const item of highConfidenceItems) {
      try {
        await approveReviewDocument(item.document_id, { actor_id: "batch-ui" });
        count += 1;
      } catch {
        // continue
      }
    }
    setMutationStatus(t("pages.reviewQueue.batchApproveComplete", { count }));
    await queryClient.invalidateQueries({ queryKey: ["review-queue"] });
  }

  function applyFilters(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const next = new URLSearchParams(searchParams);
    next.set("status", statusFilter || "needs_review");
    next.set("threshold", String(parseThreshold(thresholdFilter, 0.85)));
    next.set("offset", "0");
    setSearchParams(next);
  }

  function movePage(delta: number): void {
    const nextOffset = Math.max(0, offset + delta);
    const next = new URLSearchParams(searchParams);
    next.set("offset", String(nextOffset));
    setSearchParams(next);
  }

  const linkSearch = useMemo(() => {
    const next = new URLSearchParams(searchParams);
    next.set("status", statusFromQuery);
    next.set("threshold", String(thresholdFromQuery));
    next.set("offset", String(offset));
    return next.toString();
  }, [offset, searchParams, statusFromQuery, thresholdFromQuery]);

  const drawerOpen = Boolean(documentId);

  function closeDetailDrawer(): void {
    navigate(`/review-queue?${linkSearch}`);
  }

  function handleDrawerOpenChange(open: boolean): void {
    if (!open) {
      closeDetailDrawer();
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t("pages.reviewQueue.title")} />

      <Card>
        <CardContent className="pt-6">
          <form className="grid gap-3 md:grid-cols-4" onSubmit={applyFilters}>
            <div className="space-y-2">
              <Label htmlFor="review-queue-status">{t("pages.reviewQueue.filter.status")}</Label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger id="review-queue-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="needs_review">{t("pages.reviewQueue.filter.needsReview")}</SelectItem>
                  <SelectItem value="approved">{t("pages.reviewQueue.filter.approved")}</SelectItem>
                  <SelectItem value="rejected">{t("pages.reviewQueue.filter.rejected")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="threshold">
                {t("pages.reviewQueue.filter.threshold")}
              </Label>
              <Input
                id="threshold"
                type="number"
                min={0}
                max={1}
                step="0.01"
                value={thresholdFilter}
                onChange={(event) => setThresholdFilter(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t("pages.reviewQueue.thresholdHint")}</p>
            </div>
            <div className="self-end flex gap-2">
              <Button type="submit">{t("pages.reviewQueue.applyFilters")}</Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setBatchApproveOpen(true)}
                disabled={highConfidenceItems.length === 0}
              >
                {t("pages.reviewQueue.batchApprove")}
              </Button>
            </div>
          </form>

      <ConfirmDialog
        open={batchApproveOpen}
        onOpenChange={setBatchApproveOpen}
        title={t("pages.reviewQueue.batchApproveConfirmTitle")}
        description={t("pages.reviewQueue.batchApproveConfirmDescription")}
        confirmLabel={t("pages.reviewQueue.batchApprove")}
        onConfirm={() => void handleBatchApprove()}
      />

      {queueQuery.error ? (
        <Alert variant="destructive" className="mt-4">
          <AlertTitle>{t("pages.reviewQueue.loadError")}</AlertTitle>
          <AlertDescription>
            {resolveApiErrorMessage(queueQuery.error, t, t("pages.reviewQueue.unknownError"))}
          </AlertDescription>
        </Alert>
      ) : null}

          <div className="app-section-divider mt-4 pt-4 md:hidden">
            <div className="divide-y divide-border/40">
            {queueItems.map((item) => (
              <div
                key={item.document_id}
                className="py-3 first:pt-0 last:pb-0 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{item.merchant_name || "-"}</span>
                  <span className="text-sm text-muted-foreground">
                    {formatDateTime(item.created_at)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="tabular-nums font-semibold">
                    {formatEurFromCents(item.total_gross_cents)}
                  </span>
                  <div className="flex flex-wrap gap-1">
                    <Badge className={cn("text-xs", reviewStatusClass(item.review_status))}>
                      {item.review_status.replace(/_/g, " ")}
                    </Badge>
                    <Badge className={cn("text-xs", ocrStatusClass(item.ocr_status))}>
                      {item.ocr_status}
                    </Badge>
                  </div>
                </div>
                <div className="flex items-center justify-between text-sm text-muted-foreground">
                  <span>{t("pages.reviewQueue.col.confidence")}: {item.transaction_confidence ?? "—"}</span>
                  <span>{t("pages.reviewQueue.col.ocr")}: {item.ocr_confidence ?? "—"}</span>
                </div>
                <Button variant="outline" size="sm" asChild className="w-full">
                  <Link to={`/review-queue/${item.document_id}?${linkSearch}`}>{t("pages.reviewQueue.open")}</Link>
                </Button>
              </div>
            ))}
            {queueItems.length === 0 ? (
              <EmptyState
                title={t("pages.reviewQueue.empty")}
                description={t("pages.reviewQueue.emptyDescription")}
                action={{ label: t("pages.reviewQueue.uploadReceipts"), href: "/imports/ocr" }}
              />
            ) : null}
            </div>
          </div>

          <div className="app-section-divider mt-4 pt-4 hidden md:block overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className={STICKY_TABLE_COLUMN_CLASS}>{t("pages.reviewQueue.col.created")}</TableHead>
                <TableHead>{t("pages.reviewQueue.col.merchant")}</TableHead>
                <TableHead>{t("pages.reviewQueue.col.total")}</TableHead>
                <TableHead>{t("pages.reviewQueue.col.confidence")}</TableHead>
                <TableHead>{t("pages.reviewQueue.col.ocr")}</TableHead>
                <TableHead>{t("common.status")}</TableHead>
                <TableHead>
                  <span className="sr-only">{t("pages.reviewQueue.col.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {queueItems.map((item) => (
                <TableRow key={item.document_id}>
                  <TableCell className={STICKY_TABLE_COLUMN_CLASS}>{formatDateTime(item.created_at)}</TableCell>
                  <TableCell>{item.merchant_name || "-"}</TableCell>
                  <TableCell className="tabular-nums">{formatEurFromCents(item.total_gross_cents)}</TableCell>
                  <TableCell className="tabular-nums">{item.transaction_confidence ?? "—"}</TableCell>
                  <TableCell className="tabular-nums">{item.ocr_confidence ?? "—"}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      <Badge className={cn("text-xs", reviewStatusClass(item.review_status))}>
                        {item.review_status.replace(/_/g, " ")}
                      </Badge>
                      <Badge className={cn("text-xs", ocrStatusClass(item.ocr_status))}>
                        {item.ocr_status}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Button variant="outline" size="sm" asChild>
                      <Link to={`/review-queue/${item.document_id}?${linkSearch}`}>{t("pages.reviewQueue.open")}</Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {queueItems.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7}>
                    <EmptyState
                      title={t("pages.reviewQueue.empty")}
                      description={t("pages.reviewQueue.emptyDescription")}
                      action={{ label: t("pages.reviewQueue.uploadReceipts"), href: "/imports/ocr" }}
                    />
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-muted-foreground">{paginationLabel}</p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={!canGoPrevious}
                onClick={() => movePage(-PAGE_SIZE)}
              >
                {t("common.previous")}
              </Button>
              <Button type="button" variant="outline" disabled={!canGoNext} onClick={() => movePage(PAGE_SIZE)}>
                {t("common.next")}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Sheet open={drawerOpen} onOpenChange={handleDrawerOpenChange}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-4xl">
          <SheetHeader className="space-y-2">
            <SheetTitle>{t("pages.reviewQueue.detail.title")}</SheetTitle>
            <SheetDescription>{t("pages.reviewQueue.detail.description")}</SheetDescription>
            <div>
              <Button variant="outline" size="sm" onClick={closeDetailDrawer}>
                {t("pages.reviewQueue.detail.back")}
              </Button>
            </div>
          </SheetHeader>

          <div className="mt-4 space-y-4 pb-6">
            {detailQuery.isPending || detailQuery.isFetching ? (
              <p className="text-sm text-muted-foreground">{t("pages.reviewQueue.detail.loading")}</p>
            ) : null}
            {detailQuery.error ? (
              <Alert variant="destructive">
                <AlertTitle>{t("pages.reviewQueue.detail.loadError")}</AlertTitle>
                <AlertDescription>
                  {resolveApiErrorMessage(detailQuery.error, t, t("pages.reviewQueue.unknownError"))}
                </AlertDescription>
              </Alert>
            ) : null}

            {detail ? (
              <>
                <div className="grid gap-x-8 gap-y-3 text-sm md:grid-cols-2">
                  <div>
                    <p className="font-medium">{t("pages.reviewQueue.detail.document")}</p>
                    <p className="text-muted-foreground">ID: {detail.document.id}</p>
                    <p className="text-muted-foreground">{t("pages.reviewQueue.detail.file")}: {detail.document.file_name || "-"}</p>
                    <p className="text-muted-foreground">{t("common.source")}: {detail.document.source_id || "-"}</p>
                    <p className="text-muted-foreground">{t("pages.reviewQueue.detail.ocrStatus")}: {detail.document.ocr_status}</p>
                    <p className="text-muted-foreground">{t("pages.reviewQueue.detail.reviewStatus")}: {detail.document.review_status}</p>
                    <p className="text-muted-foreground">{t("pages.reviewQueue.detail.ocrConfidence")}: {detail.document.ocr_confidence ?? "-"}</p>
                    <Button variant="link" className="h-auto p-0" asChild>
                      <Link to="/imports/ocr">{t("pages.reviewQueue.sourceUploadLink")}</Link>
                    </Button>
                  </div>
                  <div>
                    <p className="font-medium">{t("pages.reviewQueue.detail.transaction")}</p>
                    <p className="text-muted-foreground">ID: {detail.transaction.id}</p>
                    <p className="text-muted-foreground">{t("pages.reviewQueue.col.merchant")}: {detail.transaction.merchant_name || "-"}</p>
                    <p className="text-muted-foreground">{t("pages.reviewQueue.col.total")}: {formatEurFromCents(detail.transaction.total_gross_cents)}</p>
                    <p className="text-muted-foreground">{t("pages.reviewQueue.detail.purchased")}: {formatDateTime(detail.transaction.purchased_at)}</p>
                    <p className="text-muted-foreground">{t("pages.reviewQueue.col.confidence")}: {detail.transaction.confidence ?? "-"}</p>
                  </div>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="actor-id">{t("pages.reviewQueue.detail.actorId")}</Label>
                    <Input id="actor-id" {...form.register("actorId")} />
                    {form.formState.errors.actorId ? (
                      <p className="text-xs text-destructive">{form.formState.errors.actorId.message}</p>
                    ) : null}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reason">{t("pages.reviewQueue.detail.reason")}</Label>
                    <Input id="reason" {...form.register("reason")} />
                    {form.formState.errors.reason ? (
                      <p className="text-xs text-destructive">{form.formState.errors.reason.message}</p>
                    ) : null}
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    onClick={() => setApproveOpen(true)}
                    disabled={decisionMutation.isPending}
                  >
                    {t("pages.reviewQueue.approve")}
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    onClick={() => setRejectOpen(true)}
                    disabled={decisionMutation.isPending}
                  >
                    {t("pages.reviewQueue.reject")}
                  </Button>
                  <ConfirmDialog
                    open={approveOpen}
                    onOpenChange={setApproveOpen}
                    title={t("pages.reviewQueue.approveConfirmTitle")}
                    description={t("pages.reviewQueue.approveConfirmDescription")}
                    confirmLabel={t("pages.reviewQueue.approve")}
                    onConfirm={() => void handleDecision("approve")}
                  />
                  <ConfirmDialog
                    open={rejectOpen}
                    onOpenChange={setRejectOpen}
                    title={t("pages.reviewQueue.rejectConfirmTitle")}
                    description={t("pages.reviewQueue.rejectConfirmDescription")}
                    variant="destructive"
                    confirmLabel={t("pages.reviewQueue.reject")}
                    onConfirm={() => void handleDecision("reject")}
                  />
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2">
                    <p className="text-sm font-medium">{t("pages.reviewQueue.patch.transaction")}</p>
                    <Textarea aria-label={t("pages.reviewQueue.patch.transactionAria")} rows={6} {...form.register("transactionCorrectionsJson")} />
                    {form.formState.errors.transactionCorrectionsJson ? (
                      <p className="text-xs text-destructive">{form.formState.errors.transactionCorrectionsJson.message}</p>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void handlePatchTransaction()}
                      disabled={patchTransactionMutation.isPending}
                    >
                      {t("pages.reviewQueue.patch.transactionSubmit")}
                    </Button>
                  </div>

                  <div className="space-y-2">
                    <p className="text-sm font-medium">{t("pages.reviewQueue.patch.item")}</p>
                    <Label htmlFor="review-item-select">{t("pages.reviewQueue.patch.itemLabel")}</Label>
                    <Select
                      value={selectedItemId || EMPTY_ITEM_VALUE}
                      onValueChange={(value) => {
                        form.setValue("selectedItemId", value === EMPTY_ITEM_VALUE ? "" : value, {
                          shouldDirty: true,
                          shouldValidate: true
                        });
                      }}
                    >
                      <SelectTrigger id="review-item-select">
                        <SelectValue placeholder={t("pages.reviewQueue.patch.itemSelect")} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={EMPTY_ITEM_VALUE}>{t("pages.reviewQueue.patch.noItem")}</SelectItem>
                        {detail.items.map((item) => (
                          <SelectItem value={item.id} key={item.id}>
                            #{item.line_no} {item.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {form.formState.errors.selectedItemId ? (
                      <p className="text-xs text-destructive">{form.formState.errors.selectedItemId.message}</p>
                    ) : null}
                    <Textarea aria-label={t("pages.reviewQueue.patch.itemAria")} rows={6} {...form.register("itemCorrectionsJson")} />
                    {form.formState.errors.itemCorrectionsJson ? (
                      <p className="text-xs text-destructive">{form.formState.errors.itemCorrectionsJson.message}</p>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void handlePatchItem()}
                      disabled={patchItemMutation.isPending || !hasDetailItems || !selectedItemInDetail}
                    >
                      {t("pages.reviewQueue.patch.itemSubmit")}
                    </Button>
                  </div>
                </div>

                {mutationStatus ? (
                  <Alert>
                    <AlertTitle>{t("pages.reviewQueue.success")}</AlertTitle>
                    <AlertDescription>{mutationStatus}</AlertDescription>
                  </Alert>
                ) : null}
                {mutationError ? (
                  <Alert variant="destructive">
                    <AlertTitle>{t("pages.reviewQueue.mutationFailed")}</AlertTitle>
                    <AlertDescription>{mutationError}</AlertDescription>
                  </Alert>
                ) : null}

                <div className="rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Line</TableHead>
                        <TableHead>Name</TableHead>
                        <TableHead>Qty</TableHead>
                        <TableHead>Total</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Confidence</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detail.items.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell>{item.line_no}</TableCell>
                          <TableCell>{item.name}</TableCell>
                          <TableCell>{item.qty}</TableCell>
                          <TableCell>{formatEurFromCents(item.line_total_cents)}</TableCell>
                          <TableCell>{item.category || "-"}</TableCell>
                          <TableCell>{item.confidence ?? "-"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </>
            ) : null}
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
}
