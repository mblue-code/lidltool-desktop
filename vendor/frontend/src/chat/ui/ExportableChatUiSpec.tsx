import { useMemo, useRef, useState } from "react";
import { toPng } from "html-to-image";

import { ChatUiRenderer } from "@/chat/ui/ChatUiRenderer";
import { ChatUiSpec } from "@/chat/ui/spec";
import { readChatThemeColors } from "@/chat/ui/themeColors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";

function downloadBlob(filename: string, type: string, content: string): boolean {
  if (typeof URL.createObjectURL !== "function") {
    return false;
  }
  const blob = new Blob([content], { type });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
  return true;
}

function downloadDataUrl(filename: string, dataUrl: string): boolean {
  const anchor = document.createElement("a");
  anchor.href = dataUrl;
  anchor.download = filename;
  anchor.click();
  return true;
}

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48);
}

function firstElementLabel(spec: ChatUiSpec): string {
  const first = spec.elements[0];
  if (!first) {
    return "render";
  }
  const titleCandidate = (first.props as { title?: unknown }).title;
  if (typeof titleCandidate === "string" && titleCandidate.trim()) {
    return titleCandidate;
  }
  return first.type;
}

function buildFilenameBase(spec: ChatUiSpec): string {
  const label = slugify(firstElementLabel(spec));
  return label ? `chat_ui_${label}` : "chat_ui_render";
}

function themeBackgroundColor(): string {
  return readChatThemeColors().background;
}

const ELEMENT_TYPE_KEYS: Record<ChatUiSpec["elements"][number]["type"], string> = {
  MetricCard: "chat.shared.elementType.metric",
  Table: "chat.shared.elementType.table",
  LineChart: "chat.shared.elementType.chart",
  BarChart: "chat.shared.elementType.chart",
  PieChart: "chat.shared.elementType.chart",
  SankeyChart: "chat.shared.elementType.sankey",
  Callout: "chat.shared.elementType.callout"
};

export function ExportableChatUiSpec({
  spec,
  className
}: {
  spec: ChatUiSpec;
  className?: string;
}) {
  const { t } = useI18n();
  const exportNodeRef = useRef<HTMLDivElement | null>(null);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [exportingPng, setExportingPng] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [exportSurfaceMounted, setExportSurfaceMounted] = useState(false);
  const baseFilename = useMemo(() => buildFilenameBase(spec), [spec]);
  const elementTypeLabels = useMemo(
    () =>
      Array.from(
        new Set(spec.elements.map((element) => t(ELEMENT_TYPE_KEYS[element.type] as Parameters<typeof t>[0])))
      ),
    [spec.elements, t]
  );
  const artifactTitle = useMemo(() => firstElementLabel(spec), [spec]);

  function handleDownloadJson(): void {
    const filename = `${baseFilename}.json`;
    const downloaded = downloadBlob(
      filename,
      "application/json;charset=utf-8",
      `${JSON.stringify(spec, null, 2)}\n`
    );
    setExportStatus(
      downloaded
        ? t("chat.shared.downloadedFile", { filename })
        : t("chat.shared.downloadUnavailable")
    );
  }

  async function handleDownloadPng(): Promise<void> {
    setExportingPng(true);
    try {
      setExportSurfaceMounted(true);
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      if (!exportNodeRef.current) {
        setExportStatus(t("chat.shared.renderNotReady"));
        return;
      }
      const width = Math.ceil(exportNodeRef.current.scrollWidth);
      const height = Math.ceil(exportNodeRef.current.scrollHeight);
      const dataUrl = await toPng(exportNodeRef.current, {
        cacheBust: true,
        pixelRatio: 2,
        backgroundColor: themeBackgroundColor(),
        width,
        height,
        canvasWidth: width * 2,
        canvasHeight: height * 2
      });
      const filename = `${baseFilename}.png`;
      downloadDataUrl(filename, dataUrl);
      setExportStatus(t("chat.shared.downloadedFile", { filename }));
    } catch (error) {
      setExportStatus(error instanceof Error ? error.message : t("chat.shared.exportPngFailed"));
    } finally {
      setExportSurfaceMounted(false);
      setExportingPng(false);
    }
  }

  return (
    <section className={cn("space-y-2", className)}>
      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card/70 shadow-sm backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border/70 bg-background/45 px-3 py-3">
          <div className="min-w-0 space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              {t("chat.shared.visualArtifact")}
            </p>
            <h4 className="truncate text-sm font-semibold">{artifactTitle}</h4>
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{t("chat.shared.artifactSummary", { count: spec.elements.length })}</span>
              {elementTypeLabels.map((label) => (
                <span
                  key={label}
                  className="rounded-full border border-border/70 bg-background/75 px-2 py-0.5 text-[11px] font-medium text-foreground/85"
                >
                  {label}
                </span>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setPreviewOpen(true)}>
              {t("chat.shared.openLarge")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleDownloadPng()}
              disabled={exportingPng}
            >
              {exportingPng ? t("chat.shared.exportingPng") : t("chat.shared.downloadPng")}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={handleDownloadJson}>
              {t("chat.shared.downloadJson")}
            </Button>
          </div>
        </div>

        <div className="space-y-3 p-3">
          <div
            className="rounded-xl border border-border/60 bg-background/95 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
            style={{
              backgroundColor: readChatThemeColors().background,
              color: readChatThemeColors().foreground
            }}
          >
            <ChatUiRenderer spec={spec} variant="inline" />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">{t("chat.shared.artifactPreviewHint")}</p>
            {exportStatus ? <p className="text-xs text-muted-foreground">{exportStatus}</p> : null}
          </div>
        </div>
      </div>

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-h-[94vh] overflow-hidden sm:max-w-[92vw] xl:max-w-[1400px]">
          <DialogHeader>
            <DialogTitle>{artifactTitle}</DialogTitle>
            <DialogDescription>{t("chat.shared.largePreviewDescription")}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void handleDownloadPng()}
              disabled={exportingPng}
            >
              {exportingPng ? t("chat.shared.exportingPng") : t("chat.shared.downloadPng")}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={handleDownloadJson}>
              {t("chat.shared.downloadJson")}
            </Button>
          </div>
          <div className="overflow-auto rounded-xl border border-border/70 bg-background/95 p-4">
            <ChatUiRenderer spec={spec} variant="large" />
          </div>
        </DialogContent>
      </Dialog>
      {exportSurfaceMounted ? (
        <div
          aria-hidden="true"
          className="pointer-events-none fixed left-[-20000px] top-0 inline-block w-max max-w-none overflow-visible opacity-0"
        >
          <div
            ref={exportNodeRef}
            className="inline-block rounded-xl border border-border/60 bg-background/95 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
            style={{
              backgroundColor: readChatThemeColors().background,
              color: readChatThemeColors().foreground
            }}
          >
            <ChatUiRenderer spec={spec} variant="export" />
          </div>
        </div>
      ) : null}
    </section>
  );
}
