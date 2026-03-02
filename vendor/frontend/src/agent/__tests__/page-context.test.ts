import { describe, expect, it } from "vitest";

import { getSidePanelPageContext } from "@/agent/page-context";

describe("getSidePanelPageContext", () => {
  it("returns no context for full chat workspace routes", () => {
    expect(getSidePanelPageContext("/chat")).toBeNull();
    expect(getSidePanelPageContext("/chat/thread-1")).toBeNull();
  });

  it("returns concise explore guidance", () => {
    const context = getSidePanelPageContext("/explore");
    expect(context).toContain("Page context: Explore");
    expect(context).toContain("filter and search transactions");
  });

  it("returns detail-page context with tool affordances", () => {
    const context = getSidePanelPageContext("/transactions/tx-123");
    expect(context).toContain("Page context: Transaction Detail");
    expect(context).toContain("get_transaction_detail");
    expect(context).toContain("search_transactions");
  });

  it("returns bills page context", () => {
    const context = getSidePanelPageContext("/bills");
    expect(context).toContain("Page context: Bills");
    expect(context).toContain("list_recurring_bills");
  });

  it("returns overview context only on root", () => {
    expect(getSidePanelPageContext("/")).toContain("Page context: Overview");
    expect(getSidePanelPageContext("/unknown")).toBeNull();
  });
});
