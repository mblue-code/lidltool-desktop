import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AutomationsPage } from "../AutomationsPage";

function okEnvelope(result: unknown): Record<string, unknown> {
  return {
    ok: true,
    result,
    warnings: [],
    error: null
  };
}

function renderWithQueryClient(ui: JSX.Element): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });
  render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

function findRuleRow(name: string): HTMLElement {
  const row = screen.getAllByText(name)[0]?.closest("tr");
  if (!row) {
    throw new Error(`Could not find table row for ${name}`);
  }
  return row;
}

type RuleFixture = {
  id: string;
  name: string;
  rule_type: string;
  enabled: boolean;
  trigger_config: Record<string, unknown>;
  action_config: Record<string, unknown>;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
};

describe("AutomationsPage", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.restoreAllMocks();

    const now = "2026-02-19T12:00:00Z";
    let rules: RuleFixture[] = [
      {
        id: "rule-weekly",
        name: "Weekly Summary",
        rule_type: "weekly_summary",
        enabled: true,
        trigger_config: {
          schedule: {
            interval_seconds: 3600
          }
        },
        action_config: {
          months_back: 3,
          include_breakdown: true
        },
        next_run_at: null,
        last_run_at: null,
        created_at: now,
        updated_at: now
      },
      {
        id: "rule-budget",
        name: "Budget Guard",
        rule_type: "budget_alert",
        enabled: false,
        trigger_config: {
          schedule: {
            interval_seconds: 7200
          },
          min_total_cents: 300
        },
        action_config: {
          budget_cents: 12000,
          period: "monthly"
        },
        next_run_at: null,
        last_run_at: null,
        created_at: now,
        updated_at: now
      }
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = init?.method ?? "GET";

        if (method === "GET" && url.pathname === "/api/v1/automations") {
          return {
            ok: true,
            json: async () =>
              okEnvelope({
                count: rules.length,
                total: rules.length,
                limit: 25,
                offset: Number(url.searchParams.get("offset") || "0"),
                items: rules
              })
          };
        }

        if (method === "POST" && url.pathname === "/api/v1/automations") {
          const payload = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
          const created: RuleFixture = {
            id: `rule-created-${rules.length + 1}`,
            name: String(payload.name || "Created"),
            rule_type: String(payload.rule_type || "weekly_summary"),
            enabled: Boolean(payload.enabled ?? true),
            trigger_config: (payload.trigger_config ?? {}) as Record<string, unknown>,
            action_config: (payload.action_config ?? {}) as Record<string, unknown>,
            next_run_at: null,
            last_run_at: null,
            created_at: now,
            updated_at: now
          };
          rules = [created, ...rules];
          return {
            ok: true,
            json: async () => okEnvelope(created)
          };
        }

        if (method === "PATCH" && url.pathname.startsWith("/api/v1/automations/")) {
          const id = url.pathname.replace("/api/v1/automations/", "");
          const payload = JSON.parse(String(init?.body || "{}")) as Record<string, unknown>;
          const existing = rules.find((rule) => rule.id === id);
          if (!existing) {
            throw new Error(`Unknown rule id ${id}`);
          }
          const nextRule: RuleFixture = {
            ...existing,
            ...(typeof payload.name === "string" ? { name: payload.name } : {}),
            ...(typeof payload.enabled === "boolean" ? { enabled: payload.enabled } : {}),
            ...(typeof payload.rule_type === "string" ? { rule_type: payload.rule_type } : {}),
            ...(payload.trigger_config && typeof payload.trigger_config === "object"
              ? { trigger_config: payload.trigger_config as Record<string, unknown> }
              : {}),
            ...(payload.action_config && typeof payload.action_config === "object"
              ? { action_config: payload.action_config as Record<string, unknown> }
              : {}),
            updated_at: now
          };
          rules = rules.map((rule) => (rule.id === id ? nextRule : rule));
          return {
            ok: true,
            json: async () => okEnvelope(nextRule)
          };
        }

        if (method === "DELETE" && url.pathname.startsWith("/api/v1/automations/")) {
          const id = url.pathname.replace("/api/v1/automations/", "");
          const existing = rules.find((rule) => rule.id === id);
          if (!existing) {
            throw new Error(`Unknown rule id ${id}`);
          }
          rules = rules.filter((rule) => rule.id !== id);
          return {
            ok: true,
            json: async () =>
              okEnvelope({
                deleted: true,
                id,
                name: existing.name
              })
          };
        }

        if (method === "POST" && url.pathname.startsWith("/api/v1/automations/") && url.pathname.endsWith("/run")) {
          const id = url.pathname.replace("/api/v1/automations/", "").replace("/run", "");
          return {
            ok: true,
            json: async () =>
              okEnvelope({
                id: "exec-1",
                rule_id: id,
                rule_name: "Manual run",
                rule_type: "weekly_summary",
                status: "success",
                triggered_at: now,
                executed_at: now,
                result: {
                  summary: "ok"
                },
                error: null,
                created_at: now
              })
          };
        }

        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      })
    );
  });

  it("validates required and numeric range fields before creating/updating", async () => {
    renderWithQueryClient(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText("Weekly Summary")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Create rule" }));
    const createDialog = screen.getByRole("dialog");
    fireEvent.click(within(createDialog).getByRole("button", { name: "Create rule" }));

    await waitFor(() => {
      expect(screen.getByText("Rule name is required.")).toBeInTheDocument();
      expect(screen.getByText("Pattern is required.")).toBeInTheDocument();
      expect(screen.getByText("Category is required.")).toBeInTheDocument();
    });

    fireEvent.change(within(createDialog).getByLabelText("Name"), { target: { value: "Category Rule" } });
    fireEvent.change(within(createDialog).getByLabelText("Pattern"), { target: { value: "milk" } });
    fireEvent.change(within(createDialog).getByLabelText("Category"), { target: { value: "dairy" } });
    fireEvent.change(within(createDialog).getByLabelText("Interval seconds"), { target: { value: "30" } });
    fireEvent.click(within(createDialog).getByRole("button", { name: "Create rule" }));

    await waitFor(() => {
      expect(screen.getByText("Interval seconds must be at least 60.")).toBeInTheDocument();
    });

    fireEvent.click(within(createDialog).getByRole("button", { name: "Cancel" }));
    fireEvent.click(within(findRuleRow("Budget Guard")).getByRole("button", { name: "Edit" }));
    const editBudgetDialog = screen.getByRole("dialog");
    fireEvent.change(within(editBudgetDialog).getByLabelText("Budget cents"), { target: { value: "0" } });
    fireEvent.click(within(editBudgetDialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(screen.getByText("Budget cents must be at least 1.")).toBeInTheDocument();
    });

    fireEvent.click(within(editBudgetDialog).getByRole("button", { name: "Cancel" }));
    fireEvent.click(within(findRuleRow("Weekly Summary")).getByRole("button", { name: "Edit" }));
    const editWeeklyDialog = screen.getByRole("dialog");
    fireEvent.change(within(editWeeklyDialog).getByLabelText("Months back"), { target: { value: "0" } });
    fireEvent.click(within(editWeeklyDialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(screen.getByText("Months back must be between 1 and 24.")).toBeInTheDocument();
    });

    const createCalls = vi
      .mocked(fetch)
      .mock.calls.filter((call) => String(call[0]).includes("/api/v1/automations") && String(call[1]?.method) === "POST");
    const postCreates = createCalls.filter((call) => !String(call[0]).includes("/run"));
    expect(postCreates).toHaveLength(0);
  });

  it("creates and edits rules with schema-transformed payloads", async () => {
    renderWithQueryClient(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText("Weekly Summary")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Create rule" }));
    const createDialog = screen.getByRole("dialog");
    fireEvent.change(within(createDialog).getByLabelText("Name"), { target: { value: "Auto Category" } });
    fireEvent.change(within(createDialog).getByLabelText("Pattern"), { target: { value: "yogurt" } });
    fireEvent.change(within(createDialog).getByLabelText("Category"), { target: { value: "dairy" } });
    fireEvent.change(within(createDialog).getByLabelText("Interval seconds"), { target: { value: "3600" } });
    fireEvent.change(within(createDialog).getByLabelText("Min total cents"), { target: { value: "250" } });
    fireEvent.click(within(createDialog).getByRole("button", { name: "Create rule" }));

    await waitFor(() => {
      expect(screen.getByText("Rule created.")).toBeInTheDocument();
    });

    const createCall = vi
      .mocked(fetch)
      .mock.calls.find(
        (call) =>
          String(call[0]).includes("/api/v1/automations") &&
          String(call[1]?.method) === "POST" &&
          !String(call[0]).includes("/run")
      );
    expect(createCall).toBeDefined();
    const createBody = JSON.parse(String(createCall?.[1]?.body || "{}")) as {
      trigger_config?: { schedule?: { interval_seconds?: number }; min_total_cents?: number };
      action_config?: { pattern?: string; category?: string };
    };
    expect(createBody.trigger_config?.schedule?.interval_seconds).toBe(3600);
    expect(createBody.trigger_config?.min_total_cents).toBe(250);
    expect(createBody.action_config?.pattern).toBe("yogurt");
    expect(createBody.action_config?.category).toBe("dairy");

    fireEvent.click(within(findRuleRow("Budget Guard")).getByRole("button", { name: "Edit" }));
    const editDialog = screen.getByRole("dialog");
    fireEvent.change(within(editDialog).getByLabelText("Name"), { target: { value: "Budget Guard Updated" } });
    fireEvent.change(within(editDialog).getByLabelText("Budget cents"), { target: { value: "15000" } });
    fireEvent.change(within(editDialog).getByLabelText("Interval seconds"), { target: { value: "5400" } });
    fireEvent.click(within(editDialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(screen.getByText("Rule updated.")).toBeInTheDocument();
    });

    const updateCall = vi
      .mocked(fetch)
      .mock.calls.find(
        (call) =>
          String(call[0]).includes("/api/v1/automations/rule-budget") &&
          String(call[1]?.method) === "PATCH"
      );
    expect(updateCall).toBeDefined();
    const updateBody = JSON.parse(String(updateCall?.[1]?.body || "{}")) as {
      trigger_config?: { schedule?: { interval_seconds?: number } };
      action_config?: { budget_cents?: number };
      name?: string;
    };
    expect(updateBody.name).toBe("Budget Guard Updated");
    expect(updateBody.trigger_config?.schedule?.interval_seconds).toBe(5400);
    expect(updateBody.action_config?.budget_cents).toBe(15000);
  });

  it("supports toggle, run, and delete actions with expected requests", async () => {
    renderWithQueryClient(<AutomationsPage />);

    await waitFor(() => {
      expect(screen.getByText("Budget Guard")).toBeInTheDocument();
    });

    fireEvent.click(within(findRuleRow("Weekly Summary")).getByRole("button", { name: "Disable" }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Disable automation rule" })).toBeInTheDocument();
    });
    const disableDialog = screen.getByRole("dialog");
    fireEvent.click(within(disableDialog).getByRole("button", { name: "Disable" }));

    await waitFor(() => {
      expect(screen.getByText("Rule disabled.")).toBeInTheDocument();
    });

    const disableCall = vi
      .mocked(fetch)
      .mock.calls.find(
        (call) =>
          String(call[0]).includes("/api/v1/automations/rule-weekly") &&
          String(call[1]?.method) === "PATCH"
      );
    expect(disableCall).toBeDefined();
    const disableBody = JSON.parse(String(disableCall?.[1]?.body || "{}")) as { enabled?: boolean };
    expect(disableBody.enabled).toBe(false);

    fireEvent.click(within(findRuleRow("Weekly Summary")).getByRole("button", { name: "Run" }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Run automation rule" })).toBeInTheDocument();
    });
    const runDialog = screen.getByRole("dialog");
    fireEvent.click(within(runDialog).getByRole("button", { name: "Run now" }));

    await waitFor(() => {
      expect(screen.getByText("Rule run queued: success.")).toBeInTheDocument();
    });

    const runCall = vi
      .mocked(fetch)
      .mock.calls.find(
        (call) =>
          String(call[0]).includes("/api/v1/automations/rule-weekly/run") &&
          String(call[1]?.method) === "POST"
      );
    expect(runCall).toBeDefined();

    fireEvent.click(within(findRuleRow("Budget Guard")).getByRole("button", { name: "Delete" }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Delete automation rule" })).toBeInTheDocument();
    });
    const deleteDialog = screen.getByRole("dialog");
    fireEvent.click(within(deleteDialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(screen.getByText("Rule deleted.")).toBeInTheDocument();
    });

    const deleteCall = vi
      .mocked(fetch)
      .mock.calls.find(
        (call) =>
          String(call[0]).includes("/api/v1/automations/rule-budget") &&
          String(call[1]?.method) === "DELETE"
      );
    expect(deleteCall).toBeDefined();
  });
});
