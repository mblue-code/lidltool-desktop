import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronLeft, Copy, ExternalLink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";

import { transactionDetailQueryOptions } from "@/app/queries";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import {
  TransactionOverrideRequest,
  buildDocumentPreviewUrl,
  patchTransactionItemSharing,
  patchTransactionSharing,
  patchTransactionOverrides
} from "../api/transactions";
import { formatDateTime, formatEurFromCents } from "../utils/format";

const NO_ITEM_VALUE = "__no_item__";

const overrideFormSchema = z.object({
  mode: z.enum(["local", "global", "both"]),
  actorId: z.string().trim().max(120),
  reason: z.string().trim().max(280),
  merchantName: z.string().trim().max(280),
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

export function TransactionDetailPage() {
  const { transactionId } = useParams();
  const { t } = useI18n();
  const txId = transactionId ?? null;
  const [mutationStatus, setMutationStatus] = useState<string | null>(null);
  const [sharingStatus, setSharingStatus] = useState<string | null>(null);
  const [previewFailed, setPreviewFailed] = useState<boolean>(false);
  const [rawCopyStatus, setRawCopyStatus] = useState<string | null>(null);

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
  const currentFamilyShareMode = detail?.transaction.family_share_mode ?? "inherit";

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
    mutationFn: ({ transactionId, mode }: { transactionId: string; mode: "receipt" | "items" | "none" | "inherit" }) =>
      patchTransactionSharing(transactionId, mode)
  });
  const itemSharingMutation = useMutation({
    mutationFn: ({
      transactionId,
      itemId,
      familyShared
    }: {
      transactionId: string;
      itemId: string;
      familyShared: boolean;
    }) => patchTransactionItemSharing(transactionId, itemId, familyShared)
  });

  const form = useForm<OverrideFormValues>({
    resolver: zodResolver(overrideFormSchema),
    defaultValues: {
      mode: "local",
      actorId: "ledger-ui",
      reason: "",
      merchantName: "",
      itemId: "",
      itemCategory: ""
    }
  });

  const selectedItemId = form.watch("itemId");
  const selectedDocument = detail?.documents[0] ?? null;
  const previewUrl = useMemo(
    () => (selectedDocument ? buildDocumentPreviewUrl(selectedDocument.id) : null),
    [selectedDocument]
  );
  const documentMimeType = selectedDocument?.mime_type ?? "";
  const canPreviewInline = documentMimeType ? supportsInlinePreview(documentMimeType) : false;
  const useImagePreview = documentMimeType.toLowerCase().startsWith("image/");

  useEffect(() => {
    setPreviewFailed(false);
  }, [selectedDocument?.id]);

  useEffect(() => {
    if (!detail) {
      return;
    }
    form.reset({
      mode: "local",
      actorId: "ledger-ui",
      reason: "",
      merchantName: detail.transaction.merchant_name ?? "",
      itemId: "",
      itemCategory: ""
    });
    setMutationStatus(null);
    setSharingStatus(null);
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
      await refetch();
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

  async function updateTransactionSharing(mode: "receipt" | "items" | "none" | "inherit"): Promise<void> {
    if (!detail || !txId || !isOwner) {
      return;
    }
    setSharingStatus(t("pages.transactionDetail.sharingUpdating"));
    try {
      await sharingMutation.mutateAsync({ transactionId: txId, mode });
      await refetch();
      setSharingStatus(t("pages.transactionDetail.sharingUpdated"));
    } catch (error) {
      setSharingStatus(resolveApiErrorMessage(error, t, t("pages.transactionDetail.sharingFailed")));
    }
  }

  async function updateItemSharing(itemId: string, familyShared: boolean): Promise<void> {
    if (!detail || !txId || !isOwner) {
      return;
    }
    setSharingStatus(t("pages.transactionDetail.itemSharingUpdating"));
    try {
      await itemSharingMutation.mutateAsync({ transactionId: txId, itemId, familyShared });
      await refetch();
      setSharingStatus(t("pages.transactionDetail.itemSharingUpdated"));
    } catch (error) {
      setSharingStatus(resolveApiErrorMessage(error, t, t("pages.transactionDetail.itemSharingFailed")));
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between rounded-lg border bg-card p-4">
        <h2 className="text-lg font-semibold">{t("pages.transactionDetail.title")}</h2>
        <Button asChild variant="ghost" size="sm" className="-ml-2">
          <Link to="/transactions">
            <ChevronLeft className="mr-1 h-4 w-4" />
            {t("pages.transactionDetail.back")}
          </Link>
        </Button>
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
                    <strong>{t("pages.transactionDetail.field.purchased")}:</strong> {formatDateTime(detail.transaction.purchased_at)}
                  </p>
                  <p>
                    <strong>{t("pages.transactionDetail.field.total")}:</strong> {formatEurFromCents(detail.transaction.total_gross_cents)}
                  </p>
                  <p>
                    <strong>{t("pages.transactionDetail.field.discountTotal")}:</strong> {formatEurFromCents(detail.transaction.discount_total_cents ?? 0)}
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
                <CardTitle>{t("pages.transactionDetail.familySharing")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="family-share-mode">{t("pages.transactionDetail.receiptSharingMode")}</Label>
                  <Select
                    value={currentFamilyShareMode}
                    onValueChange={(value) =>
                      void updateTransactionSharing(value as "receipt" | "items" | "none" | "inherit")
                    }
                    disabled={!isOwner || sharingMutation.isPending || itemSharingMutation.isPending}
                  >
                    <SelectTrigger id="family-share-mode" className="w-[240px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="inherit">{t("pages.transactionDetail.share.inherit")}</SelectItem>
                      <SelectItem value="none">{t("pages.transactionDetail.share.none")}</SelectItem>
                      <SelectItem value="receipt">{t("pages.transactionDetail.share.receipt")}</SelectItem>
                      <SelectItem value="items">{t("pages.transactionDetail.share.items")}</SelectItem>
                    </SelectContent>
                  </Select>
                  {!isOwner ? (
                    <p className="text-xs text-muted-foreground">
                      {t("pages.transactionDetail.readOnly")}
                    </p>
                  ) : null}
                </div>

                {currentFamilyShareMode === "items" ? (
                  <div className="space-y-2">
                    <p className="text-sm font-medium">{t("pages.transactionDetail.sharedItems")}</p>
                    {detail.items.length === 0 ? (
                      <p className="text-sm text-muted-foreground">{t("pages.transactionDetail.noShareableItems")}</p>
                    ) : (
                      <div className="space-y-2 rounded-md border p-3">
                        {detail.items.map((item) => (
                          <label key={item.id} className="flex items-center justify-between gap-3">
                            <span className="text-sm">
                              {item.name}{" "}
                              <span className="text-muted-foreground">
                                ({formatEurFromCents(item.line_total_cents)})
                              </span>
                            </span>
                            <Checkbox
                              checked={Boolean(item.family_shared)}
                              disabled={!isOwner || itemSharingMutation.isPending}
                              onCheckedChange={(checked) =>
                                void updateItemSharing(item.id, Boolean(checked))
                              }
                            />
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                ) : null}

                {sharingStatus ? <p className="text-sm text-muted-foreground">{sharingStatus}</p> : null}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t("pages.transactionDetail.overrides")}</CardTitle>
              </CardHeader>
              <CardContent>
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
                      <SelectTrigger id="override-item">
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
                    <Input id="item-category" {...form.register("itemCategory")} />
                    {form.formState.errors.itemCategory ? (
                      <p className="text-xs text-destructive">{form.formState.errors.itemCategory.message}</p>
                    ) : null}
                  </div>

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
                        <TableCell className="tabular-nums">{item.qty}</TableCell>
                        <TableCell>{item.category || "—"}</TableCell>
                        <TableCell className="tabular-nums">{formatEurFromCents(item.line_total_cents)}</TableCell>
                      </TableRow>
                    ))}
                    {detail.items.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5}>{t("pages.transactionDetail.lineItem.none")}</TableCell>
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
