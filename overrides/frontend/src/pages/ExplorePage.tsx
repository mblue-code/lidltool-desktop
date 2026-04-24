import { FormEvent, useMemo, useState } from "react";

import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createSavedQuery, deleteSavedQuery, fetchSavedQueries, runQuery, runQueryDsl } from "@/api/query";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/shared/PageHeader";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/i18n";

const DSL_TEMPLATES = {
  monthlyByCategory: 'SPEND net BY month, category\nWHERE date BETWEEN 2026-01-01..2026-12-31\nLIMIT 20',
  topProducts: 'SPEND gross BY product\nORDER BY gross DESC\nLIMIT 10',
  retailerComparison: 'SPEND net BY source_kind, month\nWHERE date BETWEEN 2026-01-01..2026-12-31\nLIMIT 24'
};

export function ExplorePage() {
  const queryClient = useQueryClient();
  const { locale, t, tText } = useI18n();
  const [metrics, setMetrics] = useState("net_total,discount_total");
  const [showSyntaxHelp, setShowSyntaxHelp] = useState(false);
  const [dimensions, setDimensions] = useState("month,source_kind");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [saveName, setSaveName] = useState("");
  const [dsl, setDsl] = useState(
    'SPEND net BY month, source_kind\nWHERE date BETWEEN 2026-01-01..2026-12-31 AND category = "Dairy"\nLIMIT 12'
  );
  const [result, setResult] = useState<Awaited<ReturnType<typeof runQuery>> | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [confirmDeleteQueryId, setConfirmDeleteQueryId] = useState<string | null>(null);

  const savedQuery = useQuery({
    queryKey: ["saved-queries"],
    queryFn: fetchSavedQueries
  });

  const runMutation = useMutation({
    mutationFn: runQuery,
    onSuccess: (data) => {
      setResult(data);
      setErrorText(null);
    },
    onError: (error) => {
      setErrorText(
        error instanceof Error
          ? error.message
          : locale === "de"
            ? "Abfrage konnte nicht ausgeführt werden."
            : "Failed to run query."
      );
    }
  });

  const saveMutation = useMutation({
    mutationFn: createSavedQuery,
    onSuccess: () => {
      setSaveName("");
      void queryClient.invalidateQueries({ queryKey: ["saved-queries"] });
    }
  });
  const dslMutation = useMutation({
    mutationFn: runQueryDsl,
    onSuccess: (data) => {
      setResult(data.result);
      setErrorText(null);
    },
    onError: (error) => {
      setErrorText(
        error instanceof Error
          ? error.message
          : locale === "de"
            ? "DSL-Abfrage konnte nicht ausgeführt werden."
            : "Failed to run DSL query."
      );
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSavedQuery,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["saved-queries"] });
    }
  });

  const parsedMetrics = useMemo(
    () =>
      metrics
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
    [metrics]
  );
  const parsedDimensions = useMemo(
    () =>
      dimensions
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
    [dimensions]
  );

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void runMutation.mutateAsync({
      metrics: parsedMetrics,
      dimensions: parsedDimensions,
      filters: {
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined
      },
      sort_by: parsedMetrics[0] ?? "net_total",
      sort_dir: "desc"
    });
  }

  function saveCurrentQuery(): void {
    if (!saveName.trim()) {
      return;
    }
    void saveMutation.mutateAsync({
      name: saveName.trim(),
      query_json: {
        metrics: parsedMetrics,
        dimensions: parsedDimensions,
        filters: {
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined
        }
      }
    });
  }

  function runDslQuery(): void {
    void dslMutation.mutateAsync(dsl);
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.explore")} />
      <form className="grid gap-3 md:grid-cols-4" onSubmit={submit}>
        <div className="space-y-1">
          <Label htmlFor="explore-metrics">{tText("Metrics (comma separated)")}</Label>
          <Input id="explore-metrics" value={metrics} onChange={(event) => setMetrics(event.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="explore-dimensions">{tText("Dimensions (comma separated)")}</Label>
          <Input
            id="explore-dimensions"
            value={dimensions}
            onChange={(event) => setDimensions(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="explore-date-from">{tText("From")}</Label>
          <Input id="explore-date-from" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="explore-date-to">{tText("To")}</Label>
          <Input id="explore-date-to" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </div>
        <div className="flex gap-2 md:col-span-4">
          <Button type="submit" disabled={runMutation.isPending}>
            {locale === "de" ? "Abfrage ausführen" : "Run query"}
          </Button>
          <Input
            placeholder={tText("Saved query name")}
            value={saveName}
            onChange={(event) => setSaveName(event.target.value)}
          />
          <Button type="button" variant="outline" onClick={saveCurrentQuery} disabled={saveMutation.isPending}>
            {locale === "de" ? "Abfrage speichern" : "Save query"}
          </Button>
        </div>
      </form>

      <Card>
        <CardHeader>
          <CardTitle>{tText("DSL Mode")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setDsl(DSL_TEMPLATES.monthlyByCategory)}>
              {t("pages.explore.template.monthlyByCategory")}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setDsl(DSL_TEMPLATES.topProducts)}>
              {t("pages.explore.template.topProducts")}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setDsl(DSL_TEMPLATES.retailerComparison)}>
              {t("pages.explore.template.retailerComparison")}
            </Button>
          </div>
          <Label htmlFor="explore-dsl">Query DSL</Label>
          <Textarea id="explore-dsl" value={dsl} onChange={(event) => setDsl(event.target.value)} rows={5} />
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={runDslQuery} disabled={dslMutation.isPending}>
              {locale === "de" ? "DSL ausführen" : "Run DSL"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setShowSyntaxHelp((v) => !v)}
            >
              {showSyntaxHelp ? t("pages.explore.syntaxHelp.hide") : t("pages.explore.syntaxHelp.show")}
            </Button>
          </div>
          {showSyntaxHelp ? (
            <div className="app-soft-surface space-y-1 rounded-md border p-3 text-xs">
              <p className="font-medium">{locale === "de" ? "DSL-Syntaxreferenz" : "DSL Syntax Reference"}</p>
              <p>
                <code>SPEND net|gross BY dim1, dim2</code> {locale === "de" ? "— Ausgaben aggregieren" : "— aggregate spending"}
              </p>
              <p>
                <code>WHERE date BETWEEN YYYY-MM-DD..YYYY-MM-DD</code> {locale === "de" ? "— Datumsfilter" : "— date filter"}
              </p>
              <p>
                <code>AND category = "Dairy"</code> {locale === "de" ? "— Feldfilter" : "— field filter"}
              </p>
              <p>
                <code>ORDER BY metric ASC|DESC</code> {locale === "de" ? "— Ergebnisse sortieren" : "— sort results"}
              </p>
              <p>
                <code>LIMIT n</code> {locale === "de" ? "— Zeilen begrenzen" : "— limit rows returned"}
              </p>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {errorText ? (
        <Alert variant="destructive">
          <AlertTitle>{tText("Query error")}</AlertTitle>
          <AlertDescription>{errorText}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{tText("Result")}</CardTitle>
        </CardHeader>
        <CardContent>
          {result === null ? (
            <p className="text-sm text-muted-foreground">
              {locale === "de" ? "Führen Sie eine Abfrage aus, um Ergebnisse zu sehen." : "Run a query to see results."}
            </p>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                <span>{t("pages.explore.previewRows").replace("{count}", String(result.rows.length))}</span>
                <span>{t("pages.explore.detailFilter")}: {result.drilldown_token}</span>
              </div>
              <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    {result.columns.map((column) => (
                      <TableHead key={column}>{column}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.rows.map((row, index) => (
                    <TableRow key={`${index}-${row.join("-")}`}>
                      {row.map((value, valueIndex) => (
                        <TableCell key={`${index}-${valueIndex}`}>{String(value)}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{locale === "de" ? "Gespeicherte Abfragen" : "Saved Queries"}</CardTitle>
        </CardHeader>
        <CardContent>
          {savedQuery.data?.items.length ? (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{tText("Name")}</TableHead>
                  <TableHead>{tText("Preset")}</TableHead>
                  <TableHead>{tText("Actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {savedQuery.data.items.map((queryItem) => (
                  <TableRow key={queryItem.query_id}>
                    <TableCell>{queryItem.name}</TableCell>
                    <TableCell>{queryItem.is_preset ? tText("Yes") : tText("No")}</TableCell>
                    <TableCell>
                      {!queryItem.is_preset ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setConfirmDeleteQueryId(queryItem.query_id)}
                          >
                          {tText("Delete")}
                        </Button>
                      ) : (
                        "-"
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">{tText("No saved queries yet.")}</p>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmDeleteQueryId !== null}
        onOpenChange={(open) => { if (!open) setConfirmDeleteQueryId(null); }}
        title={t("pages.explore.confirmDeleteTitle")}
        description={t("pages.explore.confirmDeleteDescription")}
        variant="destructive"
        confirmLabel={t("common.delete")}
        onConfirm={() => { if (confirmDeleteQueryId) void deleteMutation.mutateAsync(confirmDeleteQueryId); }}
      />
    </section>
  );
}
