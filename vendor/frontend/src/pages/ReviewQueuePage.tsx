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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
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
  const { documentId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  const statusFromQuery = searchParams.get("status") || "needs_review";
  const thresholdFromQuery = parseThreshold(searchParams.get("threshold"), 0.85);
  const offset = parsePositiveInt(searchParams.get("offset"), 0);

  const [statusFilter, setStatusFilter] = useState<string>(statusFromQuery);
  const [thresholdFilter, setThresholdFilter] = useState<string>(thresholdFromQuery.toString());
  const [mutationStatus, setMutationStatus] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

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
    total === 0 ? "Showing 0 of 0" : `Showing ${offset + 1}-${Math.min(offset + PAGE_SIZE, total)} of ${total}`;

  const decisionMutation = useMutation({
    mutationFn: async ({
      action,
      payload
    }: {
      action: "approve" | "reject";
      payload: ReviewDecisionRequest;
    }) => {
      if (!documentId) {
        throw new Error("Select a document before reviewing.");
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
        throw new Error("Select a document before editing.");
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
        throw new Error("Select a document before editing.");
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
    if (action === "reject") {
      const confirmed = window.confirm("Reject this document from the review queue?");
      if (!confirmed) {
        return;
      }
    }

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
      setMutationStatus(`Review status updated to "${result.review_status}".`);
    } catch (error) {
      setMutationError(error instanceof Error ? error.message : "Failed to update review status");
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
          ? `Transaction fields updated: ${result.updated_fields.join(", ")}`
          : "No transaction changes were applied."
      );
    } catch (error) {
      setMutationError(error instanceof Error ? error.message : "Failed to patch transaction");
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
      setMutationError("No items are available for this document.");
      return;
    }

    const selectedItemExists = detail.items.some((item) => item.id === parsed.data.selectedItemId);
    if (!selectedItemExists) {
      const message = "Selected item is no longer available. Choose a current item and retry.";
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
          ? `Item fields updated: ${result.updated_fields.join(", ")}`
          : "No item changes were applied."
      );
    } catch (error) {
      setMutationError(error instanceof Error ? error.message : "Failed to patch item");
    }
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
      <Card>
        <CardHeader>
          <CardTitle>Review Queue</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-4" onSubmit={applyFilters}>
            <div className="space-y-2">
              <Label htmlFor="review-queue-status">Status</Label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger id="review-queue-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="needs_review">Needs review</SelectItem>
                  <SelectItem value="approved">Approved</SelectItem>
                  <SelectItem value="rejected">Rejected</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="threshold">Confidence threshold</Label>
              <Input
                id="threshold"
                type="number"
                min={0}
                max={1}
                step="0.01"
                value={thresholdFilter}
                onChange={(event) => setThresholdFilter(event.target.value)}
              />
            </div>
            <div className="self-end">
              <Button type="submit">Apply filters</Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {queueQuery.error ? (
        <Alert variant="destructive">
          <AlertTitle>Failed to load queue</AlertTitle>
          <AlertDescription>
            {queueQuery.error instanceof Error ? queueQuery.error.message : "Unknown error"}
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Created</TableHead>
                <TableHead>Merchant</TableHead>
                <TableHead>Total</TableHead>
                <TableHead>Confidence</TableHead>
                <TableHead>OCR</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {queueItems.map((item) => (
                <TableRow key={item.document_id}>
                  <TableCell>{formatDateTime(item.created_at)}</TableCell>
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
                      <Link to={`/review-queue/${item.document_id}?${linkSearch}`}>Open</Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {queueItems.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7}>No documents matched the selected filters.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-muted-foreground">{paginationLabel}</p>
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

      <Sheet open={drawerOpen} onOpenChange={handleDrawerOpenChange}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-4xl">
          <SheetHeader className="space-y-2">
            <SheetTitle>Review Detail</SheetTitle>
            <SheetDescription>
              Review OCR output, apply corrections, and approve or reject the document.
            </SheetDescription>
            <div>
              <Button variant="outline" size="sm" onClick={closeDetailDrawer}>
                Back to queue
              </Button>
            </div>
          </SheetHeader>

          <div className="mt-4 space-y-4 pb-6">
            {detailQuery.isPending || detailQuery.isFetching ? (
              <p className="text-sm text-muted-foreground">Loading review detail...</p>
            ) : null}
            {detailQuery.error ? (
              <Alert variant="destructive">
                <AlertTitle>Failed to load detail</AlertTitle>
                <AlertDescription>
                  {detailQuery.error instanceof Error ? detailQuery.error.message : "Unknown error"}
                </AlertDescription>
              </Alert>
            ) : null}

            {detail ? (
              <>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-lg border p-4 text-sm">
                    <p className="font-medium">Document</p>
                    <p>ID: {detail.document.id}</p>
                    <p>File: {detail.document.file_name || "-"}</p>
                    <p>Source: {detail.document.source_id || "-"}</p>
                    <p>OCR status: {detail.document.ocr_status}</p>
                    <p>Review status: {detail.document.review_status}</p>
                    <p>OCR confidence: {detail.document.ocr_confidence ?? "-"}</p>
                  </div>
                  <div className="rounded-lg border p-4 text-sm">
                    <p className="font-medium">Transaction</p>
                    <p>ID: {detail.transaction.id}</p>
                    <p>Merchant: {detail.transaction.merchant_name || "-"}</p>
                    <p>Total: {formatEurFromCents(detail.transaction.total_gross_cents)}</p>
                    <p>Purchased: {formatDateTime(detail.transaction.purchased_at)}</p>
                    <p>Confidence: {detail.transaction.confidence ?? "-"}</p>
                  </div>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="actor-id">Actor ID</Label>
                    <Input id="actor-id" {...form.register("actorId")} />
                    {form.formState.errors.actorId ? (
                      <p className="text-xs text-destructive">{form.formState.errors.actorId.message}</p>
                    ) : null}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reason">Reason</Label>
                    <Input id="reason" {...form.register("reason")} />
                    {form.formState.errors.reason ? (
                      <p className="text-xs text-destructive">{form.formState.errors.reason.message}</p>
                    ) : null}
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    onClick={() => void handleDecision("approve")}
                    disabled={decisionMutation.isPending}
                  >
                    Approve
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    onClick={() => void handleDecision("reject")}
                    disabled={decisionMutation.isPending}
                  >
                    Reject
                  </Button>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-2 rounded-lg border p-4">
                    <p className="text-sm font-medium">Patch transaction</p>
                    <Textarea aria-label="Transaction corrections JSON" rows={6} {...form.register("transactionCorrectionsJson")} />
                    {form.formState.errors.transactionCorrectionsJson ? (
                      <p className="text-xs text-destructive">{form.formState.errors.transactionCorrectionsJson.message}</p>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void handlePatchTransaction()}
                      disabled={patchTransactionMutation.isPending}
                    >
                      Apply transaction patch
                    </Button>
                  </div>

                  <div className="space-y-2 rounded-lg border p-4">
                    <p className="text-sm font-medium">Patch item</p>
                    <Label htmlFor="review-item-select">Item</Label>
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
                        <SelectValue placeholder="Select item" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={EMPTY_ITEM_VALUE}>No item selected</SelectItem>
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
                    <Textarea aria-label="Item corrections JSON" rows={6} {...form.register("itemCorrectionsJson")} />
                    {form.formState.errors.itemCorrectionsJson ? (
                      <p className="text-xs text-destructive">{form.formState.errors.itemCorrectionsJson.message}</p>
                    ) : null}
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void handlePatchItem()}
                      disabled={patchItemMutation.isPending || !hasDetailItems || !selectedItemInDetail}
                    >
                      Apply item patch
                    </Button>
                  </div>
                </div>

                {mutationStatus ? (
                  <Alert>
                    <AlertTitle>Success</AlertTitle>
                    <AlertDescription>{mutationStatus}</AlertDescription>
                  </Alert>
                ) : null}
                {mutationError ? (
                  <Alert variant="destructive">
                    <AlertTitle>Mutation failed</AlertTitle>
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
