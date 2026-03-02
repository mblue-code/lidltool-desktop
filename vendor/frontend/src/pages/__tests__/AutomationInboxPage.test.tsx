import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AutomationInboxPage } from "../AutomationInboxPage";

function okEnvelope(result: unknown): Record<string, unknown> {
  return {
    ok: true,
    result,
    warnings: [],
    error: null
  };
}

function renderWithQueryClient(initialEntry = "/automation-inbox"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <QueryClientProvider client={queryClient}>
        <AutomationInboxPage />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("AutomationInboxPage", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.restoreAllMocks();

    const executions = Array.from({ length: 30 }).map((_, index) => {
      const id = index + 1;
      const status = id % 3 === 0 ? "failed" : id % 2 === 0 ? "skipped" : "success";
      return {
        id: `exec-${id}`,
        rule_id: id % 2 === 0 ? "rule-budget" : "rule-weekly",
        rule_name: id % 2 === 0 ? "Budget Guard" : "Weekly Summary",
        rule_type: id % 2 === 0 ? "budget_alert" : "weekly_summary",
        status,
        triggered_at: `2026-02-19T12:${String(id).padStart(2, "0")}:00Z`,
        executed_at: `2026-02-19T12:${String(id).padStart(2, "0")}:05Z`,
        result: {
          template: id % 2 === 0 ? "budget_alert" : "weekly_summary",
          row: id
        },
        error: status === "failed" ? "Execution failed" : null,
        created_at: `2026-02-19T12:${String(id).padStart(2, "0")}:00Z`
      };
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));

        if (url.pathname === "/api/v1/automations/executions") {
          const status = url.searchParams.get("status") || "";
          const ruleType = url.searchParams.get("rule_type") || "";
          const offset = Number(url.searchParams.get("offset") || "0");
          const limit = Number(url.searchParams.get("limit") || "25");

          const filtered = executions.filter((execution) => {
            if (status && execution.status !== status) {
              return false;
            }
            if (ruleType && execution.rule_type !== ruleType) {
              return false;
            }
            return true;
          });
          const items = filtered.slice(offset, offset + limit);

          return {
            ok: true,
            json: async () =>
              okEnvelope({
                count: items.length,
                total: filtered.length,
                limit,
                offset,
                items
              })
          };
        }

        throw new Error(`Unexpected request: ${url.pathname}`);
      })
    );

    vi.stubGlobal("navigator", {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined)
      }
    });
  });

  it("applies filters and requests filtered execution data", async () => {
    renderWithQueryClient();

    await waitFor(() => {
      expect(screen.getByText("Automation Inbox")).toBeInTheDocument();
      expect(screen.getByText("Showing 1-25 of 30")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("combobox", { name: "Status" }));
    fireEvent.click(screen.getByRole("option", { name: "Failed" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => {
      const filteredCall = vi
        .mocked(fetch)
        .mock.calls.find((call) => String(call[0]).includes("status=failed"));
      expect(filteredCall).toBeDefined();
    });
  });

  it("supports pagination controls and offset updates", async () => {
    renderWithQueryClient();

    await waitFor(() => {
      expect(screen.getByText("Showing 1-25 of 30")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(screen.getByText("Showing 26-30 of 30")).toBeInTheDocument();
    });

    const nextCall = vi
      .mocked(fetch)
      .mock.calls.find((call) => String(call[0]).includes("offset=25"));
    expect(nextCall).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));

    await waitFor(() => {
      expect(screen.getByText("Showing 1-25 of 30")).toBeInTheDocument();
    });
  });

  it("opens payload dialog and copies payload to clipboard", async () => {
    renderWithQueryClient();

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "View payload" }).length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getAllByRole("button", { name: "View payload" })[0]);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Execution payload" })).toBeInTheDocument();
      expect(screen.getByText(/"id": "exec-1"/)).toBeInTheDocument();
    });

    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Copy payload" }));

    await waitFor(() => {
      expect(screen.getByText("Payload copied.")).toBeInTheDocument();
    });

    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    expect(String(vi.mocked(navigator.clipboard.writeText).mock.calls[0]?.[0] || "")).toContain('"id": "exec-1"');
  });
});
