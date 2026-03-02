import {
  extractUiSpecsFromContent,
  extractUiSpecsFromDetails,
  messageTextFromContent
} from "@/chat/ui/content";

function dedupeByJson<T>(values: T[]): T[] {
  const byKey = new Map<string, T>();
  for (const value of values) {
    const key = JSON.stringify(value);
    if (!byKey.has(key)) {
      byKey.set(key, value);
    }
  }
  return Array.from(byKey.values());
}

function normalizeToolResultContent(message: any): Array<Record<string, unknown>> {
  const text = messageTextFromContent(message?.content, "\n");
  const uiSpecs = dedupeByJson([
    ...extractUiSpecsFromContent(message?.content),
    ...extractUiSpecsFromDetails(message?.details)
  ]);

  const content: Array<Record<string, unknown>> = [];
  if (text) {
    content.push({ type: "text", text });
  }
  for (const spec of uiSpecs) {
    content.push({ type: "ui_spec", spec });
  }
  return content;
}

export function normalizeRuntimeMessagesForPersistence(messages: any[]): any[] {
  return messages.map((message) => {
    if (!message || typeof message !== "object") {
      return message;
    }
    if (message.role !== "toolResult") {
      return message;
    }
    return {
      ...message,
      content: normalizeToolResultContent(message)
    };
  });
}

export function sanitizeRuntimeMessagesForModel(messages: any[]): any[] {
  return messages.map((message) => {
    if (!message || typeof message !== "object") {
      return message;
    }
    if (message.role !== "toolResult") {
      return message;
    }
    const text = messageTextFromContent(message.content, "\n");
    return {
      ...message,
      content: text ? [{ type: "text", text }] : []
    };
  });
}
