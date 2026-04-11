import { ReactNode } from "react";

import { ExportableChatUiSpec } from "@/chat/ui/ExportableChatUiSpec";
import { ChatUiSpec } from "@/chat/ui/spec";
import { cn } from "@/lib/utils";

const GENERIC_RENDER_UI_ACK_PATTERN = /^Rendered \d+ UI element\(s\)\.?$/;

function hasMeaningfulToolText(content: string, uiSpecs: ChatUiSpec[]): boolean {
  const trimmed = content.trim();
  if (!trimmed) {
    return false;
  }
  if (uiSpecs.length > 0 && GENERIC_RENDER_UI_ACK_PATTERN.test(trimmed)) {
    return false;
  }
  return true;
}

function summarizeToolOutput(content: string, fallbackLabel: string): string {
  const trimmed = content.trim();
  if (!trimmed) {
    return fallbackLabel;
  }

  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object") {
      if ("message" in parsed && typeof parsed.message === "string" && parsed.message.trim()) {
        return parsed.message.trim();
      }
      if ("detail" in parsed && typeof parsed.detail === "string" && parsed.detail.trim()) {
        return parsed.detail.trim();
      }
      if (Array.isArray(parsed) && parsed.length > 0) {
        return fallbackLabel;
      }
    }
  } catch {
    // Not JSON; fall through to plain-text summary.
  }

  const firstLine = trimmed.split(/\r?\n/, 1)[0]?.trim() ?? fallbackLabel;
  if (firstLine.length <= 120) {
    return firstLine;
  }
  return `${firstLine.slice(0, 117)}...`;
}

export function ChatToolResult({
  header,
  uiSpecs,
  content,
  inlineLabel,
  rawOutputLabel,
  noOutputLabel,
  className
}: {
  header: ReactNode;
  uiSpecs: ChatUiSpec[];
  content: string;
  inlineLabel: string;
  rawOutputLabel: string;
  noOutputLabel: string;
  className?: string;
}) {
  const showTextPayload = hasMeaningfulToolText(content, uiSpecs);
  const toolSummary = showTextPayload ? summarizeToolOutput(content, rawOutputLabel) : noOutputLabel;

  return (
    <section className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="rounded-full border border-border/70 bg-background/80 px-2 py-0.5 font-medium">
          {header}
        </span>
        {uiSpecs.length > 0 ? <span>{inlineLabel}</span> : null}
      </div>

      {uiSpecs.length > 0 ? (
        <div className="space-y-3">
          {uiSpecs.map((spec, index) => (
            <ExportableChatUiSpec key={`ui-${index}`} spec={spec} />
          ))}
        </div>
      ) : null}

      {showTextPayload ? (
        <details className="rounded-lg border border-dashed border-border/70 bg-background/40 p-2">
          <summary className="cursor-pointer list-none text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium text-foreground/85">{toolSummary}</span>
              <span className="text-muted-foreground">{rawOutputLabel}</span>
            </div>
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs">{content}</pre>
        </details>
      ) : null}

      {!showTextPayload && uiSpecs.length === 0 ? (
        <p className="rounded-lg bg-background/60 px-2 py-1.5 text-xs text-muted-foreground">{noOutputLabel}</p>
      ) : null}
    </section>
  );
}
