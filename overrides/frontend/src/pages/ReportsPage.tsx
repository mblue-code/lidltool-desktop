import { useQuery } from "@tanstack/react-query";
import { Download, FileBarChart2, FileJson, FileText, ReceiptText } from "lucide-react";

import { fetchReportTemplates } from "@/api/reports";
import { useDateRangeContext } from "@/app/date-range-context";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/i18n";

function downloadFile(filename: string, contentType: string, content: string) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function collectCsvRows(value: unknown, path = "report"): Array<Record<string, unknown>> {
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => collectCsvRows(item, `${path}.${index + 1}`));
  }
  if (!value || typeof value !== "object") {
    return [{ section: path, value }];
  }

  const record = value as Record<string, unknown>;
  const scalarRow: Record<string, unknown> = { section: path };
  const rows: Array<Record<string, unknown>> = [];

  for (const [key, child] of Object.entries(record)) {
    if (Array.isArray(child)) {
      rows.push(...child.flatMap((item, index) => collectCsvRows(item, `${path}.${key}.${index + 1}`)));
    } else if (child && typeof child === "object") {
      rows.push(...collectCsvRows(child, `${path}.${key}`));
    } else {
      scalarRow[key] = child;
    }
  }

  if (Object.keys(scalarRow).length > 1) {
    rows.unshift(scalarRow);
  }
  return rows;
}

function reportPayloadToCsv(payload: unknown): string {
  const rows = collectCsvRows(payload);
  const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return [
    headers.map(csvCell).join(","),
    ...rows.map((row) => headers.map((header) => csvCell(row[header])).join(","))
  ].join("\n");
}

function localizeTemplate(template: { slug: string; title: string; description: string }, locale: "en" | "de"): { title: string; description: string } {
  if (locale !== "de") {
    return { title: template.title, description: template.description };
  }

  switch (template.slug) {
    case "monthly-overview":
      return {
        title: "Monatsübersicht",
        description: "Ausgaben, Kategorien und Händlerkonzentration auf einen Blick."
      };
    case "grocery-review":
      return {
        title: "Einkaufsübersicht",
        description: "Warenkorngröße, Kategorienverteilung und aktuelle Einkaufsbelege."
      };
    case "budget-health":
      return {
        title: "Budgetstatus",
        description: "Aktueller Monatsstatus mit Kontext zu Zielen und wiederkehrenden Rechnungen."
      };
    default:
      return { title: template.title, description: template.description };
  }
}

export function ReportsPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const { locale } = useI18n();
  const copy = locale === "de"
    ? {
        title: "Berichte",
	        description: "Exportiere das aktuelle Finanzbild als strukturierte Berichtsnutzlasten und halte fertige Vorlagen nah an den Arbeitsoberflächen.",
	        templateSlug: "Vorlagen-Slug",
	        exportCsv: "CSV exportieren",
	        exportJson: "JSON-Rohdaten",
	        formatNote: "CSV ist die nutzerfreundliche Exportansicht. PDF und Excel sind noch nicht verfügbar; JSON bleibt als Rohdatenformat für Automatisierung erhalten."
	      }
	    : {
        title: "Reports",
	        description: "Export the current finance picture as structured report payloads and keep ready-made templates close to the working surfaces.",
	        templateSlug: "Template slug",
	        exportCsv: "Export CSV",
	        exportJson: "Raw JSON",
	        formatNote: "CSV is the user-facing export view. PDF and Excel are not available yet; JSON remains available as raw data for automation."
	      };
  const templatesQuery = useQuery({
    queryKey: ["reports-page", fromDate, toDate],
    queryFn: () => fetchReportTemplates(fromDate, toDate)
  });
  const templates = templatesQuery.data?.templates ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title={copy.title}
        description={copy.description}
      />

      <div className="grid gap-4 xl:grid-cols-3">
        {templates.map((template, index) => {
          const localizedTemplate = localizeTemplate(template, locale);
          return (
            <Card key={template.slug} className="app-dashboard-surface border-border/60">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  {index === 0 ? <FileBarChart2 className="h-4 w-4" /> : index === 1 ? <ReceiptText className="h-4 w-4" /> : <FileJson className="h-4 w-4" />}
                  {localizedTemplate.title}
                </CardTitle>
                <CardDescription>{localizedTemplate.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
	                <p className="text-sm text-muted-foreground">
	                  {copy.templateSlug}: <span className="font-medium text-foreground">{template.slug}</span>
	                </p>
	                <p className="text-sm leading-6 text-muted-foreground">{copy.formatNote}</p>
	                <div className="flex flex-wrap gap-2">
	                  <Button
	                    type="button"
	                    onClick={() =>
	                      downloadFile(
	                        `${template.slug}.csv`,
	                        "text/csv;charset=utf-8",
	                        reportPayloadToCsv(template.payload)
	                      )
	                    }
	                  >
	                    <FileText className="mr-2 h-4 w-4" />
	                    {copy.exportCsv}
	                  </Button>
	                  <Button
	                    type="button"
	                    variant="outline"
	                    onClick={() =>
	                      downloadFile(
	                        `${template.slug}.json`,
	                        "application/json",
	                        JSON.stringify(template.payload, null, 2)
	                      )
	                    }
	                  >
	                    <Download className="mr-2 h-4 w-4" />
	                    {copy.exportJson}
	                  </Button>
	                </div>
	              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
