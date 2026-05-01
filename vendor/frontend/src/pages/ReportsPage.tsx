import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { fetchReportPatterns, fetchReportTemplates } from "@/api/reports";
import { useDateRangeContext } from "@/app/date-range-context";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/i18n";
import { directionLabel, financeCategoryLabel } from "@/lib/category-presentation";
import { formatEurFromCents } from "@/utils/format";

function downloadFile(filename: string, content: string) {
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function ReportsPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const { t } = useI18n();
  const [merchantInput, setMerchantInput] = useState("");
  const [category, setCategory] = useState("all");
  const [direction, setDirection] = useState("all");
  const [valueMode, setValueMode] = useState("amount");
  const merchants = merchantInput.split(",").map((value) => value.trim()).filter(Boolean).slice(0, 2);
  const templates = useQuery({ queryKey: ["reports-page", fromDate, toDate], queryFn: () => fetchReportTemplates(fromDate, toDate) });
  const patterns = useQuery({ queryKey: ["reports-patterns", fromDate, toDate, merchants, category, direction, valueMode], queryFn: () => fetchReportPatterns({ fromDate, toDate, merchants, financeCategoryId: category === "all" ? undefined : category, direction: direction === "all" ? undefined : direction, valueMode }) });
  const data = patterns.data;
  const maxDaily = Math.max(1, ...(data?.daily_heatmap ?? []).map((point) => valueMode === "count" ? point.count : point.amount_cents));
  const maxMatrix = Math.max(1, ...(data?.weekday_hour_matrix ?? []).map((point) => valueMode === "count" ? point.count : point.amount_cents));

  return (
    <div className="space-y-6">
      <PageHeader title={t("pages.reports.title")} description={t("pages.reports.description")} />
      <Card className="app-dashboard-surface border-border/60">
        <CardHeader><CardTitle className="flex items-center gap-2"><Activity className="h-4 w-4" />{t("pages.reports.patterns.title")}</CardTitle><CardDescription>{t("pages.reports.patterns.description")}</CardDescription></CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="space-y-2"><Label>{t("pages.reports.patterns.merchants")}</Label><Input value={merchantInput} onChange={(event) => setMerchantInput(event.target.value)} placeholder={t("pages.reports.patterns.merchantsPlaceholder")} /></div>
            <SelectBox label={t("pages.transactions.filter.category")} value={category} onChange={setCategory}><SelectItem value="all">{t("pages.transactions.allCategories")}</SelectItem>{["groceries", "housing", "insurance", "credit", "mobility", "car", "investment", "subscriptions", "income", "fees", "tax", "other"].map((value) => <SelectItem key={value} value={value}>{financeCategoryLabel(value, t)}</SelectItem>)}</SelectBox>
            <SelectBox label={t("pages.transactions.filter.direction")} value={direction} onChange={setDirection}><SelectItem value="all">{t("pages.transactions.allDirections")}</SelectItem>{["outflow", "inflow", "transfer", "neutral"].map((value) => <SelectItem key={value} value={value}>{directionLabel(value, t)}</SelectItem>)}</SelectBox>
            <SelectBox label={t("pages.reports.patterns.valueMode")} value={valueMode} onChange={setValueMode}><SelectItem value="amount">{t("pages.reports.patterns.valueMode.amount")}</SelectItem><SelectItem value="count">{t("pages.reports.patterns.valueMode.count")}</SelectItem></SelectBox>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <div><h3 className="mb-3 text-sm font-semibold">{t("pages.reports.patterns.dailyHeatmap")}</h3><div className="grid grid-cols-[repeat(auto-fill,minmax(18px,1fr))] gap-1">{(data?.daily_heatmap ?? []).map((point) => { const value = valueMode === "count" ? point.count : point.amount_cents; return <div key={point.date} className="aspect-square rounded-[3px] bg-emerald-500" style={{ opacity: Math.max(0.14, value / maxDaily) }} />; })}</div></div>
            <div><h3 className="mb-3 text-sm font-semibold">{t("pages.reports.patterns.weekdayHour")}</h3><div className="grid gap-1" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>{Array.from({ length: 168 }).map((_, index) => { const weekday = Math.floor(index / 24); const hour = index % 24; const point = data?.weekday_hour_matrix.find((item) => item.weekday === weekday && item.hour === hour); const value = point ? (valueMode === "count" ? point.count : point.amount_cents) : 0; return <div key={index} className="h-3 rounded-[2px] bg-sky-500" style={{ opacity: value ? Math.max(0.14, value / maxMatrix) : 0.08 }} />; })}</div></div>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader><CardTitle>{t("pages.reports.patterns.merchantComparison")}</CardTitle></CardHeader><CardContent>{(data?.merchant_comparison ?? []).map((merchant) => <div key={merchant.merchant} className="flex justify-between border-b border-border/60 py-2"><span>{merchant.merchant}</span><span>{merchant.count}</span><strong>{formatEurFromCents(merchant.amount_cents)}</strong></div>)}</CardContent></Card>
            <Card><CardHeader><CardTitle>{t("pages.reports.patterns.insights")}</CardTitle></CardHeader><CardContent className="space-y-3">{(data?.insights ?? []).map((insight, index) => <Insight key={index} insight={insight} />)}</CardContent></Card>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-3">
        {(templates.data?.templates ?? []).map((template) => <Card key={template.slug} className="app-dashboard-surface border-border/60"><CardHeader><CardTitle>{t(("pages.reports.template." + template.slug + ".title") as any)}</CardTitle><CardDescription>{t(("pages.reports.template." + template.slug + ".description") as any)}</CardDescription></CardHeader><CardContent><Button type="button" onClick={() => downloadFile(template.slug + ".json", JSON.stringify(template.payload, null, 2))}>{t("pages.reports.exportJson")}</Button></CardContent></Card>)}
      </div>
    </div>
  );

  function Insight({ insight }: { insight: Record<string, unknown> }) {
    const kind = String(insight.kind || "");
    if (kind === "top_day") return <InsightRow title={t("pages.reports.patterns.insight.topDay")} body={t("pages.reports.patterns.insight.topDayBody", { date: String(insight.date), amount: formatEurFromCents(Number(insight.amount_cents || 0)) })} />;
    if (kind === "top_merchant") return <InsightRow title={t("pages.reports.patterns.insight.topMerchant")} body={t("pages.reports.patterns.insight.topMerchantBody", { merchant: String(insight.merchant), amount: formatEurFromCents(Number(insight.amount_cents || 0)) })} />;
    return <InsightRow title={t("pages.reports.patterns.insight.merchantGap")} body={t("pages.reports.patterns.insight.merchantGapBody", { merchant: String(insight.merchant || ""), amount: formatEurFromCents(Number(insight.amount_cents || 0)) })} />;
  }
}

function SelectBox({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return <div className="space-y-2"><Label>{label}</Label><Select value={value} onValueChange={onChange}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{children}</SelectContent></Select></div>;
}

function InsightRow({ title, body }: { title: string; body: string }) {
  return <div className="rounded-lg border border-border/60 p-3"><p className="font-medium">{title}</p><p className="text-sm text-muted-foreground">{body}</p></div>;
}
