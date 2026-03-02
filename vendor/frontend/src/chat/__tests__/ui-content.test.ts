import { describe, expect, it } from "vitest";

import {
  extractUiSpecsFromContent,
  extractUiSpecsFromDetails,
  messageTextFromContent
} from "@/chat/ui/content";

function encodeBase64Utf8(input: string): string {
  const bytes = new TextEncoder().encode(input);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return globalThis.btoa(binary);
}

describe("chat ui content parsing", () => {
  it("extracts encoded UI specs and removes marker text", () => {
    const spec = {
      version: "v1",
      layout: "stack",
      elements: [{ type: "MetricCard", props: { title: "Total", value: 123 } }]
    };
    const encoded = encodeBase64Utf8(JSON.stringify(spec));

    const content = [
      { type: "text", text: "Summary before chart." },
      { type: "text", text: `[[UI_SPEC_V1:${encoded}]]` }
    ];

    const specs = extractUiSpecsFromContent(content);
    expect(specs).toHaveLength(1);
    expect(specs[0]?.elements[0]?.type).toBe("MetricCard");

    const text = messageTextFromContent(content, "\n");
    expect(text).toContain("Summary before chart.");
    expect(text).not.toContain("UI_SPEC_V1");
  });

  it("supports direct ui_spec content parts", () => {
    const content = [
      {
        type: "ui_spec",
        spec: {
          version: "v1",
          layout: "grid",
          elements: [{ type: "Callout", props: { tone: "info", title: "Hello", body: "World" } }]
        }
      }
    ];

    const specs = extractUiSpecsFromContent(content);
    expect(specs).toHaveLength(1);
    expect(specs[0]?.layout).toBe("grid");
  });

  it("extracts ui specs from tool details", () => {
    const details = {
      ui_spec: {
        version: "v1",
        layout: "stack",
        elements: [{ type: "Callout", props: { tone: "success", title: "OK", body: "Done" } }]
      }
    };

    const specs = extractUiSpecsFromDetails(details);
    expect(specs).toHaveLength(1);
    expect(specs[0]?.elements[0]?.type).toBe("Callout");
  });
});
