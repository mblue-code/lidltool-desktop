import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronLeft, Copy, ExternalLink } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";

import { transactionDetailQueryOptions } from "@/app/queries";
import { useAccessScope } from "@/app/scope-provider";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CategoryPresentation,
  CATEGORY_OPTIONS,
  formatCategoryOptionLabel
} from "@/components/shared/CategoryPresentation";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { FINANCE_CATEGORY_OPTIONS, financeCategoryLabel } from "@/lib/category-presentation";
import {
  TransactionOverrideRequest,
  buildDocumentPreviewUrl,
  patchTransactionItemAllocation,
  patchTransactionWorkspace,
  patchTransactionOverrides
} from "../api/transactions";
import { formatDateTime, formatEurFromCents } from "../utils/format";

const NO_ITEM_VALUE = "__no_item__";
const NO_CATEGORY_VALUE = "__no_category__";

const overrideFormSchema = z.object({
  mode: z.enum(["local", "global", "both"]),
  actorId: z.string().trim().max(120),
  reason: z.string().trim().max(280),
  merchantName: z.string().trim().max(280),
  financeCategoryId: z.string().trim().max(120),
  itemId: z.string(),
  itemCategory: z.string().trim().max(120)
});

type OverrideFormValues = z.infer<typeof overrideFormSchema>;

function supportsInlinePreview(mimeType: string): boolean {
  const normalized = mimeType.toLowerCase();
  return (
    normalized === "application/pdf" ||
    normalized.startsWith("image/") ||
    normalized.startsWith("text/")
  );
}

function workspaceLabel(workspaceKind?: string | null, sharedGroupId?: string | null): string {
  if (workspaceKind === "shared_group" || sharedGroupId) {
    return sharedGroupId ? `Shared group (${sharedGroupId})` : "Shared group";
  }
  return "Personal";
}

export function TransactionDetailPage() {
  const { transactionId } = useParams();
  const { locale, t } = useI18n();
  const { workspace } = useAccessScope();
  const txId = transactionId ?? null;
  const [mutationStatus, setMutationStatus] = useState<string | null>(null);
  const [sharingStatus, setSharingStatus] = useState<string | null>(null);
  const [previewFailed, setPreviewFailed] = useState<boolean>(false);
  const [rawCopyStatus, setRawCopyStatus] = useState<string | null>(null);
  const lastResetTransactionIdRef = useRef<string | null>(null);

  const {
    data,
    error,
    isPending,
    isFetching,
    refetch
  } = useQuery({
    ...transactionDetailQueryOptions(txId ?? ""),
    enabled: Boolean(txId)
  });
  const detail = data?.detail ?? null;
  const history = data?.history ?? null;
  const loading = isPending || isFetching;
  const errorMessage = error ? resolveApiErrorMessage(error, t, t("pages.transactionDetail.loadError")) : null;
  const isOwner = detail?.transaction.is_owner !== false;
  const currentAllocationMode = detail?.transaction.allocation_mode ?? "personal";
  const canTargetSharedWorkspace = workspace.kind === "shared-group";

  const overridesMutation = useMutation({
    mutationFn: ({
      transactionId,
      payload
    }: {
      transactionId: string;
      payload: TransactionOverrideRequest;
    }) => patchTransactionOverrides(transactionId, payload)
  });
  const sharingMutation = useMutation({
    mutationFn: ({
      transactionId,
      allocationMode,
      sharedGroupId
    }: {
      transactionId: string;
      allocationMode: "personal" | "shared_receipt" | "split_items";
      sharedGroupId?: string;
    }) =>
      patchTransactionWorkspace(transactionId, {
        allocation_mode: allocationMode,
        shared_group_id: sharedGroupId
      })
  });
  const itemSharingMutation = useMutation({
    mutationFn: ({
      transactionId,
      itemId,
      shared
    }: {
      transactionId: string;
      itemId: string;
      shared: boolean;
    }) => patchTransactionItemAllocation(transactionId, itemId, shared)
  });

  const form = useForm<OverrideFormValues>({
    resolver: zodResolver(overrideFormSchema),
    defaultValues: {
      mode: "local",
      actorId: "ledger-ui",
      reason: "",
      merchantName: "",
      financeCategoryId: "",
      itemId: "",
      itemCategory: ""
    }
  });

  const selectedItemId = form.watch("itemId");
  const selectedMode = form.watch("mode");
  const selectedDocument = detail?.documents[0] ?? null;
  const previewUrl = useMemo(
    () => (selectedDocument ? buildDocumentPreviewUrl(selectedDocument.id) : null),
    [selectedDocument]
  );
  const documentMimeType = selectedDocument?.mime_type ?? "";
  const canPreviewInline = documentMimeType ? supportsInlinePreview(documentMimeType) : false;
  const useImagePreview = documentMimeType.toLowerCase().startsWith("image/");
  const selectedItem = detail?.items.find((candidate) => candidate.id === selectedItemId) ?? null;

  useEffect(() => {
    setPreviewFailed(false);
  }, [selectedDocument?.id]);

  useEffect(() => {
    if (!detail) {
      return;
    }
    const shouldResetStatuses = lastResetTransactionIdRef.current !== detail.transaction.id;
    form.reset({
      mode: "local",
      actorId: "ledger-ui",
      reason: "",
      merchantName: detail.transaction.merchant_name ?? "",
      financeCategoryId: detail.transaction.finance_category_id ?? "",
      itemId: "",
      itemCategory: ""
    });
    if (shouldResetStatuses) {
      setMutationStatus(null);
      setSharingStatus(null);
      lastResetTransactionIdRef.current = detail.transaction.id;
    }
  }, [detail, form]);

  if (!txId) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t("pages.transactionDetail.missingId")}</AlertTitle>
      </Alert>
    );
  }

  async function submitOverrides(values: OverrideFormValues): Promise<void> {
    if (!detail || !txId) {
      return;
    }

    form.clearErrors();
    setMutationStatus(null);

    const transactionCorrections: Record<string, unknown> = {};
    const normalizedMerchant = values.merchantName.trim();
    const previousMerchant = (detail.transaction.merchant_name ?? "").trim();
    if (normalizedMerchant !== previousMerchant) {
      transactionCorrections.merchant_name = normalizedMerchant || null;
    }
    const normalizedFinanceCategory = values.financeCategoryId.trim();
    const previousFinanceCategory = (detail.transaction.finance_category_id ?? "").trim();
    if (normalizedFinanceCategory !== previousFinanceCategory) {
      transactionCorrections.finance_category_id = normalizedFinanceCategory || null;
    }

    const itemCorrections: Array<{ item_id: string; corrections: Record<string, unknown> }> = [];
    if (values.itemCategory.trim() && !values.itemId) {
      form.setError("itemId", {
        message: t("pages.transactionDetail.override.itemRequired")
      });
      return;
    }
    if (values.itemId) {
      const item = detail.items.find((candidate) => candidate.id === values.itemId);
      if (!item) {
        form.setError("itemId", {
          message: t("pages.transactionDetail.override.itemUnavailable")
        });
        return;
      }
      const normalizedCategory = values.itemCategory.trim();
      const previousCategory = (item.category ?? "").trim();
      if (normalizedCategory !== previousCategory) {
        itemCorrections.push({
          item_id: item.id,
          corrections: {
            category: normalizedCategory || null
          }
        });
      }
    }

    if (Object.keys(transactionCorrections).length === 0 && itemCorrections.length === 0) {
      setMutationStatus(t("pages.transactionDetail.override.noChanges"));
      return;
    }

    if (
      values.itemId &&
      itemCorrections.length > 0 &&
      (values.mode === "global" || values.mode === "both") &&
      selectedItem
    ) {
      const confirmed = window.confirm(
        t("pages.transactionDetail.override.confirmGlobalCategory", {
          itemName: selectedItem.name,
          sourceName: detail.transaction.source_id
        })
      );
      if (!confirmed) {
        setMutationStatus(t("pages.transactionDetail.override.globalCancelled"));
        return;
      }
    }

    setMutationStatus(t("pages.transactionDetail.override.applying"));

    try {
      await overridesMutation.mutateAsync({
        transactionId: txId,
        payload: {
          actor_id: values.actorId.trim() || undefined,
          reason: values.reason.trim() || undefined,
          mode: values.mode,
          transaction_corrections: transactionCorrections,
          item_corrections: itemCorrections
        }
      });
      void refetch();
      setMutationStatus(t("pages.transactionDetail.override.applied"));
    } catch (err) {
      setMutationStatus(resolveApiErrorMessage(err, t, t("pages.transactionDetail.override.failed")));
    }
  }

  async function copyRawPayload(): Promise<void> {
    if (!detail) {
      return;
    }
    const payload = JSON.stringify(detail.transaction.raw_payload ?? {}, null, 2);
    if (!navigator.clipboard) {
      setRawCopyStatus(t("pages.transactionDetail.clipboardUnavailable"));
      return;
    }
    try {
      await navigator.clipboard.writeText(payload);
      setRawCopyStatus(t("pages.transactionDetail.copySuccess"));
    } catch {
      setRawCopyStatus(t("pages.transactionDetail.copyFailed"));
    }
  }

  async function updateTransactionWorkspace(
    allocationMode: "personal" | "shared_receipt" | "split_items"
  ): Promise<void> {
    if (!detail || !txId || !isOwner) {
      return;
    }
    setSharingStatus(t("pages.transactionDetail.allocationUpdating"));
    try {
      await sharingMutation.mutateAsync({
        transactionId: txId,
        allocationMode,
        sharedGroupId: workspace.kind === "shared-group" ? workspace.groupId : undefined
      });
      void refetch();
      setSharingStatus(t("pages.transactionDetail.allocationUpdated"));
    } catch (error) {
      setSharingStatus(resolveApiErrorMessage(error, t, t("pages.transactionDetail.allocationFailed")));
    }
  }

  async function updateItemAllocation(itemId: string, shared: boolean): Promise<void> {
    if (!detail || !txId || !isOwner) {
      return;
    }
    setSharingStatus(t("pages.transactionDetail.itemAllocationUpdating"));
    try {
      await itemSharingMutation.mutateAsync({ transactionId: txId, itemId, shared });
      void refetch();
      setSharingStatus(t("pages.transactionDetail.itemAllocationUpdated"));
    } catch (error) {
      setSharingStatus(resolveApiErrorMessage(error, t, t("pages.transactionDetail.itemAllocationFailed")));
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-2 text-sm">
        <Link to="/receipts" className="text-muted-foreground hover:text-foreground">
          {t("pages.transactionDetail.breadcrumb.receipts")}
        </Link>
        <ChevronLeft className="h-3 w-3 rotate-180 text-muted-foreground" />
        <span className="font-medium">{t("pages.transactionDetail.title")} #{txId}</span>
      </div>

      {loading ? <Skeleton className="h-44 w-full" /> : null}
      {errorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>{t("pages.transactionDetail.loadError")}</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}

      {detail ? (
        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList className="grid h-auto w-full grid-cols-2 gap-1 p-1 md:grid-cols-5">
            <TabsTrigger value="overview">{t("pages.transactionDetail.tab.overview")}</TabsTrigger>
            <TabsTrigger value="items">{t("pages.transactionDetail.tab.items")}</TabsTrigger>
            <TabsTrigger value="discounts">{t("pages.transactionDetail.tab.discounts")}</TabsTrigger>
            <TabsTrigger value="history">{t("pages.transactionDetail.tab.history")}</TabsTrigger>
            <TabsTrigger value="raw">{t("pages.transactionDetail.tab.raw")}</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>{t("pages.transactionDetail.card.transaction")}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <p>
                    <strong>{t("pages.transactionDetail.field.id")}:</strong> {detail.transaction.id}
                  </p>
                  <p>
                    <strong>{t("pages.transactionDetail.field.merchant")}:</strong> {detail.transaction.merchant_name || "-"}
                  </p>
                  <p>
                    <strong>{t("pages.transactionDetail.field.source")}:</strong> {detail.transaction.source_id}
                  </p>
                  <p>
                    <strong>{t("pages.transactionDetail.field.owner")}:</strong>{" "}
                    {detail.transaction.owner_display_name || detail.transaction.owner_username || t("pages.transactionDetail.unknownOwner")}
                  </p>
                  <p>
                    <strong>Workspace:</strong>{" "}
                    {workspaceLabel(
                      detail.transaction.workspace_kind,
                      detail.transaction.shared_group_id
                    )}
                  </p>
                  <p>
                    <strong>{t("pages.transactionDetail.field.purchased")}:</strong> {formatDateTime(detail.transaction.purchased_at)}
                  </p>
                  <p>
                    <strong>{t("pages.transactionDetail.field.total")}:</strong> {formatEurFromCents(detail.transaction.total_gross_cents)}
                  </p>
                  <p>
                    <strong>{t("pages.transactionDetail.field.discountTotal")}:</strong> {formatEurFromCents(detail.transaction.discount_total_cents ?? 0)}
                  </p>
                  <p>
                    <strong>{t("pages.transactionDetail.field.financeCategory")}:</strong>{" "}
                    {financeCategoryLabel(detail.transaction.finance_category_id, t)}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>{t("pages.transactionDetail.documentPreview")}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {!selectedDocument ? (
                    <p className="text-sm text-muted-foreground">{t("pages.transactionDetail.noDocument")}</p>
                  ) : null}

                  {selectedDocument && previewUrl && canPreviewInline && !previewFailed ? (
                    useImagePreview ? (
                      <img
                        className="max-h-[420px] w-full rounded-md border object-contain"
                        src={previewUrl}
                        alt={selectedDocument.file_name || t("pages.transactionDetail.documentAlt")}
                        onError={() => setPreviewFailed(true)}
                      />
                    ) : (
                      <iframe
                        className="min-h-[420px] w-full rounded-md border"
                        src={previewUrl}
                        title={t("pages.transactionDetail.documentAlt")}
                        onError={() => setPreviewFailed(true)}
                      />
                    )
                  ) : null}

                  {selectedDocument && previewUrl && (!canPreviewInline || previewFailed) ? (
                    <div className="space-y-3">
                      <Alert>
                        <AlertTitle>{t("pages.transactionDetail.inlineUnavailable")}</AlertTitle>
                        <AlertDescription>
                          {t("pages.transactionDetail.inlineUnavailableDescription", {
                            mimeType: documentMimeType || "unknown"
                          })}{" "}
                          <code>{documentMimeType || "unknown"}</code>
                        </AlertDescription>
                      </Alert>
                      <Button asChild variant="outline" size="sm">
                        <a href={previewUrl} target="_blank" rel="noreferrer">
                          <ExternalLink className="mr-1 h-4 w-4" />
                          {t("pages.transactionDetail.openDocument")}
                        </a>
                      </Button>
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle>{t("pages.transactionDetail.workspaceOwnership")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="transaction-allocation-mode">{t("pages.transactionDetail.receiptAllocationMode")}</Label>
                  <Select
                    value={currentAllocationMode}
                    onValueChange={(value) =>
                      void updateTransactionWorkspace(
                        value as "personal" | "shared_receipt" | "split_items"
                      )
                    }
                    disabled={
                      !isOwner ||
                      sharingMutation.isPending ||
                      itemSharingMutation.isPending ||
                      (!canTargetSharedWorkspace && currentAllocationMode === "personal")
                    }
                  >
                    <SelectTrigger id="transaction-allocation-mode" className="w-[240px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="personal">{t("pages.transactionDetail.allocation.personal")}</SelectItem>
                      {canTargetSharedWorkspace || currentAllocationMode !== "personal" ? (
                        <>
                          <SelectItem value="shared_receipt">
                            {t("pages.transactionDetail.allocation.sharedReceipt")}
                          </SelectItem>
                          <SelectItem value="split_items">
                            {t("pages.transactionDetail.allocation.splitItems")}
                          </SelectItem>
                        </>
                      ) : null}
                    </SelectContent>
                  </Select>
                  {!canTargetSharedWorkspace && currentAllocationMode === "personal" ? (
                    <p className="text-xs text-muted-foreground">
                      {t("pages.transactionDetail.switchWorkspaceHint")}
                    </p>
                  ) : null}
                  {!isOwner ? (
                    <p className="text-xs text-muted-foreground">
                      {t("pages.transactionDetail.readOnly")}
                    </p>
                  ) : null}
                </div>

                {currentAllocationMode === "split_items" ? (
                  <div className="space-y-2">
                    <p className="text-sm font-medium">{t("pages.transactionDetail.allocatedItems")}</p>
                    {detail.items.length === 0 ? (
                      <p className="text-sm text-muted-foreground">{t("pages.transactionDetail.noAllocatableItems")}</p>
                    ) : (
                      <div className="space-y-2">
                        {detail.items.map((item) => (
                          <label key={item.id} className="flex items-center justify-between gap-3 py-1">
                            <span className="text-sm">
                              {item.name}{" "}
                              <span className="text-muted-foreground">
                                ({formatEurFromCents(item.line_total_cents)})
                              </span>
                            </span>
                            <Checkbox
                              checked={Boolean(item.is_shared_allocation)}
                              disabled={!isOwner || itemSharingMutation.isPending || !canTargetSharedWorkspace}
                              onCheckedChange={(checked) =>
                                void updateItemAllocation(item.id, Boolean(checked))
                              }
                            />
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}

                {sharingStatus ? <p className="text-sm text-muted-foreground">{sharingStatus}</p> : null}

                <div className="app-section-divider space-y-3">
                  <h3 className="font-semibold leading-none tracking-tight">{t("pages.transactionDetail.overrides")}</h3>
                </div>
                {!isOwner ? (
                  <p className="mb-3 text-sm text-muted-foreground">
                    {t("pages.transactionDetail.overridesDisabled")}
                  </p>
                ) : null}
                <form
                  className="grid gap-3 md:grid-cols-3"
                  onSubmit={form.handleSubmit((values) => void submitOverrides(values))}
                >
                  <div className="space-y-2">
                    <Label htmlFor="override-mode">{t("pages.transactionDetail.override.mode")}</Label>
                    <Select
                      value={form.watch("mode")}
                      onValueChange={(value) => {
                        form.setValue("mode", value as OverrideFormValues["mode"], {
                          shouldDirty: true,
                          shouldValidate: true
                        });
                      }}
                    >
                      <SelectTrigger id="override-mode">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="local">{t("pages.transactionDetail.override.mode.local")}</SelectItem>
                        <SelectItem value="global">{t("pages.transactionDetail.override.mode.global")}</SelectItem>
                        <SelectItem value="both">{t("pages.transactionDetail.override.mode.both")}</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      {t(`pages.transactionDetail.override.modeHelp.${selectedMode}`)}
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="actor-id">{t("pages.transactionDetail.override.actorId")}</Label>
                    <Input id="actor-id" {...form.register("actorId")} />
                    {form.formState.errors.actorId ? (
                      <p className="text-xs text-destructive">{form.formState.errors.actorId.message}</p>
                    ) : null}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="reason">{t("pages.transactionDetail.override.reason")}</Label>
                    <Input id="reason" {...form.register("reason")} />
                    {form.formState.errors.reason ? (
                      <p className="text-xs text-destructive">{form.formState.errors.reason.message}</p>
                    ) : null}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="merchant-name">{t("pages.transactionDetail.override.merchantName")}</Label>
                    <Input id="merchant-name" {...form.register("merchantName")} />
                    {form.formState.errors.merchantName ? (
                      <p className="text-xs text-destructive">{form.formState.errors.merchantName.message}</p>
                    ) : null}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="finance-category">{t("pages.transactionDetail.override.financeCategory")}</Label>
                    <Select
                      value={form.watch("financeCategoryId") || NO_CATEGORY_VALUE}
                      onValueChange={(value) => {
                        form.setValue("financeCategoryId", value === NO_CATEGORY_VALUE ? "" : value, {
                          shouldDirty: true,
                          shouldValidate: true
                        });
                      }}
                    >
                      <SelectTrigger id="finance-category" aria-label={t("pages.transactionDetail.override.financeCategory")}>
                        <SelectValue placeholder={t("pages.transactionDetail.override.selectFinanceCategory")} />
                      </SelectTrigger>
                      <SelectContent className="max-h-80">
                        <SelectItem value={NO_CATEGORY_VALUE}>{t("pages.transactionDetail.override.clearFinanceCategory")}</SelectItem>
                        {FINANCE_CATEGORY_OPTIONS.map((category) => (
                          <SelectItem value={category} key={category}>
                            {financeCategoryLabel(category, t)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {form.formState.errors.financeCategoryId ? (
                      <p className="text-xs text-destructive">{form.formState.errors.financeCategoryId.message}</p>
                    ) : null}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="override-item">{t("pages.transactionDetail.override.item")}</Label>
                    <Select
                      value={selectedItemId || NO_ITEM_VALUE}
                      onValueChange={(value) => {
                        const itemId = value === NO_ITEM_VALUE ? "" : value;
                        form.setValue("itemId", itemId, {
                          shouldDirty: true,
                          shouldValidate: true
                        });

                        const item = detail.items.find((candidate) => candidate.id === itemId);
                        form.setValue("itemCategory", item?.category || "", {
                          shouldDirty: true,
                          shouldValidate: true
                        });
                      }}
                    >
                      <SelectTrigger
                        id="override-item"
                        aria-label={t("pages.transactionDetail.override.item")}
                      >
                        <SelectValue placeholder={t("pages.transactionDetail.override.selectItem")} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NO_ITEM_VALUE}>{t("pages.transactionDetail.override.noItemChange")}</SelectItem>
                        {detail.items.map((item) => (
                          <SelectItem value={item.id} key={item.id}>
                            {item.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {form.formState.errors.itemId ? (
                      <p className="text-xs text-destructive">{form.formState.errors.itemId.message}</p>
                    ) : null}
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="item-category">{t("pages.transactionDetail.override.itemCategory")}</Label>
                    <Select
                      value={form.watch("itemCategory") || NO_CATEGORY_VALUE}
                      onValueChange={(value) => {
                        form.setValue("itemCategory", value === NO_CATEGORY_VALUE ? "" : value, {
                          shouldDirty: true,
                          shouldValidate: true
                        });
                      }}
                      disabled={!selectedItemId}
                    >
                      <SelectTrigger id="item-category" aria-label={t("pages.transactionDetail.override.itemCategory")}>
                        <SelectValue placeholder={t("pages.transactionDetail.override.selectCategory")} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NO_CATEGORY_VALUE}>{t("pages.transactionDetail.override.clearCategory")}</SelectItem>
                        {CATEGORY_OPTIONS.map((category) => (
                          <SelectItem value={category} key={category}>
                            {formatCategoryOptionLabel(category, locale)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {form.formState.errors.itemCategory ? (
                      <p className="text-xs text-destructive">{form.formState.errors.itemCategory.message}</p>
                    ) : null}
                  </div>

                  {selectedItem && (selectedMode === "global" || selectedMode === "both") ? (
                    <div className="space-y-2 md:col-span-3">
                      <Alert>
                        <AlertTitle>{t("pages.transactionDetail.override.globalScopeTitle")}</AlertTitle>
                        <AlertDescription>
                          {t("pages.transactionDetail.override.globalScopeDescription", {
                            itemName: selectedItem.name,
                            sourceName: detail.transaction.source_id
                          })}
                        </AlertDescription>
                      </Alert>
                    </div>
                  ) : null}

                  <Button type="submit" className="self-end" disabled={!isOwner || overridesMutation.isPending}>
                    {overridesMutation.isPending ? t("pages.transactionDetail.override.applying") : t("pages.transactionDetail.override.submit")}
                  </Button>
                </form>

                {mutationStatus ? (
                  <p className="mt-3 text-sm text-muted-foreground">{mutationStatus}</p>
                ) : null}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="items">
            <Card>
              <CardHeader>
                <CardTitle>{t("pages.transactionDetail.lineItems")}</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>#</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Workspace</TableHead>
                      <TableHead>Qty</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className="tabular-nums">{item.line_no}</TableCell>
                        <TableCell>{item.name}</TableCell>
                        <TableCell>
                          {workspaceLabel(
                            item.shared_group_id ? "shared_group" : detail.transaction.workspace_kind,
                            item.shared_group_id
                          )}
                        </TableCell>
                        <TableCell className="tabular-nums">{item.qty}</TableCell>
                        <TableCell>
                          <CategoryPresentation category={item.category} locale={locale} />
                        </TableCell>
                        <TableCell className="tabular-nums">{formatEurFromCents(item.line_total_cents)}</TableCell>
                      </TableRow>
                    ))}
                    {detail.items.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6}>{t("pages.transactionDetail.lineItem.none")}</TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="discounts">
            <Card>
              <CardHeader>
                <CardTitle>{t("pages.transactionDetail.discountsTitle")}</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Kind</TableHead>
                      <TableHead>Scope</TableHead>
                      <TableHead>Label</TableHead>
                      <TableHead>Amount</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {detail.discounts.map((discount) => (
                      <TableRow key={discount.id}>
                        <TableCell>{discount.kind}</TableCell>
                        <TableCell>{discount.scope}</TableCell>
                        <TableCell>{discount.source_label || "—"}</TableCell>
                        <TableCell className="tabular-nums">{formatEurFromCents(discount.amount_cents)}</TableCell>
                      </TableRow>
                    ))}
                    {detail.discounts.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4}>{t("pages.transactionDetail.discounts.none")}</TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="history">
            <Card>
              <CardHeader>
                <CardTitle>{t("pages.transactionDetail.historyTitle")}</CardTitle>
              </CardHeader>
              <CardContent>
                {!history || history.events.length === 0 ? (
                  <p className="text-sm text-muted-foreground">{t("pages.transactionDetail.history.none")}</p>
                ) : (
                  <ol className="relative space-y-3 border-l-2 border-border pl-5">
                    {history.events.map((event) => (
                      <li key={event.id} className="relative">
                        <span className="absolute -left-[1.3125rem] top-1 h-2.5 w-2.5 rounded-full border-2 border-primary bg-background" />
                        <p className="text-sm font-medium">{event.action}</p>
                        <p className="text-xs text-muted-foreground">{formatDateTime(event.created_at)}</p>
                      </li>
                    ))}
                  </ol>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="raw">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>{t("pages.transactionDetail.rawTitle")}</CardTitle>
                <Button type="button" variant="outline" size="sm" onClick={() => void copyRawPayload()}>
                  <Copy className="mr-1 h-4 w-4" />
                  {t("pages.transactionDetail.copyJson")}
                </Button>
              </CardHeader>
              <CardContent className="space-y-2">
                <pre className="max-h-[520px] overflow-auto rounded-md border bg-muted/50 p-4 font-mono text-xs text-foreground">
                  {JSON.stringify(detail.transaction.raw_payload || {}, null, 2)}
                </pre>
                {rawCopyStatus ? <p className="text-xs text-muted-foreground">{rawCopyStatus}</p> : null}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      ) : null}
    </section>
  );
}
