import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Loader2, ReceiptText, ScanLine, Store } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { createManualTransaction, ManualTransactionResponse } from "@/api/transactions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/shared/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";

type ManualFormValues = {
  purchasedAt: string;
  merchantName: string;
  totalGrossAmount: string;
  itemName: string;
  itemTotalAmount: string;
  idempotencyKey: string;
};

function defaultPurchasedAtValue(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function parseEuroAmountToCents(raw: string): number | null {
  const normalized = raw.trim().replace(",", ".");
  if (!normalized) {
    return null;
  }
  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  return Math.round(parsed * 100);
}

export function ManualImportPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [manualErrorMessage, setManualErrorMessage] = useState<string | null>(null);
  const [manualSuccess, setManualSuccess] = useState<ManualTransactionResponse | null>(null);
  const [showAdvancedFields, setShowAdvancedFields] = useState(false);
  const [manualFormValues, setManualFormValues] = useState<ManualFormValues>({
    purchasedAt: defaultPurchasedAtValue(),
    merchantName: "",
    totalGrossAmount: "",
    itemName: "",
    itemTotalAmount: "",
    idempotencyKey: ""
  });

  const manualMutation = useMutation({
    mutationFn: createManualTransaction,
    onSuccess: async (result) => {
      setManualSuccess(result);
      setManualErrorMessage(null);
      setManualFormValues({
        purchasedAt: defaultPurchasedAtValue(),
        merchantName: "",
        totalGrossAmount: "",
        itemName: "",
        itemTotalAmount: "",
        idempotencyKey: ""
      });
      await queryClient.invalidateQueries({ queryKey: ["transactions"] });
    }
  });

  async function submitManualTransaction(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setManualErrorMessage(null);
    setManualSuccess(null);

    const purchasedDate = new Date(manualFormValues.purchasedAt);
    if (Number.isNaN(purchasedDate.valueOf())) {
      setManualErrorMessage(t("pages.transactions.manual.invalidDate"));
      return;
    }

    const merchantName = manualFormValues.merchantName.trim();
    if (!merchantName) {
      setManualErrorMessage(t("pages.transactions.manual.merchantRequired"));
      return;
    }

    const totalGrossCents = parseEuroAmountToCents(manualFormValues.totalGrossAmount);
    if (totalGrossCents === null) {
      setManualErrorMessage(t("pages.transactions.manual.totalInvalid"));
      return;
    }

    const itemName = manualFormValues.itemName.trim();
    const itemTotalRaw = manualFormValues.itemTotalAmount.trim();
    if ((itemName && !itemTotalRaw) || (!itemName && itemTotalRaw)) {
      setManualErrorMessage(t("pages.transactions.manual.itemPairRequired"));
      return;
    }

    let itemTotalCents: number | null = null;
    if (itemTotalRaw) {
      itemTotalCents = parseEuroAmountToCents(itemTotalRaw);
      if (itemTotalCents === null) {
        setManualErrorMessage(t("pages.transactions.manual.itemTotalInvalid"));
        return;
      }
    }

    try {
      await manualMutation.mutateAsync({
        purchased_at: purchasedDate.toISOString(),
        merchant_name: merchantName,
        total_gross_cents: totalGrossCents,
        idempotency_key: manualFormValues.idempotencyKey.trim() || undefined,
        items:
          itemName && itemTotalCents !== null
            ? [
                {
                  name: itemName,
                  line_total_cents: itemTotalCents,
                  qty: 1,
                  line_no: 1
                }
              ]
            : undefined
      });
    } catch (mutationError) {
      setManualErrorMessage(resolveApiErrorMessage(mutationError, t, t("pages.transactions.manual.createFailed")));
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader title={t("nav.item.addReceipt")} description={t("pages.manualImport.description")} />

      <Tabs defaultValue="upload" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="upload">{t("pages.manualImport.tabs.upload")}</TabsTrigger>
          <TabsTrigger value="manual">{t("pages.manualImport.tabs.manual")}</TabsTrigger>
          <TabsTrigger value="connect">{t("pages.manualImport.tabs.connect")}</TabsTrigger>
        </TabsList>

        <TabsContent value="upload" className="space-y-4">
          <section className="grid gap-4 rounded-2xl border bg-card p-6 md:grid-cols-[1.6fr_1fr]">
            <div className="space-y-4">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <ScanLine className="h-5 w-5" />
              </div>
              <div className="space-y-2">
                <h2 className="text-xl font-semibold">{t("pages.manualImport.upload.title")}</h2>
                <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                  {t("pages.manualImport.upload.description")}
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button asChild className="gap-2">
                  <Link to="/imports/ocr">
                    {t("pages.manualImport.upload.action")}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline">
                  <Link to="/review-queue">{t("pages.manualImport.upload.secondaryAction")}</Link>
                </Button>
              </div>
            </div>

            <div className="space-y-3 rounded-2xl border bg-muted/20 p-4">
              <p className="text-sm font-medium">{t("pages.manualImport.upload.bestFor")}</p>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li>{t("pages.manualImport.upload.support.one")}</li>
                <li>{t("pages.manualImport.upload.support.two")}</li>
                <li>{t("pages.manualImport.upload.support.three")}</li>
              </ul>
            </div>
          </section>
        </TabsContent>

        <TabsContent value="manual" className="space-y-4">
          <section className="space-y-5 rounded-2xl border bg-card p-6">
            <div className="space-y-2">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <ReceiptText className="h-5 w-5" />
              </div>
              <h2 className="text-xl font-semibold">{t("pages.manualImport.manual.title")}</h2>
              <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                {t("pages.manualImport.manual.description")}
              </p>
            </div>

            <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" onSubmit={submitManualTransaction}>
              <div className="space-y-2">
                <Label htmlFor="manual-purchased-at">{t("pages.transactions.manual.purchasedAt")}</Label>
                <Input
                  id="manual-purchased-at"
                  type="datetime-local"
                  value={manualFormValues.purchasedAt}
                  onChange={(event) =>
                    setManualFormValues((previous) => ({
                      ...previous,
                      purchasedAt: event.target.value
                    }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="manual-merchant">{t("pages.transactions.manual.merchant")}</Label>
                <Input
                  id="manual-merchant"
                  value={manualFormValues.merchantName}
                  placeholder={t("pages.manualImport.manual.merchantPlaceholder")}
                  onChange={(event) =>
                    setManualFormValues((previous) => ({
                      ...previous,
                      merchantName: event.target.value
                    }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="manual-total-amount">{t("pages.transactions.manual.totalCents")}</Label>
                <Input
                  id="manual-total-amount"
                  inputMode="decimal"
                  value={manualFormValues.totalGrossAmount}
                  placeholder="12.34"
                  onChange={(event) =>
                    setManualFormValues((previous) => ({
                      ...previous,
                      totalGrossAmount: event.target.value
                    }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="manual-item-name">{t("pages.transactions.manual.itemName")}</Label>
                <Input
                  id="manual-item-name"
                  value={manualFormValues.itemName}
                  placeholder={t("pages.manualImport.manual.itemPlaceholder")}
                  onChange={(event) =>
                    setManualFormValues((previous) => ({
                      ...previous,
                      itemName: event.target.value
                    }))
                  }
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="manual-item-total-amount">{t("pages.transactions.manual.itemTotalCents")}</Label>
                <Input
                  id="manual-item-total-amount"
                  inputMode="decimal"
                  value={manualFormValues.itemTotalAmount}
                  placeholder="3.99"
                  onChange={(event) =>
                    setManualFormValues((previous) => ({
                      ...previous,
                      itemTotalAmount: event.target.value
                    }))
                  }
                />
              </div>

              <div className="flex items-end">
                <Button type="button" variant="outline" onClick={() => setShowAdvancedFields((current) => !current)}>
                  {t(showAdvancedFields ? "pages.manualImport.manual.hideAdvanced" : "pages.manualImport.manual.showAdvanced")}
                </Button>
              </div>

              {showAdvancedFields ? (
                <div className="space-y-2 md:col-span-2 xl:col-span-2">
                  <Label htmlFor="manual-idempotency-key">{t("pages.transactions.manual.idempotencyKey")}</Label>
                  <Input
                    id="manual-idempotency-key"
                    value={manualFormValues.idempotencyKey}
                    onChange={(event) =>
                      setManualFormValues((previous) => ({
                        ...previous,
                        idempotencyKey: event.target.value
                      }))
                    }
                  />
                </div>
              ) : null}

              <div className="md:col-span-2 xl:col-span-4 flex flex-wrap items-center gap-3">
                <Button type="submit" disabled={manualMutation.isPending}>
                  {manualMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      {t("pages.transactions.manual.saving")}
                    </>
                  ) : (
                    t("pages.transactions.manual.submit")
                  )}
                </Button>
                <Button asChild variant="outline">
                  <Link to="/receipts">{t("pages.manualImport.manual.viewReceipts")}</Link>
                </Button>
              </div>
            </form>

            {manualErrorMessage ? (
              <Alert variant="destructive">
                <AlertTitle>{t("pages.transactions.manual.errorTitle")}</AlertTitle>
                <AlertDescription>{manualErrorMessage}</AlertDescription>
              </Alert>
            ) : null}

            {manualSuccess ? (
              <Alert>
                <CheckCircle2 className="h-4 w-4" />
                <AlertTitle>{t("pages.transactions.manual.savedTitle")}</AlertTitle>
                <AlertDescription className="space-y-1">
                  <p>
                    {manualSuccess.reused ? t("pages.transactions.manual.reused") : t("pages.transactions.manual.created")}{" "}
                    {t("common.source")}: <span className="font-medium">{manualSuccess.source_id}</span>
                  </p>
                  <Button asChild variant="link" className="h-auto p-0">
                    <Link to={`/transactions/${manualSuccess.transaction_id}`}>{t("pages.transactions.manual.openDetails")}</Link>
                  </Button>
                </AlertDescription>
              </Alert>
            ) : null}
          </section>
        </TabsContent>

        <TabsContent value="connect" className="space-y-4">
          <section className="grid gap-4 rounded-2xl border bg-card p-6 md:grid-cols-[1.6fr_1fr]">
            <div className="space-y-4">
              <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                <Store className="h-5 w-5" />
              </div>
              <div className="space-y-2">
                <h2 className="text-xl font-semibold">{t("pages.manualImport.connect.title")}</h2>
                <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                  {t("pages.manualImport.connect.description")}
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button asChild className="gap-2">
                  <Link to="/connectors">
                    {t("pages.manualImport.connect.action")}
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild variant="outline">
                  <Link to="/sources">{t("pages.manualImport.connect.secondaryAction")}</Link>
                </Button>
              </div>
            </div>

            <div className="space-y-3 rounded-2xl border bg-muted/20 p-4">
              <p className="text-sm font-medium">{t("pages.manualImport.connect.supportTitle")}</p>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li>Lidl</li>
                <li>Amazon</li>
                <li>REWE</li>
                <li>Kaufland</li>
              </ul>
            </div>
          </section>
        </TabsContent>
      </Tabs>
    </section>
  );
}
