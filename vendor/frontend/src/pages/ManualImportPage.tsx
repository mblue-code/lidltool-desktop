import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2 } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { createManualTransaction, ManualTransactionResponse } from "@/api/transactions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type ManualFormValues = {
  purchasedAt: string;
  merchantName: string;
  totalGrossCents: string;
  itemName: string;
  itemTotalCents: string;
  idempotencyKey: string;
};

function defaultPurchasedAtValue(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export function ManualImportPage() {
  const queryClient = useQueryClient();
  const [manualErrorMessage, setManualErrorMessage] = useState<string | null>(null);
  const [manualSuccess, setManualSuccess] = useState<ManualTransactionResponse | null>(null);
  const [manualFormValues, setManualFormValues] = useState<ManualFormValues>({
    purchasedAt: defaultPurchasedAtValue(),
    merchantName: "",
    totalGrossCents: "",
    itemName: "",
    itemTotalCents: "",
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
        totalGrossCents: "",
        itemName: "",
        itemTotalCents: "",
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
      setManualErrorMessage("Purchased at must be a valid date and time.");
      return;
    }
    const merchantName = manualFormValues.merchantName.trim();
    if (!merchantName) {
      setManualErrorMessage("Merchant is required.");
      return;
    }
    const totalGrossCents = Number(manualFormValues.totalGrossCents);
    if (!Number.isInteger(totalGrossCents) || totalGrossCents < 0) {
      setManualErrorMessage("Total cents must be a non-negative integer.");
      return;
    }

    const itemName = manualFormValues.itemName.trim();
    const itemTotalRaw = manualFormValues.itemTotalCents.trim();
    if ((itemName && !itemTotalRaw) || (!itemName && itemTotalRaw)) {
      setManualErrorMessage("Item name and item total cents must be filled together.");
      return;
    }

    let itemTotalCents: number | null = null;
    if (itemTotalRaw) {
      const parsed = Number(itemTotalRaw);
      if (!Number.isInteger(parsed) || parsed < 0) {
        setManualErrorMessage("Item total cents must be a non-negative integer.");
        return;
      }
      itemTotalCents = parsed;
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
      setManualErrorMessage(
        mutationError instanceof Error ? mutationError.message : "Failed to create transaction."
      );
    }
  }

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Manual Import</CardTitle>
          <CardDescription>
            Add one-off purchases from merchants where you do not want a full connector.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="grid gap-3 md:grid-cols-6" onSubmit={submitManualTransaction}>
            <div className="space-y-2">
              <Label htmlFor="manual-purchased-at">Purchased at</Label>
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
              <Label htmlFor="manual-merchant">Merchant</Label>
              <Input
                id="manual-merchant"
                value={manualFormValues.merchantName}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    merchantName: event.target.value
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="manual-total-cents">Total cents</Label>
              <Input
                id="manual-total-cents"
                type="number"
                min={0}
                value={manualFormValues.totalGrossCents}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    totalGrossCents: event.target.value
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="manual-item-name">Item (optional)</Label>
              <Input
                id="manual-item-name"
                value={manualFormValues.itemName}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    itemName: event.target.value
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="manual-item-total-cents">Item total cents (optional)</Label>
              <Input
                id="manual-item-total-cents"
                type="number"
                min={0}
                value={manualFormValues.itemTotalCents}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    itemTotalCents: event.target.value
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="manual-idempotency-key">Idempotency key (optional)</Label>
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
            <Button type="submit" className="md:col-span-6 md:w-fit" disabled={manualMutation.isPending}>
              {manualMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                "Add manual transaction"
              )}
            </Button>
          </form>

          {manualErrorMessage ? (
            <Alert variant="destructive">
              <AlertTitle>Manual ingestion failed</AlertTitle>
              <AlertDescription>{manualErrorMessage}</AlertDescription>
            </Alert>
          ) : null}

          {manualSuccess ? (
            <Alert>
              <CheckCircle2 className="h-4 w-4" />
              <AlertTitle>Transaction saved</AlertTitle>
              <AlertDescription className="space-y-1">
                <p>
                  {manualSuccess.reused ? "Existing transaction reused." : "New transaction created."} Source:{" "}
                  <span className="font-medium">{manualSuccess.source_id}</span>
                </p>
                <Button asChild variant="link" className="h-auto p-0">
                  <Link to={`/transactions/${manualSuccess.transaction_id}`}>Open transaction details</Link>
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/imports/ocr">Go to OCR import</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/connectors">Go to connectors</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
