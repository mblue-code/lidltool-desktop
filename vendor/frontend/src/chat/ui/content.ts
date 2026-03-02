import { ChatUiSpec, tryParseChatUiSpec } from "@/chat/ui/spec";

const UI_SPEC_MARKER_PATTERN = /\[\[UI_SPEC_V1:([A-Za-z0-9+/=]+)\]\]/g;

function decodeBase64Utf8(base64Value: string): string | null {
  try {
    const binary = globalThis.atob(base64Value);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
}

function extractUiSpecsFromText(text: string): ChatUiSpec[] {
  const specs: ChatUiSpec[] = [];
  let match = UI_SPEC_MARKER_PATTERN.exec(text);
  while (match) {
    const encoded = match[1];
    const decoded = decodeBase64Utf8(encoded);
    if (decoded) {
      try {
        const maybeSpec = JSON.parse(decoded) as unknown;
        const spec = tryParseChatUiSpec(maybeSpec);
        if (spec) {
          specs.push(spec);
        }
      } catch {
        // Ignore malformed JSON markers.
      }
    }
    match = UI_SPEC_MARKER_PATTERN.exec(text);
  }
  UI_SPEC_MARKER_PATTERN.lastIndex = 0;
  return specs;
}

function stripUiSpecMarkers(text: string): string {
  return text.replace(UI_SPEC_MARKER_PATTERN, "").replace(/\n{3,}/g, "\n\n").trim();
}

function readPartText(part: unknown): string {
  if (!part || typeof part !== "object") {
    return "";
  }
  const candidate = (part as { type?: unknown; text?: unknown }).type;
  const text = (part as { text?: unknown }).text;
  if (candidate === "text" && typeof text === "string") {
    return text;
  }
  return "";
}

function parseUiSpecCandidate(candidate: unknown): ChatUiSpec | null {
  const parsed = tryParseChatUiSpec(candidate);
  return parsed ?? null;
}

function dedupeUiSpecs(specs: ChatUiSpec[]): ChatUiSpec[] {
  const byKey = new Map<string, ChatUiSpec>();
  for (const spec of specs) {
    const key = JSON.stringify(spec);
    if (!byKey.has(key)) {
      byKey.set(key, spec);
    }
  }
  return Array.from(byKey.values());
}

export function messageTextFromContent(content: unknown, separator = ""): string {
  if (typeof content === "string") {
    return stripUiSpecMarkers(content);
  }
  if (!Array.isArray(content)) {
    return "";
  }
  return content
    .map((part) => readPartText(part))
    .filter(Boolean)
    .join(separator)
    .replace(UI_SPEC_MARKER_PATTERN, "")
    .trim();
}

export function extractUiSpecsFromContent(content: unknown): ChatUiSpec[] {
  if (Array.isArray(content)) {
    const specs: ChatUiSpec[] = [];
    for (const part of content) {
      if (!part || typeof part !== "object") {
        continue;
      }
      const text = readPartText(part);
      if (text) {
        specs.push(...extractUiSpecsFromText(text));
      }
      const typedPart = part as {
        type?: unknown;
        spec?: unknown;
        ui?: unknown;
        value?: unknown;
      };
      const type = typeof typedPart.type === "string" ? typedPart.type : "";
      if (type !== "ui_spec" && type !== "ui") {
        continue;
      }
      const spec = parseUiSpecCandidate(typedPart.spec ?? typedPart.ui ?? typedPart.value);
      if (spec) {
        specs.push(spec);
      }
    }
    return dedupeUiSpecs(specs);
  }

  if (typeof content === "string") {
    return dedupeUiSpecs(extractUiSpecsFromText(content));
  }

  const standalone = parseUiSpecCandidate(content);
  return standalone ? [standalone] : [];
}

export function extractUiSpecsFromDetails(details: unknown): ChatUiSpec[] {
  if (!details || typeof details !== "object") {
    return [];
  }
  const typedDetails = details as {
    spec?: unknown;
    ui_spec?: unknown;
    uiSpecs?: unknown;
  };
  const specs: ChatUiSpec[] = [];
  const direct = parseUiSpecCandidate(typedDetails.spec ?? typedDetails.ui_spec);
  if (direct) {
    specs.push(direct);
  }
  if (Array.isArray(typedDetails.uiSpecs)) {
    for (const candidate of typedDetails.uiSpecs) {
      const parsed = parseUiSpecCandidate(candidate);
      if (parsed) {
        specs.push(parsed);
      }
    }
  }
  return dedupeUiSpecs(specs);
}
