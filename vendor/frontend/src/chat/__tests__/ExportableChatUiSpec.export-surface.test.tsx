import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { ExportableChatUiSpec } from "@/chat/ui/ExportableChatUiSpec";

const { toPngMock, chatUiRendererMock } = vi.hoisted(() => ({
  toPngMock: vi.fn(async () => "data:image/png;base64,AAAA"),
  chatUiRendererMock: vi.fn(({ spec, variant = "inline" }: { spec: { elements: unknown[] }; variant?: string }) => (
    <div data-testid="chat-ui-renderer" data-variant={variant} data-element-count={spec.elements.length}>
      {variant}
    </div>
  ))
}));

vi.mock("html-to-image", () => ({
  toPng: toPngMock
}));

vi.mock("@/chat/ui/ChatUiRenderer", () => ({
  ChatUiRenderer: chatUiRendererMock
}));

describe("ExportableChatUiSpec export surface", () => {
  const createObjectURL = vi.fn(() => "blob:mock");
  const revokeObjectURL = vi.fn();
  const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

  beforeEach(() => {
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
    anchorClick.mockClear();
    toPngMock.mockClear();
    chatUiRendererMock.mockClear();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: createObjectURL
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeObjectURL
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  it("mounts a hidden export-only renderer when png export starts", async () => {
    render(
      <ExportableChatUiSpec
        spec={{
          version: "v1",
          layout: "stack",
          elements: [
            {
              type: "BarChart",
              props: {
                title: "Retailer Spend",
                x: "store",
                y: "amount",
                data: [
                  { store: "Lidl", amount: 120 },
                  { store: "dm", amount: 80 }
                ]
              }
            }
          ]
        }}
      />
    );

    expect(chatUiRendererMock.mock.calls.some(([props]) => props.variant === "inline")).toBe(true);
    expect(chatUiRendererMock.mock.calls.some(([props]) => props.variant === "export")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Download PNG" }));

    await waitFor(() => {
      expect(toPngMock).toHaveBeenCalledOnce();
    });

    expect(chatUiRendererMock.mock.calls.some(([props]) => props.variant === "export")).toBe(true);

    const pngMock = toPngMock as unknown as { mock: { calls: Array<[HTMLElement]> } };
    const lastCall = pngMock.mock.calls[pngMock.mock.calls.length - 1];
    const exportNode = lastCall?.[0];
    expect(exportNode).toBeInstanceOf(HTMLElement);
    const exportElement = exportNode as HTMLElement;
    const exportShell = exportElement.parentElement as HTMLElement | null;
    expect(exportShell).toBeInstanceOf(HTMLElement);
    expect(exportShell).toHaveAttribute("aria-hidden", "true");
    expect(exportShell).toHaveClass("fixed", "left-[-20000px]", "top-0", "opacity-0");
    expect(exportElement.querySelector('[data-testid="chat-ui-renderer"]')).toHaveAttribute(
      "data-variant",
      "export"
    );
    expect(screen.getByText("Downloaded chat_ui_retailer_spend.png.")).toBeInTheDocument();
  });
});
