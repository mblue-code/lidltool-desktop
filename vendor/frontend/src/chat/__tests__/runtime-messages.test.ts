import { describe, expect, it } from "vitest";

import {
  normalizeRuntimeMessagesForPersistence,
  sanitizeRuntimeMessagesForModel
} from "@/chat/ui/runtime-messages";

describe("runtime message normalization", () => {
  it("persists ui_spec parts from tool details", () => {
    const runtimeMessages = [
      {
        role: "toolResult",
        toolName: "render_ui",
        content: [{ type: "text", text: "Rendered 1 UI element(s)." }],
        details: {
          ui_spec: {
            version: "v1",
            layout: "stack",
            elements: [{ type: "MetricCard", props: { title: "Spend", value: 123 } }]
          }
        }
      }
    ];

    const normalized = normalizeRuntimeMessagesForPersistence(runtimeMessages as any[]);
    const first = normalized[0] as { content: Array<{ type: string; text?: string; spec?: unknown }> };
    expect(first.content[0]?.type).toBe("text");
    expect(first.content[1]?.type).toBe("ui_spec");
    expect((first.content[1]?.spec as any)?.version).toBe("v1");
  });

  it("strips non-text tool payloads from model context", () => {
    const runtimeMessages = [
      {
        role: "toolResult",
        toolName: "render_ui",
        content: [
          { type: "text", text: "Rendered chart." },
          {
            type: "ui_spec",
            spec: {
              version: "v1",
              layout: "stack",
              elements: [{ type: "MetricCard", props: { title: "Spend", value: 123 } }]
            }
          }
        ]
      }
    ];

    const sanitized = sanitizeRuntimeMessagesForModel(runtimeMessages as any[]);
    const first = sanitized[0] as { content: Array<{ type: string; text?: string }> };
    expect(first.content).toEqual([{ type: "text", text: "Rendered chart." }]);
  });
});
