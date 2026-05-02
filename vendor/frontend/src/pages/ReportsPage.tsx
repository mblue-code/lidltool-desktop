import { startTransition, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, ChevronDown } from "lucide-react";
import { toPng } from "html-to-image";

import { fetchDashboardYears } from "@/api/dashboard";
import { fetchMerchantSummary } from "@/api/merchants";
import { fetchReportPatterns, fetchReportSankey, fetchReportTemplates, buildWorkspaceComparisonSankey, type ReportSankeyBreakdown, type ReportSankeyMode, type ReportSankeyResponse } from "@/api/reports";
import { fetchSharedGroups } from "@/api/shared-groups";
import { useAccessScope } from "@/app/scope-provider";
import { fetchSources } from "@/api/sources";
import { useDateRangeContext, type DateRangePreset } from "@/app/date-range-context";
import { SankeyFlowChart, buildSankeyFlowLinkKey } from "@/components/charts/SankeyFlowChart";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n, type TranslationKey, type TranslationVariables } from "@/i18n";
import { FINANCE_CATEGORY_OPTIONS, directionLabel, financeCategoryLabel, groceryCategoryLabel } from "@/lib/category-presentation";
import { formatEurFromCents } from "@/utils/format";

type MultiSelectOption = {
  value: string;
  label: string;
  description?: string;
};

const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
const OTHER_INFLOW_NODE = "inflow:__other__";
const SYNTHETIC_INFLOW_NODE = "inflow:__synthetic__";
const OTHER_CATEGORY_NODE = "category:__other__";
const OTHER_MERCHANT_NODE = "merchant:__other__";
const OTHER_SOURCE_NODE = "source:__other__";
const OTHER_SUBCATEGORY_PREFIX = "subcategory:__other__:";
const DIRECT_SUBCATEGORY_PREFIX = "subcategory:__direct__:";
const LOCALIZABLE_FINANCE_CATEGORIES = new Set<string>([
  ...FINANCE_CATEGORY_OPTIONS,
  "income",
  "other",
  "uncategorized",
]);
type Translate = (key: TranslationKey, values?: TranslationVariables) => string;
type SankeyTimeView = "report_range" | "month" | "year" | "year_average_month";
type SankeyWorkspaceView = "current" | "compare";
type SankeySelection =
  | { kind: "node"; nodeId: string }
  | { kind: "link"; linkKey: string }
  | null;
type SankeyRenameDraft = {
  nodeId: string;
  value: string;
} | null;

function downloadBlob(filename: string, content: string, type: string): boolean {
  if (typeof URL.createObjectURL !== "function") {
    return false;
  }
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return true;
}

function downloadDataUrl(filename: string, dataUrl: string) {
  const anchor = document.createElement("a");
  anchor.href = dataUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function downloadFile(filename: string, content: string) {
  downloadBlob(filename, content, "application/json;charset=utf-8");
}

function heatmapColor(rgb: string, intensity: number): string {
  const alpha = intensity > 0 ? Math.max(0.14, Math.min(1, intensity)) : 0.08;
  return `rgba(${rgb}, ${alpha})`;
}

function formatSelectionSummary(
  locale: string,
  options: MultiSelectOption[],
  selectedValues: string[],
  placeholder: string,
): string {
  if (selectedValues.length === 0) {
    return placeholder;
  }

  const labels = selectedValues.map((value) => {
    const option = options.find((entry) => entry.value === value);
    return option?.label ?? value;
  });

  if (labels.length <= 2) {
    return labels.join(", ");
  }

  return locale === "de" ? `${labels.length} ausgewählt` : `${labels.length} selected`;
}

function formatHeatmapMetric(locale: string, valueMode: string, amountCents: number, count: number): string {
  if (valueMode === "count") {
    return locale === "de" ? `${count} Belege` : `${count} receipts`;
  }
  return formatEurFromCents(amountCents);
}

function formatDateOnly(value: Date): string {
  const copy = new Date(value);
  copy.setHours(0, 0, 0, 0);
  const year = copy.getFullYear();
  const month = String(copy.getMonth() + 1).padStart(2, "0");
  const day = String(copy.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftDays(value: Date, days: number): Date {
  const copy = new Date(value);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function startOfWeek(value: Date): Date {
  const copy = new Date(value);
  const weekday = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - weekday);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function endOfWeek(value: Date): Date {
  return shiftDays(startOfWeek(value), 6);
}

function monthBounds(monthValue: string): { fromDate: string; toDate: string } | null {
  const match = /^(\d{4})-(\d{2})$/.exec(monthValue);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const from = new Date(year, month - 1, 1);
  const to = new Date(year, month, 0);
  return { fromDate: formatDateOnly(from), toDate: formatDateOnly(to) };
}

function yearBounds(year: number): { fromDate: string; toDate: string } {
  return {
    fromDate: formatDateOnly(new Date(year, 0, 1)),
    toDate: formatDateOnly(new Date(year, 11, 31))
  };
}

function deriveWeekdayHeatmap(
  fallback: Array<{ weekday: number; amount_cents: number; count: number }>,
  matrixPoints: Array<{ weekday: number; hour: number; amount_cents: number; count: number }>
): Array<{ weekday: number; amount_cents: number; count: number }> {
  if (matrixPoints.length === 0) {
    return Array.from({ length: 7 }, (_, weekday) => (
      fallback.find((point) => point.weekday === weekday) ?? { weekday, amount_cents: 0, count: 0 }
    ));
  }

  const buckets = new Map<number, { weekday: number; amount_cents: number; count: number }>();
  for (const point of matrixPoints) {
    const current = buckets.get(point.weekday) ?? { weekday: point.weekday, amount_cents: 0, count: 0 };
    current.amount_cents += point.amount_cents;
    current.count += point.count;
    buckets.set(point.weekday, current);
  }

  return Array.from({ length: 7 }, (_, weekday) => (
    buckets.get(weekday) ?? fallback.find((point) => point.weekday === weekday) ?? { weekday, amount_cents: 0, count: 0 }
  ));
}


function serializeSvg(svgNode: SVGSVGElement): string {
  const clone = svgNode.cloneNode(true) as SVGSVGElement;
  if (!clone.getAttribute("xmlns")) {
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  }
  return new XMLSerializer().serializeToString(clone);
}

function readRootBackgroundColor(): string {
  if (typeof window === "undefined") {
    return "#ffffff";
  }
  const background = getComputedStyle(document.documentElement).getPropertyValue("--background").trim();
  return background.startsWith("#") ? background : background ? "hsl(" + background + ")" : "#ffffff";
}

function formatDateWindowLabel(fromDate: string, toDate: string, locale: string): string {
  const formatter = new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  return formatter.format(new Date(fromDate)) + " - " + formatter.format(new Date(toDate));
}

function buildReportSankeyFilenameBase(
  fromDate: string,
  toDate: string,
  mode: ReportSankeyMode,
  breakdown: ReportSankeyBreakdown,
  timeView: SankeyTimeView,
): string {
  return "report_sankey_" + mode + "_" + breakdown + "_" + timeView + "_" + fromDate + "_" + toDate;
}

function buildReportSankeyNodeLabel(
  node: ReportSankeyResponse["nodes"][number],
  t: Translate,
  copy: {
    sankeyOtherInflows: string;
    sankeySyntheticInflow: string;
    sankeyOtherCategories: string;
    sankeyOtherMerchants: string;
    sankeyOtherSources: string;
    sankeyOtherSubcategories: string;
    sankeyDirectSubcategory: string;
  },
): string {
  if (node.id === OTHER_INFLOW_NODE) {
    return copy.sankeyOtherInflows;
  }
  if (node.id === SYNTHETIC_INFLOW_NODE) {
    return copy.sankeySyntheticInflow;
  }
  if (node.id === OTHER_CATEGORY_NODE) {
    return copy.sankeyOtherCategories;
  }
  if (node.id === OTHER_MERCHANT_NODE) {
    return copy.sankeyOtherMerchants;
  }
  if (node.id === OTHER_SOURCE_NODE) {
    return copy.sankeyOtherSources;
  }
  if (node.id.startsWith(OTHER_SUBCATEGORY_PREFIX)) {
    return copy.sankeyOtherSubcategories;
  }
  if (node.id.startsWith(DIRECT_SUBCATEGORY_PREFIX)) {
    return copy.sankeyDirectSubcategory;
  }
  if (node.category_id) {
    if (
      node.kind === "subcategory"
      && (
        node.category_id.startsWith("groceries:")
        || node.category_id === "groceries"
        || node.category_id === "deposit"
        || node.category_id === "other"
        || node.category_id === "uncategorized"
      )
    ) {
      return groceryCategoryLabel(node.category_id, t);
    }
    return financeCategoryLabel(node.category_id, t);
  }
  if (node.kind === "inflow" && LOCALIZABLE_FINANCE_CATEGORIES.has(node.label)) {
    return financeCategoryLabel(node.label, t);
  }
  return node.label;
}

function buildReportSankeyNotes(
  sankey: ReportSankeyResponse | undefined,
  copy: {
    sankeyAggregationNote: string;
    sankeyEditedNote: string;
    sankeyCombinedNote: string;
    sankeySubcategoryOnlyBreakdownNote: string;
    sankeyOutflowNote: string;
    sankeySubcategoryBreakdownNote: string;
    sankeySubcategorySourceBreakdownNote: string;
    sankeySourceBreakdownNote: string;
    sankeySourceFilterNote: string;
    sankeySyntheticNote: string;
    sankeyTimeAnchorNote: string;
    sankeyTimeAverageMonthNote: string;
  },
  options: {
    breakdown: ReportSankeyBreakdown;
    editedView: boolean;
    timeView: SankeyTimeView;
  },
): string[] {
  if (!sankey) {
    return [];
  }
  const notes = [
    sankey.mode === "combined" ? copy.sankeyCombinedNote : copy.sankeyOutflowNote,
  ];
  if (options.breakdown === "subcategory_only") {
    notes.push(copy.sankeySubcategoryOnlyBreakdownNote);
  }
  if (options.breakdown === "subcategory") {
    notes.push(copy.sankeySubcategoryBreakdownNote);
  }
  if (options.breakdown === "subcategory_source") {
    notes.push(copy.sankeySubcategorySourceBreakdownNote);
  }
  if (options.breakdown === "source") {
    notes.push(copy.sankeySourceBreakdownNote);
  }
  if (sankey.flags.manual_inflows_excluded_by_source_filter) {
    notes.push(copy.sankeySourceFilterNote);
  }
  if (sankey.flags.synthetic_inflow_bucket && sankey.mode === "combined") {
    notes.push(copy.sankeySyntheticNote);
  }
  if (
    sankey.flags.aggregated_inflows
    || sankey.flags.aggregated_categories
    || sankey.flags.aggregated_merchants
    || sankey.flags.aggregated_subcategories
    || sankey.flags.aggregated_sources
  ) {
    notes.push(copy.sankeyAggregationNote);
  }
  if (options.timeView !== "report_range") {
    notes.push(copy.sankeyTimeAnchorNote);
  }
  if (options.timeView === "year_average_month") {
    notes.push(copy.sankeyTimeAverageMonthNote);
  }
  if (options.editedView) {
    notes.push(copy.sankeyEditedNote);
  }
  return notes;
}

function applyReportSankeyLabelOverrides(
  sankey: ReportSankeyResponse | undefined,
  labelOverrides: Record<string, string>,
): ReportSankeyResponse | undefined {
  if (!sankey || Object.keys(labelOverrides).length === 0) {
    return sankey;
  }

  return {
    ...sankey,
    nodes: sankey.nodes.map((node) => ({
      ...node,
      label: labelOverrides[node.id] ?? node.label,
    })),
  };
}

function parseDateOnly(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}

function countCoveredMonths(fromDate: string, toDate: string): number {
  const from = parseDateOnly(fromDate);
  const to = parseDateOnly(toDate);
  return Math.max(1, (to.getFullYear() - from.getFullYear()) * 12 + (to.getMonth() - from.getMonth()) + 1);
}

function resolveSankeyWindow(
  fromDate: string,
  toDate: string,
  timeView: SankeyTimeView,
): {
  averageMonthDivisor: number;
  fromDate: string;
  toDate: string;
} {
  if (timeView === "report_range") {
    return {
      fromDate,
      toDate,
      averageMonthDivisor: countCoveredMonths(fromDate, toDate),
    };
  }

  const anchor = parseDateOnly(toDate);
  if (timeView === "month") {
    return {
      fromDate: formatDateOnly(new Date(anchor.getFullYear(), anchor.getMonth(), 1)),
      toDate,
      averageMonthDivisor: 1,
    };
  }

  const yearStart = formatDateOnly(new Date(anchor.getFullYear(), 0, 1));
  return {
    fromDate: yearStart,
    toDate,
    averageMonthDivisor: countCoveredMonths(yearStart, toDate),
  };
}

function scaleReportSankeyForAverageMonth(
  sankey: ReportSankeyResponse | undefined,
  monthDivisor: number,
): ReportSankeyResponse | undefined {
  if (!sankey || monthDivisor <= 1) {
    return sankey;
  }

  const scale = (value: number): number => Math.max(0, Math.round(value / monthDivisor));
  return {
    ...sankey,
    summary: {
      total_outflow_cents: scale(sankey.summary.total_outflow_cents),
      total_inflow_basis_cents: scale(sankey.summary.total_inflow_basis_cents),
      node_count: sankey.summary.node_count,
      link_count: sankey.summary.link_count,
    },
    nodes: sankey.nodes.map((node) => ({
      ...node,
      amount_cents: scale(node.amount_cents),
      basis_amount_cents: node.basis_amount_cents === undefined ? undefined : scale(node.basis_amount_cents),
    })),
    links: sankey.links.map((link) => ({
      ...link,
      value_cents: scale(link.value_cents),
    })),
  };
}

function sankeyMatchesActiveView(
  sankey: ReportSankeyResponse | undefined,
  options: {
    fromDate: string;
    toDate: string;
    mode: ReportSankeyMode;
    breakdown: ReportSankeyBreakdown;
  },
): sankey is ReportSankeyResponse {
  return Boolean(
    sankey
      && sankey.period.from_date === options.fromDate
      && sankey.period.to_date === options.toDate
      && sankey.mode === options.mode
      && sankey.breakdown === options.breakdown,
  );
}

function applyReportSankeyVisibility(
  sankey: ReportSankeyResponse | undefined,
  hiddenNodeIds: Set<string>,
  hiddenLinkKeys: Set<string>,
): ReportSankeyResponse | undefined {
  if (!sankey) {
    return undefined;
  }

  const visibleLinks = sankey.links.filter((link) => {
    const linkKey = buildSankeyFlowLinkKey(link.source, link.target);
    return (
      !hiddenLinkKeys.has(linkKey)
      && !hiddenNodeIds.has(link.source)
      && !hiddenNodeIds.has(link.target)
    );
  });

  if (visibleLinks.length === 0) {
    return {
      ...sankey,
      summary: {
        total_outflow_cents: 0,
        total_inflow_basis_cents: 0,
        node_count: 0,
        link_count: 0,
      },
      nodes: [],
      links: [],
    };
  }

  const connectedNodeIds = new Set<string>();
  const inboundTotals = new Map<string, number>();
  const outboundTotals = new Map<string, number>();

  for (const link of visibleLinks) {
    connectedNodeIds.add(link.source);
    connectedNodeIds.add(link.target);
    outboundTotals.set(link.source, (outboundTotals.get(link.source) ?? 0) + link.value_cents);
    inboundTotals.set(link.target, (inboundTotals.get(link.target) ?? 0) + link.value_cents);
  }

  const visibleNodes = sankey.nodes
    .filter((node) => !hiddenNodeIds.has(node.id) && connectedNodeIds.has(node.id))
    .map((node) => {
      const visibleAmount = Math.max(inboundTotals.get(node.id) ?? 0, outboundTotals.get(node.id) ?? 0);
      const scaledBasis = (
        typeof node.basis_amount_cents === "number"
        && node.amount_cents > 0
      )
        ? Math.round(node.basis_amount_cents * (visibleAmount / node.amount_cents))
        : node.basis_amount_cents;
      return {
        ...node,
        amount_cents: visibleAmount,
        basis_amount_cents: scaledBasis,
      };
    });

  const visibleNodeIdSet = new Set(visibleNodes.map((node) => node.id));
  const normalizedLinks = visibleLinks.filter(
    (link) => visibleNodeIdSet.has(link.source) && visibleNodeIdSet.has(link.target),
  );
  const sourceNodeIds = new Set(normalizedLinks.map((link) => link.source));
  const totalOutflowCents = normalizedLinks
    .filter((link) => !sourceNodeIds.has(link.target))
    .reduce((sum, link) => sum + link.value_cents, 0);
  const totalInflowBasisCents = visibleNodes
    .filter((node) => node.kind === "inflow")
    .reduce((sum, node) => sum + (node.basis_amount_cents ?? node.amount_cents), 0);

  return {
    ...sankey,
    summary: {
      total_outflow_cents: totalOutflowCents,
      total_inflow_basis_cents: totalInflowBasisCents,
      node_count: visibleNodes.length,
      link_count: normalizedLinks.length,
    },
    nodes: visibleNodes,
    links: normalizedLinks,
  };
}

export function ReportsPage() {
  const { fromDate, toDate, setPreset, setCustomRange } = useDateRangeContext();
  const { workspace } = useAccessScope();
  const { locale, t } = useI18n();
  const copy = locale === "de"
    ? {
        sourceLabel: "Quelle",
        sourcePlaceholder: "Alle Quellen",
        sourceEmpty: "Keine Quellen vorhanden.",
        merchantLabel: "Händler",
        merchantPlaceholder: "Alle Händler",
        merchantEmpty: "Keine Händler für diese Auswahl.",
        clearSelection: "Auswahl zurücksetzen",
        weeklyHeatmapTitle: "Wochen-Heatmap",
        weeklyHeatmapDescription: "Ein Feld pro Wochentag. Dunklere Felder bedeuten mehr Ausgaben oder mehr Belege.",
        weekdayHourlyTitle: "Wochen- und Stunden-Heatmap",
        weekdayHourlyDescription: "Zeigt, an welchen Wochentagen und Stunden Ihre Aktivität konzentriert ist.",
        heatmapLegend: "Stärker = mehr Aktivität",
        receiptsShort: "Belege",
        hourAxis: "Stunde",
        dateRangeTitle: "Zeitraum",
        dateRangeDescription: "Wählen Sie hier direkt Wochen, Monate, Jahre oder einen eigenen Bereich für diese Auswertung.",
        currentRange: "Aktiver Zeitraum",
        lastWeek: "Letzte Woche",
        lastYear: "Letztes Jahr",
        allTime: "Gesamte Zeit",
        monthLabel: "Monat",
        yearLabel: "Jahr",
        customFrom: "Von",
        customTo: "Bis",
        pickYear: "Jahr wählen",
        sankeyCombinedMode: "Kombiniert",
        sankeyCombinedNote: "Kombiniert ordnet den ausgewählten Abfluss proportional nach Inflow-Buckets des Zeitraums zu. Das ist keine transaktionsgenaue Geldspur.",
        sankeyBreakdownLabel: "Sankey-Aufschlüsselung",
        sankeyBreakdownMerchants: "Händler",
        sankeyBreakdownSubcategories: "Unterkategorien",
        sankeyBreakdownSubcategoryMerchants: "Unterkategorien + Händler",
        sankeyBreakdownSubcategorySources: "Unterkategorien + Quellen",
        sankeyBreakdownSources: "Quellen",
        sankeyDirectionEmpty: "Dieses Diagramm zeigt nur Abflüsse. Wählen Sie „Alle“ oder „Abfluss“, um Werte anzuzeigen.",
        sankeyExportJson: "JSON exportieren",
        sankeyExportPng: "PNG exportieren",
        sankeyExportSvg: "SVG exportieren",
        sankeyExportingPng: "PNG wird exportiert...",
        sankeyLoading: "Sankey-Diagramm wird geladen...",
        sankeyNoData: "Für die aktuellen Filter sind keine Flussdaten verfügbar.",
        sankeyOtherCategories: "Weitere Kategorien",
        sankeyOtherInflows: "Weitere Zuflüsse",
        sankeyOtherMerchants: "Weitere Händler",
        sankeyOtherSources: "Weitere Quellen",
        sankeyOtherSubcategories: "Weitere Unterkategorien",
        sankeyOutflowMode: "Nur Abfluss",
        sankeyOutflowNote: "Nur Abfluss zeigt beobachtete Ausgabenkategorien und Händler ohne künstliche Herkunftszuteilung.",
        sankeySubcategoryOnlyBreakdownNote: "Unterkategorien enden auf der Detail-Ebene. Für Lebensmittel nutzt diese Ebene echte Artikelkategorien wie Fleisch, Fisch oder Getränke, wenn sie vorhanden sind.",
        sankeySubcategoryBreakdownNote: "Unterkategorien + Händler führen dieselbe Detail-Ebene weiter bis zu den Händlern. Für Lebensmittel nutzt die mittlere Ebene echte Artikelkategorien wie Fleisch, Fisch oder Getränke, wenn sie vorhanden sind.",
        sankeySubcategorySourceBreakdownNote: "Unterkategorien + Quellen führen dieselbe Detail-Ebene weiter bis zu den aufgezeichneten Quellen oder Connectoren der Ausgabetransaktionen.",
        sankeySourceBreakdownNote: "Quellen zeigen die aufgezeichnete Herkunft der Ausgabetransaktion, also z. B. Connector oder Ingest-Weg. Das ist keine Aussage über die Herkunft des Zuflusses.",
        sankeySourceFilterNote: "Bei aktiven Quellenfiltern bleiben manuelle Cashflow-Zuflüsse außen vor, weil sie keiner einzelnen Quelle zugeordnet sind.",
        sankeySummaryLinks: "Verbindungen",
        sankeySummaryNodes: "Knoten",
        sankeySummaryOutflow: "Ausgewählter Abfluss",
        sankeySummaryBasis: "Zuflussbasis",
        sankeyDirectSubcategory: "Direkt",
        sankeySyntheticInflow: "Nicht zugeordneter Zeitraum-Zufluss",
        sankeySyntheticNote: "Es war keine passende Zuflussbasis verfügbar. Deshalb nutzt „Kombiniert“ einen offengelegten Sammel-Bucket für den Zeitraum.",
        sankeyAggregationNote: "Kleine Werte werden zu „Weitere …“ zusammengefasst, damit das Diagramm mit echten Daten lesbar bleibt.",
        sankeyTitle: "Cashflow-Sankey",
        sankeyDescription: "Erkunden Sie, wie sich der ausgewählte Zeitraum über Kategorien und Händler verdichtet, und exportieren Sie die aktuelle Ansicht.",
        sankeyWorkspaceCompareAllocationNote: "Die Gruppen-Seite folgt den aktuellen Workspace- und Zuteilungsregeln. Gemischt zugeteilte Belege können dadurch auf der Gruppen-Seite erscheinen.",
        sankeyWorkspaceCompareUnavailable: "Für diesen Desktop-Nutzer ist aktuell keine geteilte Gruppe konfiguriert. Legen Sie eine Gruppe an oder wechseln Sie in eine geteilte Gruppe, um persönliche und gemeinsame Flüsse zu vergleichen.",
        sankeyWorkspaceCompareModeNote: "Arbeitsbereich-Vergleich nutzt aktuell „Nur Abfluss“, damit persönliche und Gruppen-Daten ohne künstliche Zuflusszuordnung nebeneinander bleiben.",
        sankeyWorkspaceCompareNote: "Arbeitsbereich-Vergleich lädt persönliche und Gruppen-Daten getrennt und führt sie erst im Diagramm zusammen. Das ist ein Workspace-Vergleich, keine personen-genaue Ausgabenaufteilung.",
        sankeyWorkspaceCompareView: "Persönlich + Gruppe",
        sankeyWorkspaceCurrentView: "Aktueller Arbeitsbereich",
        sankeyWorkspaceGroupLabel: "Geteilte Gruppe",
        sankeyWorkspacePersonalNode: "Persönlich",
        sankeyWorkspaceSharedFallback: "Geteilte Gruppe",
        sankeyWorkspaceViewLabel: "Arbeitsbereiche",
        sankeyAllHidden: "Alle Flüsse sind in dieser bearbeiteten Ansicht ausgeblendet. Setzen Sie die Ansicht zurück, um sie wieder anzuzeigen.",
        sankeyClearSelection: "Auswahl aufheben",
        sankeyEditedNote: "Ausgeblendete Knoten, Verbindungen und umbenannte Bezeichnungen gelten nur für diese aktuelle Ansicht und für Exporte daraus.",
        sankeyEditorDescription: "Blenden Sie einzelne Verbindungen oder ganze Knoten aus, wenn Sie eine bereinigte Version teilen oder exportieren möchten.",
        sankeyEditorTitle: "Ansicht bearbeiten",
        sankeyHiddenLinks: "Ausgeblendete Verbindungen",
        sankeyHiddenNodes: "Ausgeblendete Knoten",
        sankeyHideSelectedFlow: "Ausgewählte Verbindung ausblenden",
        sankeyHideSelectedNode: "Ausgewählten Knoten ausblenden",
        sankeySelectedFlow: "Ausgewählte Verbindung",
        sankeySelectedNode: "Ausgewählter Knoten",
        sankeySelectionEmpty: "Klicken Sie auf einen Fluss oder einen Knoten im Diagramm, um ihn für diese Ansicht auszublenden.",
        sankeySummaryWindow: "Sankey-Zeitraum",
        sankeyTimeAnchorNote: "Monat und Jahr richten sich am Enddatum des Bericht-Zeitraums aus und verändern die übrigen Filter nicht.",
        sankeyTimeAverageMonthMode: "Ø Monat",
        sankeyTimeAverageMonthNote: "Ø Monat skaliert das bisherige Jahr bis zum Enddatum auf einen durchschnittlichen Monat herunter.",
        sankeyTimeMonthMode: "Monat",
        sankeyTimeRangeMode: "Zeitraum",
        sankeyTimeViewLabel: "Sankey-Zeitfenster",
        sankeyTimeYearMode: "Jahr",
        sankeyResetEditedView: "Ansicht zurücksetzen",
        sankeyRenameCancel: "Umbenennen abbrechen",
        sankeyRenameHint: "Doppelklicken Sie auf einen Knoten oder wählen Sie ihn aus, um die sichtbare Bezeichnung für diese Ansicht zu ändern.",
        sankeyRenameInputLabel: "Sichtbare Bezeichnung",
        sankeyRenameNode: "Knoten umbenennen",
        sankeyRenamePlaceholder: "Bezeichnung eingeben",
        sankeyRenameSave: "Bezeichnung speichern",
        sankeyRenamedLabels: "Umbenannte Bezeichnungen",
      }
    : {
        sourceLabel: "Source",
        sourcePlaceholder: "All sources",
        sourceEmpty: "No sources available.",
        merchantLabel: "Merchant",
        merchantPlaceholder: "All merchants",
        merchantEmpty: "No merchants for this selection.",
        clearSelection: "Clear selection",
        weeklyHeatmapTitle: "Weekly heatmap",
        weeklyHeatmapDescription: "One tile per weekday. Darker tiles mean more spend or more receipts.",
        weekdayHourlyTitle: "Weekly hourly heatmap",
        weekdayHourlyDescription: "Shows which weekday and hour combinations carry the most activity.",
        heatmapLegend: "Stronger = more activity",
        receiptsShort: "receipts",
        hourAxis: "Hour",
        dateRangeTitle: "Date range",
        dateRangeDescription: "Pick weeks, months, years, or a custom window directly on this report page.",
        currentRange: "Active range",
        lastWeek: "Last week",
        lastYear: "Last year",
        allTime: "All time",
        monthLabel: "Month",
        yearLabel: "Year",
        customFrom: "From",
        customTo: "To",
        pickYear: "Pick year",
        sankeyCombinedMode: "Combined",
        sankeyCombinedNote: "Combined mode proportionally attributes the selected outflow across period inflow buckets. It is not transaction-level money provenance.",
        sankeyBreakdownLabel: "Sankey breakdown",
        sankeyBreakdownMerchants: "Merchants",
        sankeyBreakdownSubcategories: "Subcategories",
        sankeyBreakdownSubcategoryMerchants: "Subcategories + merchants",
        sankeyBreakdownSubcategorySources: "Subcategories + sources",
        sankeyBreakdownSources: "Sources",
        sankeyDirectionEmpty: "This diagram only visualizes outflow. Choose All or Outflow to see a graph.",
        sankeyExportJson: "Export JSON",
        sankeyExportPng: "Export PNG",
        sankeyExportSvg: "Export SVG",
        sankeyExportingPng: "Exporting PNG...",
        sankeyLoading: "Loading sankey diagram...",
        sankeyNoData: "No flow data is available for the current filters.",
        sankeyOtherCategories: "Other categories",
        sankeyOtherInflows: "Other inflows",
        sankeyOtherMerchants: "Other merchants",
        sankeyOtherSources: "Other sources",
        sankeyOtherSubcategories: "Other subcategories",
        sankeyOutflowMode: "Outflow only",
        sankeyOutflowNote: "Outflow only shows observed spend categories and merchants without a synthetic origin layer.",
        sankeySubcategoryOnlyBreakdownNote: "Subcategories stop at the detail layer. For groceries this uses real receipt item categories like meat, fish, or beverages when available.",
        sankeySubcategoryBreakdownNote: "Subcategories + merchants continue that same detail layer into the merchant layer. For groceries the middle layer uses real receipt item categories like meat, fish, or beverages when available.",
        sankeySubcategorySourceBreakdownNote: "Subcategories + sources continue that same detail layer into the recorded source or connector layer for the outflow transactions.",
        sankeySourceBreakdownNote: "Sources show the recorded source or connector of the outflow transaction. They do not describe where the inflow bucket came from.",
        sankeySourceFilterNote: "When source filters are active, manual cash-flow inflows stay out because they are not tied to individual sources.",
        sankeySummaryLinks: "Links",
        sankeySummaryNodes: "Nodes",
        sankeySummaryOutflow: "Selected outflow",
        sankeySummaryBasis: "Inflow basis",
        sankeyDirectSubcategory: "Direct",
        sankeySyntheticInflow: "Unattributed period inflow",
        sankeySyntheticNote: "No matching inflow basis was available, so Combined mode falls back to a clearly labeled period-level funding bucket.",
        sankeyAggregationNote: "Small values are rolled into “Other …” buckets to keep the graph readable with real data.",
        sankeyTitle: "Cashflow sankey",
        sankeyDescription: "Inspect how the selected period compresses across categories and merchants, then export the current view.",
        sankeyWorkspaceCompareAllocationNote: "The shared-group side follows the current workspace and allocation rules. Mixed receipts can therefore still appear on the shared side.",
        sankeyWorkspaceCompareUnavailable: "No shared group is currently configured for this desktop user. Create or switch into a shared group to compare personal and shared flows.",
        sankeyWorkspaceCompareModeNote: "Workspace compare currently uses Outflow only so personal and shared-group data stay side by side without synthetic inflow attribution.",
        sankeyWorkspaceCompareNote: "Workspace compare loads personal and shared-group data separately, then merges them only inside this diagram. It is a workspace comparison, not per-person spend attribution.",
        sankeyWorkspaceCompareView: "Personal + shared group",
        sankeyWorkspaceCurrentView: "Current workspace",
        sankeyWorkspaceGroupLabel: "Shared group",
        sankeyWorkspacePersonalNode: "Personal",
        sankeyWorkspaceSharedFallback: "Shared group",
        sankeyWorkspaceViewLabel: "Workspaces",
        sankeyAllHidden: "All flows are hidden in this edited view. Reset the view to bring them back.",
        sankeyClearSelection: "Clear selection",
        sankeyEditedNote: "Hidden nodes, links, and renamed labels only affect this current view and exports made from it.",
        sankeyEditorDescription: "Hide individual links or whole nodes when you want a cleaner version to share or export.",
        sankeyEditorTitle: "Edit view",
        sankeyHiddenLinks: "Hidden links",
        sankeyHiddenNodes: "Hidden nodes",
        sankeyHideSelectedFlow: "Hide selected link",
        sankeyHideSelectedNode: "Hide selected node",
        sankeySelectedFlow: "Selected link",
        sankeySelectedNode: "Selected node",
        sankeySelectionEmpty: "Click a flow band or node in the diagram to hide it from this view.",
        sankeySummaryWindow: "Sankey window",
        sankeyTimeAnchorNote: "Month and year views anchor to the report end date and do not change the rest of the report filters.",
        sankeyTimeAverageMonthMode: "Avg month",
        sankeyTimeAverageMonthNote: "Avg month scales the year-to-date window down to one average month.",
        sankeyTimeMonthMode: "Month",
        sankeyTimeRangeMode: "Range",
        sankeyTimeViewLabel: "Sankey time window",
        sankeyTimeYearMode: "Year",
        sankeyResetEditedView: "Reset view",
        sankeyRenameCancel: "Cancel rename",
        sankeyRenameHint: "Double-click a node, or select one here, to change its visible label for this view.",
        sankeyRenameInputLabel: "Visible label",
        sankeyRenameNode: "Rename node",
        sankeyRenamePlaceholder: "Enter a label",
        sankeyRenameSave: "Save label",
        sankeyRenamedLabels: "Renamed labels",
      };
  const weekdayLabels = locale === "de"
    ? ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    : ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [selectedMerchants, setSelectedMerchants] = useState<string[]>([]);
  const [category, setCategory] = useState("all");
  const [direction, setDirection] = useState("all");
  const [sankeyMode, setSankeyMode] = useState<ReportSankeyMode>("combined");
  const [sankeyBreakdown, setSankeyBreakdown] = useState<ReportSankeyBreakdown>("merchant");
  const [sankeyTimeView, setSankeyTimeView] = useState<SankeyTimeView>("report_range");
  const [sankeyWorkspaceView, setSankeyWorkspaceView] = useState<SankeyWorkspaceView>("current");
  const [sankeyCompareGroupId, setSankeyCompareGroupId] = useState("");
  const [hiddenSankeyNodeIds, setHiddenSankeyNodeIds] = useState<string[]>([]);
  const [hiddenSankeyLinkKeys, setHiddenSankeyLinkKeys] = useState<string[]>([]);
  const [sankeyLabelOverrides, setSankeyLabelOverrides] = useState<Record<string, string>>({});
  const [sankeySelection, setSankeySelection] = useState<SankeySelection>(null);
  const [sankeyRenameDraft, setSankeyRenameDraft] = useState<SankeyRenameDraft>(null);
  const [sankeyExportStatus, setSankeyExportStatus] = useState<string | null>(null);
  const [exportingSankeyPng, setExportingSankeyPng] = useState(false);
  const [valueMode, setValueMode] = useState("amount");
  const sankeyCardRef = useRef<HTMLDivElement | null>(null);
  const sankeySvgRef = useRef<SVGSVGElement | null>(null);
  const sankeyWindow = useMemo(
    () => resolveSankeyWindow(fromDate, toDate, sankeyTimeView),
    [fromDate, sankeyTimeView, toDate],
  );
  const templates = useQuery({ queryKey: ["reports-page", fromDate, toDate], queryFn: () => fetchReportTemplates(fromDate, toDate) });
  const sharedGroupsQuery = useQuery({ queryKey: ["shared-groups", "reports"], queryFn: fetchSharedGroups, staleTime: 60_000 });
  const sourcesQuery = useQuery({ queryKey: ["reports-sources"], queryFn: fetchSources, staleTime: 0 });
  const yearsQuery = useQuery({
    queryKey: ["reports-years", selectedSourceIds],
    queryFn: () => fetchDashboardYears(selectedSourceIds),
    staleTime: 60_000
  });
  const merchantSummaryQuery = useQuery({
    queryKey: ["reports-merchants", fromDate, toDate],
    queryFn: () => fetchMerchantSummary(fromDate, toDate),
    staleTime: 0
  });
  const sourceOptions = (sourcesQuery.data?.sources ?? [])
    .slice()
    .sort((left, right) => left.display_name.localeCompare(right.display_name, locale))
    .map((source) => ({
      value: source.id,
      label: source.display_name,
      description: `${source.kind} · ${source.id}`,
    }));
  const merchantOptions = (merchantSummaryQuery.data?.items ?? [])
    .filter((merchant) => (
      selectedSourceIds.length === 0
      || merchant.source_ids.some((sourceId) => selectedSourceIds.includes(sourceId))
    ))
    .slice()
    .sort((left, right) => left.merchant.localeCompare(right.merchant, locale))
    .map((merchant) => ({
      value: merchant.merchant,
      label: merchant.merchant,
      description: merchant.source_ids.join(", "),
    }));
  const sharedGroupOptions = (sharedGroupsQuery.data?.groups ?? [])
    .filter((group) => group.status === "active")
    .slice()
    .sort((left, right) => left.name.localeCompare(right.name, locale))
    .map((group) => ({
      value: group.group_id,
      label: group.name,
      description: group.group_type,
    }));
  const compareAvailable = workspace.kind === "shared-group" || sharedGroupOptions.length > 0;
  const compareGroupId = workspace.kind === "shared-group"
    ? workspace.groupId
    : (sankeyCompareGroupId || sharedGroupOptions[0]?.value || "");
  const compareGroupLabel = workspace.kind === "shared-group"
    ? (
      sharedGroupsQuery.data?.groups.find((group) => group.group_id === workspace.groupId)?.name
      ?? copy.sankeyWorkspaceSharedFallback
    )
    : (
      sharedGroupOptions.find((group) => group.value === compareGroupId)?.label
      ?? copy.sankeyWorkspaceSharedFallback
    );
  const effectiveSankeyMode: ReportSankeyMode = sankeyWorkspaceView === "compare" ? "outflow_only" : sankeyMode;

  useEffect(() => {
    if (!merchantSummaryQuery.data) {
      return;
    }
    const availableMerchants = new Set(
      merchantSummaryQuery.data.items
        .filter((merchant) => (
          selectedSourceIds.length === 0
          || merchant.source_ids.some((sourceId) => selectedSourceIds.includes(sourceId))
        ))
        .map((merchant) => merchant.merchant)
    );
    setSelectedMerchants((current) => {
      const next = current.filter((merchant) => availableMerchants.has(merchant));
      return next.length === current.length ? current : next;
    });
  }, [merchantSummaryQuery.data, selectedSourceIds]);

  useEffect(() => {
    if (!compareAvailable && sankeyWorkspaceView === "compare") {
      setSankeyWorkspaceView("current");
    }
  }, [compareAvailable, sankeyWorkspaceView]);

  useEffect(() => {
    if (workspace.kind === "shared-group") {
      return;
    }
    if (sankeyCompareGroupId) {
      const exists = sharedGroupOptions.some((group) => group.value === sankeyCompareGroupId);
      if (exists) {
        return;
      }
    }
    if (sharedGroupOptions[0]?.value) {
      setSankeyCompareGroupId(sharedGroupOptions[0].value);
    }
  }, [sankeyCompareGroupId, sharedGroupOptions, workspace.kind]);

  useEffect(() => {
    setHiddenSankeyNodeIds([]);
    setHiddenSankeyLinkKeys([]);
    setSankeyLabelOverrides({});
    setSankeySelection(null);
    setSankeyRenameDraft(null);
    setSankeyExportStatus(null);
  }, [compareGroupId, sankeyWorkspaceView]);


  const patterns = useQuery({
    queryKey: ["reports-patterns", fromDate, toDate, selectedSourceIds, selectedMerchants, category, direction, valueMode],
    queryFn: () => fetchReportPatterns({
      fromDate,
      toDate,
      merchants: selectedMerchants,
      financeCategoryId: category === "all" ? undefined : category,
      direction: direction === "all" ? undefined : direction,
      sourceIds: selectedSourceIds,
      valueMode
    })
  });
  const sankey = useQuery({
    queryKey: [
      "reports-sankey",
      sankeyWindow.fromDate,
      sankeyWindow.toDate,
      selectedSourceIds,
      selectedMerchants,
      category,
      direction,
      effectiveSankeyMode,
      sankeyBreakdown,
      sankeyTimeView,
      sankeyWorkspaceView,
    ],
    queryFn: () => fetchReportSankey({
      fromDate: sankeyWindow.fromDate,
      toDate: sankeyWindow.toDate,
      merchants: selectedMerchants,
      financeCategoryId: category === "all" ? undefined : category,
      direction: direction === "all" ? undefined : direction,
      sourceIds: selectedSourceIds,
      mode: effectiveSankeyMode,
      breakdown: sankeyBreakdown,
      topN: 8,
    }),
    enabled: sankeyWorkspaceView === "current",
  });
  const comparePersonalSankey = useQuery({
    queryKey: [
      "reports-sankey-compare",
      "personal",
      sankeyWindow.fromDate,
      sankeyWindow.toDate,
      selectedSourceIds,
      selectedMerchants,
      category,
      direction,
      sankeyBreakdown,
      sankeyTimeView,
      compareGroupId,
    ],
    queryFn: () => fetchReportSankey({
      fromDate: sankeyWindow.fromDate,
      toDate: sankeyWindow.toDate,
      merchants: selectedMerchants,
      financeCategoryId: category === "all" ? undefined : category,
      direction: direction === "all" ? undefined : direction,
      sourceIds: selectedSourceIds,
      mode: "outflow_only",
      breakdown: sankeyBreakdown,
      scopeOverride: "personal",
      topN: 8,
    }),
    enabled: sankeyWorkspaceView === "compare" && Boolean(compareGroupId),
  });
  const compareGroupSankey = useQuery({
    queryKey: [
      "reports-sankey-compare",
      compareGroupId,
      sankeyWindow.fromDate,
      sankeyWindow.toDate,
      selectedSourceIds,
      selectedMerchants,
      category,
      direction,
      sankeyBreakdown,
      sankeyTimeView,
    ],
    queryFn: () => fetchReportSankey({
      fromDate: sankeyWindow.fromDate,
      toDate: sankeyWindow.toDate,
      merchants: selectedMerchants,
      financeCategoryId: category === "all" ? undefined : category,
      direction: direction === "all" ? undefined : direction,
      sourceIds: selectedSourceIds,
      mode: "outflow_only",
      breakdown: sankeyBreakdown,
      scopeOverride: `group:${compareGroupId}`,
      topN: 8,
    }),
    enabled: sankeyWorkspaceView === "compare" && Boolean(compareGroupId),
  });
  const data = patterns.data;
  const matrixPoints = data?.weekday_hour_matrix ?? [];
  const weekdayHeatmap = deriveWeekdayHeatmap(data?.weekday_heatmap ?? [], matrixPoints);
  const maxWeekday = Math.max(1, ...weekdayHeatmap.map((point) => valueMode === "count" ? point.count : point.amount_cents));
  const maxMatrix = Math.max(1, ...matrixPoints.map((point) => valueMode === "count" ? point.count : point.amount_cents));
  const rawSankey = useMemo(() => {
    if (sankeyWorkspaceView === "compare") {
      const personalSankey = sankeyMatchesActiveView(comparePersonalSankey.data, {
        fromDate: sankeyWindow.fromDate,
        toDate: sankeyWindow.toDate,
        mode: "outflow_only",
        breakdown: sankeyBreakdown,
      }) ? comparePersonalSankey.data : undefined;
      const groupSankey = sankeyMatchesActiveView(compareGroupSankey.data, {
        fromDate: sankeyWindow.fromDate,
        toDate: sankeyWindow.toDate,
        mode: "outflow_only",
        breakdown: sankeyBreakdown,
      }) ? compareGroupSankey.data : undefined;
      if (!personalSankey || !groupSankey) {
        return undefined;
      }
      return buildWorkspaceComparisonSankey({
        breakdown: sankeyBreakdown,
        personal: personalSankey,
        personalLabel: copy.sankeyWorkspacePersonalNode,
        group: groupSankey,
        groupLabel: compareGroupLabel,
      });
    }
    return sankeyMatchesActiveView(sankey.data, {
      fromDate: sankeyWindow.fromDate,
      toDate: sankeyWindow.toDate,
      mode: effectiveSankeyMode,
      breakdown: sankeyBreakdown,
    })
      ? sankey.data
      : undefined;
  }, [
    compareGroupLabel,
    compareGroupSankey.data,
    comparePersonalSankey.data,
    copy.sankeyWorkspacePersonalNode,
    effectiveSankeyMode,
    sankey.data,
    sankeyBreakdown,
    sankeyWindow.fromDate,
    sankeyWindow.toDate,
    sankeyWorkspaceView,
  ]);
  const sankeyViewIsRefreshing = sankeyWorkspaceView === "compare"
    ? ((comparePersonalSankey.isFetching || compareGroupSankey.isFetching) && !rawSankey)
    : (sankey.isFetching && !rawSankey);
  const transformedSankey = useMemo(
    () => (
      sankeyTimeView === "year_average_month"
        ? scaleReportSankeyForAverageMonth(rawSankey, sankeyWindow.averageMonthDivisor)
        : rawSankey
    ),
    [rawSankey, sankeyTimeView, sankeyWindow.averageMonthDivisor],
  );
  const labelledSankey = useMemo(
    () => applyReportSankeyLabelOverrides(transformedSankey, sankeyLabelOverrides),
    [sankeyLabelOverrides, transformedSankey],
  );
  const hiddenNodeIdSet = useMemo(() => new Set(hiddenSankeyNodeIds), [hiddenSankeyNodeIds]);
  const hiddenLinkKeySet = useMemo(() => new Set(hiddenSankeyLinkKeys), [hiddenSankeyLinkKeys]);
  const sankeyHasEditedView = hiddenSankeyNodeIds.length > 0 || hiddenSankeyLinkKeys.length > 0 || Object.keys(sankeyLabelOverrides).length > 0;
  const activeSankey = useMemo(
    () => applyReportSankeyVisibility(labelledSankey, hiddenNodeIdSet, hiddenLinkKeySet),
    [hiddenLinkKeySet, hiddenNodeIdSet, labelledSankey],
  );
  const sankeyNotes = useMemo(() => {
    const notes = buildReportSankeyNotes(labelledSankey, copy, {
      breakdown: sankeyBreakdown,
      editedView: sankeyHasEditedView,
      timeView: sankeyTimeView,
    });
    if (sankeyWorkspaceView === "compare") {
      notes.push(copy.sankeyWorkspaceCompareNote);
      notes.push(copy.sankeyWorkspaceCompareModeNote);
      notes.push(copy.sankeyWorkspaceCompareAllocationNote);
    }
    return notes;
  }, [copy, labelledSankey, sankeyBreakdown, sankeyHasEditedView, sankeyTimeView, sankeyWorkspaceView]);
  const sankeyFilenameBase = buildReportSankeyFilenameBase(
    activeSankey?.period.from_date ?? sankeyWindow.fromDate,
    activeSankey?.period.to_date ?? sankeyWindow.toDate,
    effectiveSankeyMode,
    sankeyBreakdown,
    sankeyTimeView,
  ) + (sankeyWorkspaceView === "compare" ? "_workspace_compare" : "");
  const sankeyTimeViewLabels: Record<SankeyTimeView, string> = {
    report_range: copy.sankeyTimeRangeMode,
    month: copy.sankeyTimeMonthMode,
    year: copy.sankeyTimeYearMode,
    year_average_month: copy.sankeyTimeAverageMonthMode,
  };
  const sankeyWindowLabel = formatDateWindowLabel(
    activeSankey?.period.from_date ?? sankeyWindow.fromDate,
    activeSankey?.period.to_date ?? sankeyWindow.toDate,
    locale,
  );
  const sankeyNodes = (activeSankey?.nodes ?? []).map((node) => ({
    id: node.id,
    label: sankeyLabelOverrides[node.id] ?? buildReportSankeyNodeLabel(node, t, copy),
    kind: node.kind,
    amountCents: node.amount_cents,
    basisAmountCents: node.basis_amount_cents,
  }));
  const sankeyLinks = (activeSankey?.links ?? []).map((link) => ({
    source: link.source,
    target: link.target,
    value: link.value_cents,
    kind: link.kind,
  }));
  const sankeyDirectionBlocked = direction !== "all" && direction !== "outflow";
  const visibleSankey = sankeyDirectionBlocked ? undefined : activeSankey;
  const visibleSankeyNodes = sankeyDirectionBlocked ? [] : sankeyNodes;
  const visibleSankeyLinks = sankeyDirectionBlocked ? [] : sankeyLinks;
  const sankeyRenderSignature = useMemo(
    () => JSON.stringify({
      from: activeSankey?.period.from_date ?? sankeyWindow.fromDate,
      to: activeSankey?.period.to_date ?? sankeyWindow.toDate,
      mode: effectiveSankeyMode,
      breakdown: sankeyBreakdown,
      timeView: sankeyTimeView,
      nodes: visibleSankeyNodes.map((node) => [node.id, node.label, node.amountCents]),
      links: visibleSankeyLinks.map((link) => [link.source, link.target, link.value]),
    }),
    [
      activeSankey?.period.from_date,
      activeSankey?.period.to_date,
      effectiveSankeyMode,
      sankeyWindow.fromDate,
      sankeyWindow.toDate,
      sankeyBreakdown,
      sankeyTimeView,
      visibleSankeyLinks,
      visibleSankeyNodes,
    ],
  );
  const sankeyBasePending = sankeyWorkspaceView === "compare"
    ? (comparePersonalSankey.isPending || compareGroupSankey.isPending)
    : sankey.isPending;
  const sankeySummaryLoading = (sankeyBasePending || sankeyViewIsRefreshing) && !visibleSankey;
  const sankeyNodeLabelMap = useMemo(
    () => new Map(sankeyNodes.map((node) => [node.id, node.label ?? node.id])),
    [sankeyNodes],
  );
  const selectedSankeyNode = sankeySelection?.kind === "node"
    ? activeSankey?.nodes.find((node) => node.id === sankeySelection.nodeId) ?? null
    : null;
  const selectedSankeyLink = sankeySelection?.kind === "link"
    ? activeSankey?.links.find(
        (link) => buildSankeyFlowLinkKey(link.source, link.target) === sankeySelection.linkKey,
      ) ?? null
    : null;
  const selectedSankeyLabel = selectedSankeyNode
    ? String(sankeyNodeLabelMap.get(selectedSankeyNode.id) ?? selectedSankeyNode.id)
    : selectedSankeyLink
      ? String(sankeyNodeLabelMap.get(selectedSankeyLink.source) ?? selectedSankeyLink.source) + " -> " + String(sankeyNodeLabelMap.get(selectedSankeyLink.target) ?? selectedSankeyLink.target)
      : null;
  const selectedSankeyValue = selectedSankeyNode
    ? selectedSankeyNode.amount_cents
    : selectedSankeyLink?.value_cents ?? 0;
  const selectedSankeyBaseNode = sankeySelection?.kind === "node"
    ? transformedSankey?.nodes.find((node) => node.id === sankeySelection.nodeId) ?? null
    : null;
  const renamedLabelCount = Object.keys(sankeyLabelOverrides).length;

  useEffect(() => {
    setHiddenSankeyNodeIds([]);
    setHiddenSankeyLinkKeys([]);
    setSankeyLabelOverrides({});
    setSankeySelection(null);
    setSankeyRenameDraft(null);
    setSankeyExportStatus(null);
  }, [
    category,
    direction,
    fromDate,
    sankeyBreakdown,
    sankeyCompareGroupId,
    sankeyTimeView,
    sankeyWorkspaceView,
    selectedMerchants.join("|"),
    selectedSourceIds.join("|"),
    toDate,
  ]);

  useEffect(() => {
    if (!sankeySelection) {
      return;
    }
    if (sankeySelection.kind === "node") {
      if (!(activeSankey?.nodes ?? []).some((node) => node.id === sankeySelection.nodeId)) {
        setSankeySelection(null);
        setSankeyRenameDraft((current) => current?.nodeId === sankeySelection.nodeId ? null : current);
      }
      return;
    }
    if (!(activeSankey?.links ?? []).some(
      (link) => buildSankeyFlowLinkKey(link.source, link.target) === sankeySelection.linkKey,
    )) {
      setSankeySelection(null);
    }
  }, [activeSankey, sankeySelection]);

  function toggleSankeyNodeSelection(nodeId: string): void {
    setSankeyRenameDraft((current) => current?.nodeId === nodeId ? current : null);
    setSankeySelection((current) => (
      current?.kind === "node" && current.nodeId === nodeId
        ? null
        : { kind: "node", nodeId }
    ));
  }

  function toggleSankeyLinkSelection(linkKey: string): void {
    setSankeyRenameDraft(null);
    setSankeySelection((current) => (
      current?.kind === "link" && current.linkKey === linkKey
        ? null
        : { kind: "link", linkKey }
    ));
  }

  function hideSelectedSankeyItem(): void {
    if (!sankeySelection) {
      return;
    }
    if (sankeySelection.kind === "node") {
      setHiddenSankeyNodeIds((current) => (
        current.includes(sankeySelection.nodeId) ? current : [...current, sankeySelection.nodeId]
      ));
    } else {
      setHiddenSankeyLinkKeys((current) => (
        current.includes(sankeySelection.linkKey) ? current : [...current, sankeySelection.linkKey]
      ));
    }
    setSankeySelection(null);
    setSankeyRenameDraft(null);
    setSankeyExportStatus(null);
  }

  function resetEditedSankeyView(): void {
    setHiddenSankeyNodeIds([]);
    setHiddenSankeyLinkKeys([]);
    setSankeyLabelOverrides({});
    setSankeySelection(null);
    setSankeyRenameDraft(null);
    setSankeyExportStatus(null);
  }

  function startSankeyNodeRename(nodeId: string): void {
    const node = activeSankey?.nodes.find((entry) => entry.id === nodeId);
    if (!node) {
      return;
    }
    setSankeySelection({ kind: "node", nodeId });
    setSankeyRenameDraft({
      nodeId,
      value: sankeyLabelOverrides[nodeId] ?? node.label,
    });
  }

  function saveSankeyNodeRename(): void {
    if (!sankeyRenameDraft) {
      return;
    }
    const rawValue = sankeyRenameDraft.value.trim();
    const baseNode = transformedSankey?.nodes.find((node) => node.id === sankeyRenameDraft.nodeId) ?? null;
    if (!baseNode) {
      setSankeyRenameDraft(null);
      return;
    }
    setSankeyLabelOverrides((current) => {
      const next = { ...current };
      if (!rawValue || rawValue === baseNode.label) {
        delete next[sankeyRenameDraft.nodeId];
      } else {
        next[sankeyRenameDraft.nodeId] = rawValue;
      }
      return next;
    });
    setSankeyRenameDraft(null);
    setSankeyExportStatus(null);
  }

  const weeklyCards = weekdayLabels.map((label, weekday) => {
    const point = weekdayHeatmap.find((entry) => entry.weekday === weekday) ?? { weekday, amount_cents: 0, count: 0 };
    const rawValue = valueMode === "count" ? point.count : point.amount_cents;
    const metric = formatHeatmapMetric(locale, valueMode, point.amount_cents, point.count);
    return {
      label,
      weekday,
      count: point.count,
      metric,
      title: label + ": " + metric,
      backgroundColor: heatmapColor("16, 185, 129", rawValue / maxWeekday)
    };
  });
  const matrixRows = weekdayLabels.map((label, weekday) => ({
    label,
    cells: HOURS.map((hour) => {
      const point = matrixPoints.find((entry) => entry.weekday === weekday && entry.hour === hour) ?? { amount_cents: 0, count: 0 };
      const rawValue = valueMode === "count" ? point.count : point.amount_cents;
      const metric = formatHeatmapMetric(locale, valueMode, point.amount_cents, point.count);
      return {
        hour,
        title: label + ", " + hour + ":00 - " + metric,
        ariaLabel: label + ", " + hour + ":00, " + metric,
        backgroundColor: heatmapColor("14, 165, 233", rawValue / maxMatrix)
      };
    })
  }));

  async function exportSankeyPng(): Promise<void> {
    if (!visibleSankey || !sankeyCardRef.current) {
      setSankeyExportStatus(copy.sankeyNoData);
      return;
    }
    setExportingSankeyPng(true);
    try {
      const dataUrl = await toPng(sankeyCardRef.current, {
        cacheBust: true,
        pixelRatio: 2,
        backgroundColor: readRootBackgroundColor(),
      });
      downloadDataUrl(sankeyFilenameBase + ".png", dataUrl);
      setSankeyExportStatus(sankeyFilenameBase + ".png");
    } catch (error) {
      setSankeyExportStatus(error instanceof Error ? error.message : copy.sankeyNoData);
    } finally {
      setExportingSankeyPng(false);
    }
  }

  function exportSankeyJson(): void {
    if (!visibleSankey) {
      setSankeyExportStatus(copy.sankeyNoData);
      return;
    }
    const downloaded = downloadBlob(
      sankeyFilenameBase + ".json",
      JSON.stringify(visibleSankey, null, 2) + "\n",
      "application/json;charset=utf-8",
    );
    setSankeyExportStatus(downloaded ? sankeyFilenameBase + ".json" : copy.sankeyNoData);
  }

  function exportSankeySvg(): void {
    if (!visibleSankey || !sankeySvgRef.current) {
      setSankeyExportStatus(copy.sankeyNoData);
      return;
    }
    const downloaded = downloadBlob(
      sankeyFilenameBase + ".svg",
      serializeSvg(sankeySvgRef.current) + "\n",
      "image/svg+xml;charset=utf-8",
    );
    setSankeyExportStatus(downloaded ? sankeyFilenameBase + ".svg" : copy.sankeyNoData);
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t("pages.reports.title")} description={t("pages.reports.description")} />
      <Card className="app-dashboard-surface border-border/60">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            {t("pages.reports.patterns.title")}
          </CardTitle>
          <CardDescription>{t("pages.reports.patterns.description")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <ReportDateRangePanel
            locale={locale}
            copy={copy}
            fromDate={fromDate}
            toDate={toDate}
            years={yearsQuery.data?.years ?? []}
            onSelectPreset={setPreset}
            onSelectRange={setCustomRange}
          />
          <div className="grid gap-3 md:grid-cols-4">
            <MultiSelectDropdown
              label={copy.sourceLabel}
              placeholder={copy.sourcePlaceholder}
              emptyText={copy.sourceEmpty}
              options={sourceOptions}
              selectedValues={selectedSourceIds}
              onChange={setSelectedSourceIds}
              locale={locale}
              clearLabel={copy.clearSelection}
            />
            <MultiSelectDropdown
              label={copy.merchantLabel}
              placeholder={copy.merchantPlaceholder}
              emptyText={copy.merchantEmpty}
              options={merchantOptions}
              selectedValues={selectedMerchants}
              onChange={setSelectedMerchants}
              locale={locale}
              clearLabel={copy.clearSelection}
            />
            <SelectBox label={t("pages.transactions.filter.category")} value={category} onChange={setCategory}>
              <SelectItem value="all">{t("pages.transactions.allCategories")}</SelectItem>
              {["groceries", "housing", "insurance", "credit", "mobility", "car", "investment", "subscriptions", "income", "fees", "tax", "other"].map((value) => (
                <SelectItem key={value} value={value}>{financeCategoryLabel(value, t)}</SelectItem>
              ))}
            </SelectBox>
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectBox label={t("pages.transactions.filter.direction")} value={direction} onChange={setDirection}>
                <SelectItem value="all">{t("pages.transactions.allDirections")}</SelectItem>
                {["outflow", "inflow", "transfer", "neutral"].map((value) => (
                  <SelectItem key={value} value={value}>{directionLabel(value, t)}</SelectItem>
                ))}
              </SelectBox>
              <SelectBox label={t("pages.reports.patterns.valueMode")} value={valueMode} onChange={setValueMode}>
                <SelectItem value="amount">{t("pages.reports.patterns.valueMode.amount")}</SelectItem>
                <SelectItem value="count">{t("pages.reports.patterns.valueMode.count")}</SelectItem>
              </SelectBox>
            </div>
          </div>

          <Card className="border-border/60 bg-background/30">
            <CardHeader>
              <CardTitle>{copy.weeklyHeatmapTitle}</CardTitle>
              <CardDescription>{copy.weeklyHeatmapDescription}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                <span>{copy.heatmapLegend}</span>
                <span>{valueMode === "count" ? copy.receiptsShort : t("pages.reports.patterns.valueMode.amount")}</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-7">
                {weeklyCards.map((card) => (
                    <div
                      key={`${card.label}-${card.metric}-${card.count}`}
                      className="relative overflow-hidden rounded-2xl border border-border/60 p-4"
                      title={card.title}
                    >
                      <div
                        className="absolute inset-0"
                        style={{ backgroundColor: card.backgroundColor }}
                      />
                      <div className="relative space-y-10">
                        <div>
                          <p className="text-sm font-semibold">{card.label}</p>
                          <p className="text-xs text-muted-foreground">{card.metric}</p>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {card.count} {copy.receiptsShort}
                        </p>
                      </div>
                    </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/60 bg-background/30">
            <CardHeader>
              <CardTitle>{copy.weekdayHourlyTitle}</CardTitle>
              <CardDescription>{copy.weekdayHourlyDescription}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-1 overflow-x-auto" style={{ gridTemplateColumns: "72px repeat(24, minmax(28px, 1fr))" }}>
                <div className="flex items-end text-[11px] font-medium text-muted-foreground">{copy.hourAxis}</div>
                {HOURS.map((hour) => (
                  <div key={hour} className="text-center text-[11px] text-muted-foreground">
                    {hour}
                  </div>
                ))}
                {matrixRows.map((row) => (
                  <FragmentRow
                    key={row.label}
                    label={row.label}
                    cells={row.cells.map((cell) => (
                        <div
                          key={`${row.label}-${cell.hour}-${cell.title}`}
                          aria-label={cell.ariaLabel}
                          className="h-8 rounded-md border border-border/40"
                          style={{ backgroundColor: cell.backgroundColor }}
                          title={cell.title}
                        />
                    ))}
                  />
                ))}
              </div>
            </CardContent>
          </Card>


          <Card className="overflow-hidden border-border/60 bg-background/30">
            <CardHeader className="gap-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                  <CardTitle>{copy.sankeyTitle}</CardTitle>
                  <CardDescription>{copy.sankeyDescription}</CardDescription>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void exportSankeyPng()}
                    disabled={exportingSankeyPng || !visibleSankey || visibleSankeyNodes.length === 0}
                  >
                    {exportingSankeyPng ? copy.sankeyExportingPng : copy.sankeyExportPng}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={exportSankeySvg}
                    disabled={!visibleSankey || visibleSankeyNodes.length === 0}
                  >
                    {copy.sankeyExportSvg}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={exportSankeyJson}
                    disabled={!visibleSankey}
                  >
                    {copy.sankeyExportJson}
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  {copy.sankeyWorkspaceViewLabel}
                </p>
                <Tabs value={sankeyWorkspaceView} onValueChange={(value) => startTransition(() => setSankeyWorkspaceView(value as SankeyWorkspaceView))}>
                  <TabsList className="h-auto w-full justify-start gap-2 rounded-[22px] border border-border/60 p-1.5 app-soft-surface">
                    <TabsTrigger value="current" onClick={() => startTransition(() => setSankeyWorkspaceView("current"))}>
                      {copy.sankeyWorkspaceCurrentView}
                    </TabsTrigger>
                    <TabsTrigger value="compare" disabled={!compareAvailable} onClick={() => startTransition(() => setSankeyWorkspaceView("compare"))}>
                      {copy.sankeyWorkspaceCompareView}
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
                {!compareAvailable ? (
                  <p className="text-sm text-muted-foreground">{copy.sankeyWorkspaceCompareUnavailable}</p>
                ) : null}
                {sankeyWorkspaceView === "compare" && workspace.kind !== "shared-group" && sharedGroupOptions.length > 0 ? (
                  <div className="max-w-sm space-y-2">
                    <Label htmlFor="reports-sankey-group">{copy.sankeyWorkspaceGroupLabel}</Label>
                    <Select value={compareGroupId} onValueChange={(value) => setSankeyCompareGroupId(value)}>
                      <SelectTrigger id="reports-sankey-group">
                        <SelectValue placeholder={copy.sankeyWorkspaceGroupLabel} />
                      </SelectTrigger>
                      <SelectContent>
                        {sharedGroupOptions.map((group) => (
                          <SelectItem key={group.value} value={group.value}>
                            {group.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                ) : null}
              </div>
              <Tabs value={effectiveSankeyMode} onValueChange={(value) => startTransition(() => setSankeyMode(value as ReportSankeyMode))}>
                <TabsList className="h-auto w-full justify-start gap-2 rounded-[22px] border border-border/60 p-1.5 app-soft-surface">
                  <TabsTrigger value="combined" disabled={sankeyWorkspaceView === "compare"} onClick={() => startTransition(() => setSankeyMode("combined"))}>
                    {copy.sankeyCombinedMode}
                  </TabsTrigger>
                  <TabsTrigger value="outflow_only" onClick={() => startTransition(() => setSankeyMode("outflow_only"))}>
                    {copy.sankeyOutflowMode}
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  {copy.sankeyTimeViewLabel}
                </p>
                <Tabs value={sankeyTimeView} onValueChange={(value) => startTransition(() => setSankeyTimeView(value as SankeyTimeView))}>
                  <TabsList className="h-auto w-full justify-start gap-2 rounded-[22px] border border-border/60 p-1.5 app-soft-surface">
                    <TabsTrigger value="report_range" onClick={() => startTransition(() => setSankeyTimeView("report_range"))}>
                      {copy.sankeyTimeRangeMode}
                    </TabsTrigger>
                    <TabsTrigger value="month" onClick={() => startTransition(() => setSankeyTimeView("month"))}>
                      {copy.sankeyTimeMonthMode}
                    </TabsTrigger>
                    <TabsTrigger value="year" onClick={() => startTransition(() => setSankeyTimeView("year"))}>
                      {copy.sankeyTimeYearMode}
                    </TabsTrigger>
                    <TabsTrigger value="year_average_month" onClick={() => startTransition(() => setSankeyTimeView("year_average_month"))}>
                      {copy.sankeyTimeAverageMonthMode}
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  {copy.sankeyBreakdownLabel}
                </p>
                <Tabs value={sankeyBreakdown} onValueChange={(value) => startTransition(() => setSankeyBreakdown(value as ReportSankeyBreakdown))}>
                  <TabsList className="h-auto w-full justify-start gap-2 rounded-[22px] border border-border/60 p-1.5 app-soft-surface">
                    <TabsTrigger value="merchant" onClick={() => startTransition(() => setSankeyBreakdown("merchant"))}>
                      {copy.sankeyBreakdownMerchants}
                    </TabsTrigger>
                    <TabsTrigger value="subcategory_only" onClick={() => startTransition(() => setSankeyBreakdown("subcategory_only"))}>
                      {copy.sankeyBreakdownSubcategories}
                    </TabsTrigger>
                    <TabsTrigger value="subcategory" onClick={() => startTransition(() => setSankeyBreakdown("subcategory"))}>
                      {copy.sankeyBreakdownSubcategoryMerchants}
                    </TabsTrigger>
                    <TabsTrigger value="subcategory_source" onClick={() => startTransition(() => setSankeyBreakdown("subcategory_source"))}>
                      {copy.sankeyBreakdownSubcategorySources}
                    </TabsTrigger>
                    <TabsTrigger value="source" onClick={() => startTransition(() => setSankeyBreakdown("source"))}>
                      {copy.sankeyBreakdownSources}
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                <div ref={sankeyCardRef} className="space-y-4 rounded-[30px] border border-border/60 bg-[linear-gradient(180deg,rgba(255,255,255,0.05),rgba(255,255,255,0.02))] p-4 shadow-[0_22px_70px_rgba(15,23,42,0.08)]">
                  {((sankey.isPending || sankeyViewIsRefreshing) && !activeSankey) ? (
                    <div className="space-y-3">
                      <p className="text-sm text-muted-foreground">{copy.sankeyLoading}</p>
                      <Skeleton className="h-12 rounded-2xl" />
                      <Skeleton className="h-[26rem] rounded-[28px]" />
                    </div>
                  ) : sankeyDirectionBlocked ? (
                    <p className="rounded-2xl border border-border/60 bg-background/60 px-4 py-4 text-sm text-muted-foreground">
                      {copy.sankeyDirectionEmpty}
                    </p>
                  ) : visibleSankeyNodes.length > 0 ? (
                    <SankeyFlowChart
                      key={sankeyRenderSignature}
                      ref={sankeySvgRef}
                      links={visibleSankeyLinks}
                      nodes={visibleSankeyNodes}
                      onLinkSelect={toggleSankeyLinkSelection}
                      onNodeSelect={toggleSankeyNodeSelection}
                      onNodeRenameRequest={startSankeyNodeRename}
                      selectedLinkKey={sankeySelection?.kind === "link" ? sankeySelection.linkKey : null}
                      selectedNodeId={sankeySelection?.kind === "node" ? sankeySelection.nodeId : null}
                      variant="comfortable"
                      formatValue={formatEurFromCents}
                    />
                  ) : sankeyHasEditedView && (labelledSankey?.nodes.length ?? 0) > 0 ? (
                    <p className="rounded-2xl border border-border/60 bg-background/60 px-4 py-4 text-sm text-muted-foreground">
                      {copy.sankeyAllHidden}
                    </p>
                  ) : (
                    <p className="rounded-2xl border border-border/60 bg-background/60 px-4 py-4 text-sm text-muted-foreground">
                      {copy.sankeyNoData}
                    </p>
                  )}
                </div>

                <div className="space-y-3">
                  <div className="rounded-[24px] border border-border/60 bg-background/60 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      {copy.sankeySummaryOutflow}
                    </p>
                    {sankeySummaryLoading ? (
                      <div className="mt-3 space-y-3">
                        <Skeleton className="h-10 w-36 rounded-xl" />
                        <Skeleton className="h-6 w-48 rounded-full" />
                      </div>
                    ) : (
                      <p className="mt-2 text-3xl font-semibold tracking-tight">
                        {formatEurFromCents(visibleSankey?.summary.total_outflow_cents ?? 0)}
                      </p>
                    )}
                    <div className="mt-3 flex flex-wrap gap-2">
                      <span className="rounded-full border border-border/60 bg-background/75 px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                        {copy.sankeySummaryWindow}: {sankeyWindowLabel}
                      </span>
                      <span className="rounded-full border border-border/60 bg-background/75 px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                        {sankeyWorkspaceView === "compare" ? copy.sankeyWorkspaceCompareView : copy.sankeyWorkspaceCurrentView}
                      </span>
                      <span className="rounded-full border border-border/60 bg-background/75 px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                        {sankeyTimeViewLabels[sankeyTimeView]}
                      </span>
                      {sankeyWorkspaceView === "compare" ? (
                        <span className="rounded-full border border-border/60 bg-background/75 px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                          {compareGroupLabel}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
                      <div className="rounded-2xl border border-border/60 bg-background/75 px-3 py-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{copy.sankeySummaryBasis}</p>
                        {sankeySummaryLoading ? <Skeleton className="mt-2 h-5 w-28 rounded-lg" /> : <p className="mt-1 text-sm font-semibold">{formatEurFromCents(visibleSankey?.summary.total_inflow_basis_cents ?? 0)}</p>}
                      </div>
                      <div className="rounded-2xl border border-border/60 bg-background/75 px-3 py-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{copy.sankeySummaryNodes}</p>
                        {sankeySummaryLoading ? <Skeleton className="mt-2 h-5 w-12 rounded-lg" /> : <p className="mt-1 text-sm font-semibold">{visibleSankey?.summary.node_count ?? 0}</p>}
                      </div>
                      <div className="rounded-2xl border border-border/60 bg-background/75 px-3 py-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{copy.sankeySummaryLinks}</p>
                        {sankeySummaryLoading ? <Skeleton className="mt-2 h-5 w-12 rounded-lg" /> : <p className="mt-1 text-sm font-semibold">{visibleSankey?.summary.link_count ?? 0}</p>}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-[24px] border border-border/60 bg-background/60 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                          {copy.sankeyEditorTitle}
                        </p>
                        <p className="mt-2 text-sm text-muted-foreground">
                          {copy.sankeyEditorDescription}
                        </p>
                      </div>
                      {sankeyHasEditedView ? (
                        <span className="rounded-full border border-border/60 bg-background/75 px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                          {copy.sankeyEditedNote}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-4 grid gap-2 sm:grid-cols-3 xl:grid-cols-1">
                      <div className="rounded-2xl border border-border/60 bg-background/75 px-3 py-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{copy.sankeyHiddenNodes}</p>
                        <p className="mt-1 text-sm font-semibold">{hiddenSankeyNodeIds.length}</p>
                      </div>
                      <div className="rounded-2xl border border-border/60 bg-background/75 px-3 py-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{copy.sankeyHiddenLinks}</p>
                        <p className="mt-1 text-sm font-semibold">{hiddenSankeyLinkKeys.length}</p>
                      </div>
                      <div className="rounded-2xl border border-border/60 bg-background/75 px-3 py-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">{copy.sankeyRenamedLabels}</p>
                        <p className="mt-1 text-sm font-semibold">{renamedLabelCount}</p>
                      </div>
                    </div>
                    <div className="mt-4 rounded-2xl border border-border/60 bg-background/75 px-3 py-3">
                      {selectedSankeyLabel ? (
                        <div className="space-y-3">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                              {selectedSankeyNode ? copy.sankeySelectedNode : copy.sankeySelectedFlow}
                            </p>
                            <p className="mt-1 text-sm font-semibold text-foreground/90">{selectedSankeyLabel}</p>
                            <p className="mt-1 text-xs text-muted-foreground">{formatEurFromCents(selectedSankeyValue)}</p>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Button type="button" variant="outline" size="sm" onClick={hideSelectedSankeyItem}>
                              {selectedSankeyNode ? copy.sankeyHideSelectedNode : copy.sankeyHideSelectedFlow}
                            </Button>
                            {selectedSankeyNode ? (
                              <Button type="button" variant="outline" size="sm" onClick={() => startSankeyNodeRename(selectedSankeyNode.id)}>
                                {copy.sankeyRenameNode}
                              </Button>
                            ) : null}
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setSankeySelection(null);
                                setSankeyRenameDraft(null);
                              }}
                            >
                              {copy.sankeyClearSelection}
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">{copy.sankeySelectionEmpty}</p>
                      )}
                    </div>
                    <div className="mt-4 rounded-2xl border border-border/60 bg-background/75 px-3 py-3">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                        {copy.sankeyRenameNode}
                      </p>
                      {sankeyRenameDraft ? (
                        <form
                          className="mt-3 space-y-3"
                          onSubmit={(event) => {
                            event.preventDefault();
                            saveSankeyNodeRename();
                          }}
                        >
                          <div className="space-y-2">
                            <Label htmlFor="sankey-rename-input" className="text-xs text-muted-foreground">{copy.sankeyRenameInputLabel}</Label>
                            <input
                              id="sankey-rename-input"
                              type="text"
                              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                              value={sankeyRenameDraft.value}
                              placeholder={copy.sankeyRenamePlaceholder}
                              onChange={(event) => setSankeyRenameDraft((current) => current ? { ...current, value: event.target.value } : current)}
                            />
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Button type="submit" variant="outline" size="sm">
                              {copy.sankeyRenameSave}
                            </Button>
                            <Button type="button" variant="ghost" size="sm" onClick={() => setSankeyRenameDraft(null)}>
                              {copy.sankeyRenameCancel}
                            </Button>
                          </div>
                        </form>
                      ) : selectedSankeyNode && selectedSankeyBaseNode ? (
                        <div className="mt-3 space-y-3">
                          <p className="text-sm text-muted-foreground">
                            {selectedSankeyLabel}
                          </p>
                          <Button type="button" variant="outline" size="sm" onClick={() => startSankeyNodeRename(selectedSankeyNode.id)}>
                            {copy.sankeyRenameNode}
                          </Button>
                        </div>
                      ) : (
                        <p className="mt-3 text-sm text-muted-foreground">{copy.sankeyRenameHint}</p>
                      )}
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-4 w-full"
                      onClick={resetEditedSankeyView}
                      disabled={!sankeyHasEditedView}
                    >
                      {copy.sankeyResetEditedView}
                    </Button>
                  </div>

                  <div className="rounded-[24px] border border-border/60 bg-background/60 p-4">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                      {effectiveSankeyMode === "combined" ? copy.sankeyCombinedMode : copy.sankeyOutflowMode}
                    </p>
                    <div className="mt-3 space-y-3">
                      {sankeyNotes.map((note) => (
                        <p key={note} className="rounded-2xl border border-border/60 bg-background/75 px-3 py-3 text-sm text-muted-foreground">
                          {note}
                        </p>
                      ))}
                      {sankeyExportStatus ? (
                        <p className="text-xs text-muted-foreground">{sankeyExportStatus}</p>
                      ) : null}
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>{t("pages.reports.patterns.merchantComparison")}</CardTitle>
              </CardHeader>
              <CardContent>
                {(data?.merchant_comparison ?? []).map((merchant) => (
                  <div key={merchant.merchant} className="flex justify-between gap-3 border-b border-border/60 py-2">
                    <span>{merchant.merchant}</span>
                    <span className="text-muted-foreground">{merchant.count} {copy.receiptsShort}</span>
                    <strong>{formatEurFromCents(merchant.amount_cents)}</strong>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>{t("pages.reports.patterns.insights")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {(data?.insights ?? []).map((insight, index) => <Insight key={index} insight={insight} />)}
              </CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-3">
        {(templates.data?.templates ?? []).map((template) => (
          <Card key={template.slug} className="app-dashboard-surface border-border/60">
            <CardHeader>
              <CardTitle>{t((`pages.reports.template.${template.slug}.title`) as never)}</CardTitle>
              <CardDescription>{t((`pages.reports.template.${template.slug}.description`) as never)}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button type="button" onClick={() => downloadFile(`${template.slug}.json`, JSON.stringify(template.payload, null, 2))}>
                {t("pages.reports.exportJson")}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );

  function Insight({ insight }: { insight: Record<string, unknown> }) {
    const kind = String(insight.kind || "");
    if (kind === "top_day") {
      return <InsightRow title={t("pages.reports.patterns.insight.topDay")} body={t("pages.reports.patterns.insight.topDayBody", { date: String(insight.date), amount: formatEurFromCents(Number(insight.amount_cents || 0)) })} />;
    }
    if (kind === "top_merchant") {
      return <InsightRow title={t("pages.reports.patterns.insight.topMerchant")} body={t("pages.reports.patterns.insight.topMerchantBody", { merchant: String(insight.merchant), amount: formatEurFromCents(Number(insight.amount_cents || 0)) })} />;
    }
    return <InsightRow title={t("pages.reports.patterns.insight.merchantGap")} body={t("pages.reports.patterns.insight.merchantGapBody", { merchant: String(insight.merchant || ""), amount: formatEurFromCents(Number(insight.amount_cents || 0)) })} />;
  }
}

function FragmentRow({ label, cells }: { label: string; cells: ReactNode[] }) {
  return (
    <>
      <div className="flex items-center text-sm font-medium">{label}</div>
      {cells}
    </>
  );
}

function MultiSelectDropdown({
  label,
  placeholder,
  emptyText,
  options,
  selectedValues,
  onChange,
  locale,
  clearLabel,
}: {
  label: string;
  placeholder: string;
  emptyText: string;
  options: MultiSelectOption[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
  locale: string;
  clearLabel: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    function handlePointerDown(event: MouseEvent) {
      if (containerRef.current?.contains(event.target as Node)) {
        return;
      }
      setOpen(false);
    }
    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, [open]);

  return (
    <div ref={containerRef} className="relative space-y-2">
      <Label>{label}</Label>
      <Button type="button" variant="outline" className="w-full justify-between" onClick={() => setOpen((current) => !current)}>
        <span className="truncate text-left">
          {formatSelectionSummary(locale, options, selectedValues, placeholder)}
        </span>
        <ChevronDown className="h-4 w-4 opacity-70" />
      </Button>
      {open ? (
        <div className="absolute z-20 mt-2 max-h-72 w-full overflow-y-auto rounded-xl border border-border/70 bg-popover/95 p-1.5 shadow-2xl ring-1 ring-white/5 supports-[backdrop-filter]:bg-popover/85 supports-[backdrop-filter]:backdrop-blur-xl">
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
            <button
              type="button"
              className="text-xs font-medium text-muted-foreground transition hover:text-foreground disabled:opacity-50"
              disabled={selectedValues.length === 0}
              onClick={() => onChange([])}
            >
              {clearLabel}
            </button>
          </div>
          {options.length === 0 ? (
            <div className="px-2 py-2 text-sm text-muted-foreground">{emptyText}</div>
          ) : (
            options.map((option) => {
              const checked = selectedValues.includes(option.value);
              return (
                <label key={option.value} className="flex cursor-pointer items-start gap-3 rounded-md px-2.5 py-2 text-sm transition hover:bg-accent/80">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => {
                      if (event.target.checked) {
                        onChange(checked ? selectedValues : [...selectedValues, option.value]);
                        return;
                      }
                      onChange(selectedValues.filter((value) => value !== option.value));
                    }}
                  />
                  <span className="flex min-w-0 flex-col">
                    <span>{option.label}</span>
                    {option.description ? <span className="text-xs text-muted-foreground">{option.description}</span> : null}
                  </span>
                </label>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}

function SelectBox({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent>{children}</SelectContent>
      </Select>
    </div>
  );
}

function InsightRow({ title, body }: { title: string; body: string }) {
  return <div className="rounded-lg border border-border/60 p-3"><p className="font-medium">{title}</p><p className="text-sm text-muted-foreground">{body}</p></div>;
}

function ReportDateRangePanel({
  locale,
  copy,
  fromDate,
  toDate,
  years,
  onSelectPreset,
  onSelectRange,
}: {
  locale: string;
  copy: {
    dateRangeTitle: string;
    dateRangeDescription: string;
    currentRange: string;
    lastWeek: string;
    lastYear: string;
    allTime: string;
    monthLabel: string;
    yearLabel: string;
    customFrom: string;
    customTo: string;
    pickYear: string;
  };
  fromDate: string;
  toDate: string;
  years: number[];
  onSelectPreset: (preset: DateRangePreset) => void;
  onSelectRange: (fromDate: string, toDate: string) => void;
}) {
  const today = new Date();
  const currentMonthValue = fromDate.slice(0, 7);
  const currentYearValue = fromDate.slice(0, 4);
  const formatter = new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  });
  const currentRangeLabel = `${formatter.format(new Date(fromDate))} - ${formatter.format(new Date(toDate))}`;

  return (
    <div className="rounded-2xl border border-border/60 bg-background/40 p-4">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold">{copy.dateRangeTitle}</p>
          <p className="text-sm text-muted-foreground">{copy.dateRangeDescription}</p>
        </div>
        <div className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{copy.currentRange}:</span> {currentRangeLabel}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => onSelectPreset("this_week")}>
          {locale === "de" ? "Diese Woche" : "This week"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            const end = shiftDays(startOfWeek(today), -1);
            const start = shiftDays(startOfWeek(today), -7);
            onSelectRange(formatDateOnly(start), formatDateOnly(end));
          }}
        >
          {copy.lastWeek}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => onSelectPreset("last_month")}>
          {locale === "de" ? "Letzter Monat" : "Last month"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            const previousYear = today.getFullYear() - 1;
            const bounds = yearBounds(previousYear);
            onSelectRange(bounds.fromDate, bounds.toDate);
          }}
        >
          {copy.lastYear}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={years.length === 0}
          onClick={() => {
            if (years.length === 0) {
              return;
            }
            const firstYear = Math.min(...years);
            onSelectRange(`${firstYear}-01-01`, formatDateOnly(today));
          }}
        >
          {copy.allTime}
        </Button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <div className="space-y-2">
          <Label>{copy.monthLabel}</Label>
          <input
            type="month"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={currentMonthValue}
            onChange={(event) => {
              const next = monthBounds(event.target.value);
              if (next) {
                onSelectRange(next.fromDate, next.toDate);
              }
            }}
          />
        </div>
        <div className="space-y-2">
          <Label>{copy.yearLabel}</Label>
          <select
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={years.includes(Number(currentYearValue)) ? currentYearValue : ""}
            onChange={(event) => {
              if (!event.target.value) {
                return;
              }
              const bounds = yearBounds(Number(event.target.value));
              onSelectRange(bounds.fromDate, bounds.toDate);
            }}
          >
            <option value="">{copy.pickYear}</option>
            {years.map((year) => (
              <option key={year} value={String(year)}>
                {year}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label>{copy.customFrom}</Label>
          <input
            type="date"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={fromDate}
            onChange={(event) => onSelectRange(event.target.value, toDate)}
          />
        </div>
        <div className="space-y-2">
          <Label>{copy.customTo}</Label>
          <input
            type="date"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={toDate}
            onChange={(event) => onSelectRange(fromDate, event.target.value)}
          />
        </div>
      </div>
    </div>
  );
}
