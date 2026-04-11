import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { ExportableChatUiSpec } from "@/chat/ui/ExportableChatUiSpec";

const { toPngMock } = vi.hoisted(() => ({
  toPngMock: vi.fn(async () => "data:image/png;base64,AAAA")
}));

vi.mock("html-to-image", () => ({
  toPng: toPngMock
}));

describe("ExportableChatUiSpec", () => {
  const createObjectURL = vi.fn(() => "blob:mock");
  const revokeObjectURL = vi.fn();
  const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

  beforeEach(() => {
    createObjectURL.mockClear();
    revokeObjectURL.mockClear();
    anchorClick.mockClear();
    toPngMock.mockClear();
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

  it("downloads the raw JSON ui spec", () => {
    render(
      <ExportableChatUiSpec
        spec={{
          version: "v1",
          layout: "stack",
          elements: [{ type: "MetricCard", props: { title: "Net Spend", value: 321 } }]
        }}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Download JSON" }));

    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledOnce();
    expect(anchorClick).toHaveBeenCalledOnce();
    expect(screen.getByText("Downloaded chat_ui_net_spend.json.")).toBeInTheDocument();
  });

  it("downloads the rendered ui block as png", async () => {
    render(
      <ExportableChatUiSpec
        spec={{
          version: "v1",
          layout: "stack",
          elements: [
            {
              type: "SankeyChart",
              props: {
                title: "Budget Flow",
                nodes: [
                  { id: "income", label: "Income" },
                  { id: "groceries", label: "Groceries" }
                ],
                links: [{ source: "income", target: "groceries", value: 120 }]
              }
            }
          ]
        }}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Download PNG" }));

    await waitFor(() => {
      expect(toPngMock).toHaveBeenCalledOnce();
    });
    expect(anchorClick).toHaveBeenCalledOnce();
    expect(screen.getByText("Downloaded chat_ui_budget_flow.png.")).toBeInTheDocument();
  });
});
