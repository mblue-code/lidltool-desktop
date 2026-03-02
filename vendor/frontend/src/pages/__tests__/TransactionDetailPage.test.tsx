import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TransactionDetailPage } from "../TransactionDetailPage";

function renderTransactionDetail(initialEntry = "/transactions/tx-1"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/transactions/:transactionId" element={<TransactionDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TransactionDetailPage", () => {
  let overrideResultPayload: Record<string, unknown>;

  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.restoreAllMocks();
    overrideResultPayload = {
      transaction_id: "tx-1",
      mode: "local",
      local: {
        transaction: { transaction_id: "tx-1", updated_fields: ["merchant_name"] },
        items: []
      },
      global: {
        created: []
      }
    };

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";

        if (method === "PATCH" && url.includes("/overrides")) {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: overrideResultPayload,
              warnings: [],
              error: null
            })
          };
        }

        if (url.includes("/history")) {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                transaction_id: "tx-1",
                count: 1,
                events: [
                  {
                    id: "hist-1",
                    created_at: "2026-01-05T12:00:00Z",
                    action: "override_applied",
                    actor_id: "ledger-ui",
                    entity_type: "transaction",
                    details: null
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        return {
          ok: true,
          json: async () => ({
            ok: true,
            result: {
              transaction: {
                id: "tx-1",
                source_id: "lidl",
                source_transaction_id: "abc",
                purchased_at: "2026-01-05T10:00:00Z",
                merchant_name: "Lidl Central",
                total_gross_cents: 1999,
                discount_total_cents: 200,
                raw_payload: { id: "raw-1" }
              },
              items: [
                {
                  id: "item-1",
                  line_no: 1,
                  name: "Milk",
                  qty: 1,
                  unit: "pcs",
                  line_total_cents: 199,
                  category: "dairy"
                }
              ],
              discounts: [
                {
                  id: "disc-1",
                  transaction_item_id: "item-1",
                  source_label: "coupon",
                  scope: "item",
                  kind: "promotion",
                  amount_cents: 50
                }
              ],
              documents: [
                {
                  id: "doc-1",
                  mime_type: "application/zip",
                  file_name: "receipt.zip",
                  created_at: "2026-01-05T10:01:00Z"
                }
              ]
            },
            warnings: [],
            error: null
          })
        };
      })
    );
  });

  it("renders tabs, shows document fallback, and validates no-op overrides", async () => {
    renderTransactionDetail();

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Raw payload" })).toBeInTheDocument();
      expect(screen.getByText("Inline preview unavailable")).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: /Open document/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Apply override" }));

    await waitFor(() => {
      expect(
        screen.getByText("No changes detected. Update merchant or item category before applying.")
      ).toBeInTheDocument();
    });
  });

  it("submits overrides successfully and sends transaction corrections", async () => {
    renderTransactionDetail();

    await waitFor(() => {
      expect(screen.getByLabelText("Merchant Name")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Merchant Name"), {
      target: { value: "Lidl Updated" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply override" }));

    await waitFor(() => {
      expect(screen.getByText("Overrides applied.")).toBeInTheDocument();
    });

    const patchCall = vi
      .mocked(fetch)
      .mock.calls.find((call) => String(call[0]).includes("/overrides"));
    expect(patchCall).toBeDefined();
    expect(String(patchCall?.[1]?.method)).toBe("PATCH");
    const body = JSON.parse(String(patchCall?.[1]?.body || "{}")) as {
      transaction_corrections?: { merchant_name?: string };
    };
    expect(body.transaction_corrections?.merchant_name).toBe("Lidl Updated");
  });

  it("shows schema validation error when override response payload drifts", async () => {
    overrideResultPayload = {
      mode: "local"
    };
    renderTransactionDetail();

    await waitFor(() => {
      expect(screen.getByLabelText("Merchant Name")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Merchant Name"), {
      target: { value: "Lidl Updated" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply override" }));

    await waitFor(() => {
      expect(screen.getByText(/Invalid API payload/)).toBeInTheDocument();
    });
  });

  it("renders tab-specific states across items, discounts, history, and raw payload", async () => {
    renderTransactionDetail();

    function activateTab(name: "Items" | "Discounts" | "History" | "Raw payload"): void {
      const tab = screen.getByRole("tab", { name });
      fireEvent.mouseDown(tab, { button: 0 });
      fireEvent.focus(tab);
    }

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Items" })).toBeInTheDocument();
    });

    activateTab("Items");
    await waitFor(() => {
      expect(screen.getByText("Line Items")).toBeInTheDocument();
      expect(screen.getByText("Milk")).toBeInTheDocument();
    });

    activateTab("Discounts");
    await waitFor(() => {
      expect(screen.getByText("Discount Events")).toBeInTheDocument();
      expect(screen.getByText("coupon")).toBeInTheDocument();
    });

    activateTab("History");
    await waitFor(() => {
      expect(screen.getByText("Edit History")).toBeInTheDocument();
      expect(screen.getByText("override_applied")).toBeInTheDocument();
    });

    activateTab("Raw payload");
    await waitFor(() => {
      expect(screen.getByText("Raw Payload")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Copy JSON" })).toBeInTheDocument();
    });
  });
});
