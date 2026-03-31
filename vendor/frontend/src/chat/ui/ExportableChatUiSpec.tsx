import { useMemo, useRef, useState } from "react";
import { toPng } from "html-to-image";

import { ChatUiRenderer } from "@/chat/ui/ChatUiRenderer";
import { ChatUiSpec } from "@/chat/ui/spec";
import { Button } from "@/components/ui/button";
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
  const fallback = "#ffffff";
  if (typeof window === "undefined") {
    return fallback;
  }
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--background").trim();
  if (!raw) {
    return fallback;
  }
  return raw.startsWith("#") ? raw : `hsl(${raw})`;
}

export function ExportableChatUiSpec({
  spec,
  className
}: {
  spec: ChatUiSpec;
  className?: string;
}) {
  const exportNodeRef = useRef<HTMLDivElement | null>(null);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [exportingPng, setExportingPng] = useState(false);
  const baseFilename = useMemo(() => buildFilenameBase(spec), [spec]);

  function handleDownloadJson(): void {
    const filename = `${baseFilename}.json`;
    const downloaded = downloadBlob(
      filename,
      "application/json;charset=utf-8",
      `${JSON.stringify(spec, null, 2)}\n`
    );
    setExportStatus(downloaded ? `Downloaded ${filename}.` : "Download API unavailable in this browser.");
  }

  async function handleDownloadPng(): Promise<void> {
    if (!exportNodeRef.current) {
      setExportStatus("Render not ready for PNG export.");
      return;
    }
    setExportingPng(true);
    try {
      const dataUrl = await toPng(exportNodeRef.current, {
        cacheBust: true,
        pixelRatio: 2,
        backgroundColor: themeBackgroundColor()
      });
      const filename = `${baseFilename}.png`;
      downloadDataUrl(filename, dataUrl);
      setExportStatus(`Downloaded ${filename}.`);
    } catch (error) {
      setExportStatus(error instanceof Error ? error.message : "Failed to export PNG.");
    } finally {
      setExportingPng(false);
    }
  }

  return (
    <section className={cn("space-y-2", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => void handleDownloadPng()} disabled={exportingPng}>
          {exportingPng ? "Exporting PNG..." : "Download PNG"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={handleDownloadJson}>
          Download JSON
        </Button>
        {exportStatus ? <p className="text-xs text-muted-foreground">{exportStatus}</p> : null}
      </div>
      <div ref={exportNodeRef}>
        <ChatUiRenderer spec={spec} />
      </div>
    </section>
  );
}
