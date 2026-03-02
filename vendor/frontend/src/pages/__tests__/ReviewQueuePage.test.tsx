import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewQueuePage } from "../ReviewQueuePage";

function renderReviewQueueRoute(initialEntry = "/review-queue/doc-1"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/review-queue" element={<ReviewQueuePage />} />
          <Route path="/review-queue/:documentId" element={<ReviewQueuePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

type ReviewDetailFixture = {
  document: {
    id: string;
    transaction_id: string;
    source_id: string;
    review_status: string;
    ocr_status: string;
    file_name: string;
    mime_type: string;
    storage_uri: string;
    ocr_provider: string;
    ocr_confidence: number;
    ocr_fallback_used: boolean;
    ocr_latency_ms: number;
    ocr_text: string;
    created_at: string;
    processed_at: string;
  };
  transaction: {
    id: string;
    source_id: string;
    source_transaction_id: string;
    purchased_at: string;
    merchant_name: string;
    total_gross_cents: number;
    currency: string;
    discount_total_cents: null;
    confidence: number;
    raw_payload: Record<string, unknown>;
  };
  items: Array<{
    id: string;
    line_no: number;
    name: string;
    qty: number;
    unit: string;
    unit_price_cents: number;
    line_total_cents: number;
    category: string | null;
    confidence: number;
    raw_payload: Record<string, unknown>;
  }>;
  confidence: {
    transaction_confidence: number;
  };
};

function buildDetailFixture(
  documentId: string,
  transactionId: string,
  merchantName: string,
  items: ReviewDetailFixture["items"]
): ReviewDetailFixture {
  return {
    document: {
      id: documentId,
      transaction_id: transactionId,
      source_id: "ocr_upload",
      review_status: "needs_review",
      ocr_status: "completed",
      file_name: `${documentId}.png`,
      mime_type: "image/png",
      storage_uri: `file:///tmp/${documentId}.png`,
      ocr_provider: "external_api",
      ocr_confidence: 0.82,
      ocr_fallback_used: false,
      ocr_latency_ms: 300,
      ocr_text: "receipt text",
      created_at: "2026-02-19T12:00:00Z",
      processed_at: "2026-02-19T12:01:00Z"
    },
    transaction: {
      id: transactionId,
      source_id: "ocr_upload",
      source_transaction_id: `${transactionId}-source`,
      purchased_at: "2026-02-19T11:59:00Z",
      merchant_name: merchantName,
      total_gross_cents: 449,
      currency: "EUR",
      discount_total_cents: null,
      confidence: 0.7,
      raw_payload: {}
    },
    items,
    confidence: {
      transaction_confidence: 0.7
    }
  };
}

describe("ReviewQueuePage", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    const detailByDocumentId: Record<string, ReviewDetailFixture> = {
      "doc-1": buildDetailFixture("doc-1", "tx-1", "My Store", [
        {
          id: "item-1",
          line_no: 1,
          name: "Milk",
          qty: 1,
          unit: "pcs",
          unit_price_cents: 199,
          line_total_cents: 199,
          category: null,
          confidence: 0.65,
          raw_payload: {}
        }
      ]),
      "doc-2": buildDetailFixture("doc-2", "tx-2", "Second Store", [
        {
          id: "item-2",
          line_no: 1,
          name: "Bread",
          qty: 1,
          unit: "pcs",
          unit_price_cents: 299,
          line_total_cents: 299,
          category: null,
          confidence: 0.68,
          raw_payload: {}
        }
      ]),
      "doc-empty": buildDetailFixture("doc-empty", "tx-empty", "Empty Store", [])
    };

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = init?.method ?? "GET";

        if (method === "GET" && url.pathname.startsWith("/api/v1/review-queue/") && !url.pathname.includes("/items/")) {
          const documentId = url.pathname.replace("/api/v1/review-queue/", "");
          const detail = detailByDocumentId[documentId];
          if (!detail) {
            throw new Error(`Unexpected request: ${method} ${url.pathname}`);
          }
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: detail,
              warnings: [],
              error: null
            })
          };
        }

        if (method === "POST" && url.pathname === "/api/v1/review-queue/doc-1/approve") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                document_id: "doc-1",
                review_status: "approved"
              },
              warnings: [],
              error: null
            })
          };
        }
        if (method === "POST" && url.pathname === "/api/v1/review-queue/doc-1/reject") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                document_id: "doc-1",
                review_status: "rejected"
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "PATCH" && url.pathname === "/api/v1/review-queue/doc-1/transaction") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                transaction_id: "tx-1",
                updated_fields: ["merchant_name"]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "PATCH" && url.pathname.startsWith("/api/v1/review-queue/") && url.pathname.includes("/items/")) {
          const itemId = url.pathname.split("/items/")[1] ?? "";
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                transaction_item_id: itemId,
                updated_fields: ["category"]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/review-queue") {
          const statusFilter = url.searchParams.get("status");
          const items =
            statusFilter === "approved"
              ? []
              : [
                  {
                    document_id: "doc-1",
                    transaction_id: "tx-1",
                    source_id: "ocr_upload",
                    review_status: "needs_review",
                    ocr_status: "completed",
                    merchant_name: "My Store",
                    purchased_at: "2026-02-19T11:59:00Z",
                    total_gross_cents: 449,
                    currency: "EUR",
                    transaction_confidence: 0.7,
                    ocr_confidence: 0.82,
                    created_at: "2026-02-19T12:00:00Z"
                  },
                  {
                    document_id: "doc-2",
                    transaction_id: "tx-2",
                    source_id: "ocr_upload",
                    review_status: "needs_review",
                    ocr_status: "completed",
                    merchant_name: "Second Store",
                    purchased_at: "2026-02-19T12:10:00Z",
                    total_gross_cents: 799,
                    currency: "EUR",
                    transaction_confidence: 0.72,
                    ocr_confidence: 0.84,
                    created_at: "2026-02-19T12:10:00Z"
                  },
                  {
                    document_id: "doc-empty",
                    transaction_id: "tx-empty",
                    source_id: "ocr_upload",
                    review_status: "needs_review",
                    ocr_status: "completed",
                    merchant_name: "Empty Store",
                    purchased_at: "2026-02-19T12:20:00Z",
                    total_gross_cents: 0,
                    currency: "EUR",
                    transaction_confidence: 0.4,
                    ocr_confidence: 0.84,
                    created_at: "2026-02-19T12:20:00Z"
                  }
                ];
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                limit: 25,
                offset: 0,
                count: items.length,
                total: items.length,
                items
              },
              warnings: [],
              error: null
            })
          };
        }

        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      })
    );
  });

  it("renders queue/detail and approves a document", async () => {
    renderReviewQueueRoute();

    await waitFor(() => {
      expect(screen.getByText("Review Queue")).toBeInTheDocument();
      expect(screen.getByText("Review Detail")).toBeInTheDocument();
      expect(screen.getByText("My Store")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(screen.getByText('Review status updated to "approved".')).toBeInTheDocument();
    });

    const approveCall = vi
      .mocked(fetch)
      .mock.calls.find((call) => String(call[0]).includes("/api/v1/review-queue/doc-1/approve"));
    expect(approveCall).toBeDefined();
    expect(String(approveCall?.[1]?.method)).toBe("POST");
  });

  it("handles reject confirmation flow and sends reject payload", async () => {
    renderReviewQueueRoute();

    await waitFor(() => {
      expect(screen.getByText("ID: doc-1")).toBeInTheDocument();
    });

    const detailDialog = screen.getByRole("dialog");
    fireEvent.change(within(detailDialog).getByLabelText("Actor ID"), {
      target: { value: "qa-reviewer" }
    });
    fireEvent.change(within(detailDialog).getByLabelText("Reason"), {
      target: { value: "OCR mismatch" }
    });
    fireEvent.click(within(detailDialog).getByRole("button", { name: "Reject" }));

    await waitFor(() => {
      expect(screen.getByText('Review status updated to "rejected".')).toBeInTheDocument();
    });

    expect(window.confirm).toHaveBeenCalledWith("Reject this document from the review queue?");
    const rejectCall = vi
      .mocked(fetch)
      .mock.calls.find((call) => String(call[0]).includes("/api/v1/review-queue/doc-1/reject"));
    expect(rejectCall).toBeDefined();
    expect(String(rejectCall?.[1]?.method)).toBe("POST");
    const rejectBody = JSON.parse(String(rejectCall?.[1]?.body || "{}")) as {
      actor_id?: string;
      reason?: string;
    };
    expect(rejectBody.actor_id).toBe("qa-reviewer");
    expect(rejectBody.reason).toBe("OCR mismatch");
  });

  it("skips reject mutation when confirmation is cancelled", async () => {
    vi.mocked(window.confirm).mockReturnValueOnce(false);
    renderReviewQueueRoute();

    await waitFor(() => {
      expect(screen.getByText("ID: doc-1")).toBeInTheDocument();
    });

    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Reject" }));

    const rejectCalls = vi
      .mocked(fetch)
      .mock.calls.filter((call) => String(call[0]).includes("/api/v1/review-queue/doc-1/reject"));
    expect(rejectCalls).toHaveLength(0);
  });

  it("keeps deep-linking and closes the detail drawer back to queue route", async () => {
    renderReviewQueueRoute("/review-queue/doc-1?status=needs_review&threshold=0.8&offset=0");

    await waitFor(() => {
      expect(screen.getByText("Review Detail")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Back to queue" }));

    await waitFor(() => {
      expect(screen.queryByText("Review Detail")).not.toBeInTheDocument();
      expect(screen.getByText("Review Queue")).toBeInTheDocument();
    });
  });

  it("submits transaction patch with validated payload", async () => {
    renderReviewQueueRoute("/review-queue/doc-1?status=needs_review&threshold=0.85&offset=0");

    await waitFor(() => {
      expect(screen.getByText("ID: doc-1")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Actor ID"), {
      target: { value: "ledger-bot" }
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "merchant correction" }
    });
    fireEvent.change(screen.getByLabelText("Transaction corrections JSON"), {
      target: { value: "{\"merchant_name\":\"My Store Updated\"}" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply transaction patch" }));

    await waitFor(() => {
      expect(screen.getByText("Transaction fields updated: merchant_name")).toBeInTheDocument();
    });

    const patchCall = vi
      .mocked(fetch)
      .mock.calls.find((call) => String(call[0]).includes("/api/v1/review-queue/doc-1/transaction"));
    expect(patchCall).toBeDefined();
    expect(String(patchCall?.[1]?.method)).toBe("PATCH");
    const patchBody = JSON.parse(String(patchCall?.[1]?.body || "{}")) as {
      actor_id?: string;
      reason?: string;
      corrections?: Record<string, unknown>;
    };
    expect(patchBody.actor_id).toBe("ledger-bot");
    expect(patchBody.reason).toBe("merchant correction");
    expect(patchBody.corrections?.merchant_name).toBe("My Store Updated");
  });

  it("revalidates selected item on document switch and patches the current document item", async () => {
    renderReviewQueueRoute("/review-queue/doc-1?status=needs_review&threshold=0.85&offset=0");

    await waitFor(() => {
      expect(screen.getByText("ID: doc-1")).toBeInTheDocument();
      expect(screen.getByText("Milk")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Back to queue" }));
    await waitFor(() => {
      expect(screen.queryByText("Review Detail")).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("link", { name: "Open" })[1]);

    await waitFor(() => {
      expect(screen.getByText("ID: doc-2")).toBeInTheDocument();
      expect(screen.getByText("Bread")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Apply item patch" }));

    await waitFor(() => {
      expect(screen.getByText("Item fields updated: category")).toBeInTheDocument();
    });

    const patchCall = vi
      .mocked(fetch)
      .mock.calls.find((call) => String(call[0]).includes("/api/v1/review-queue/doc-2/items/item-2"));
    expect(patchCall).toBeDefined();
    expect(String(patchCall?.[1]?.method)).toBe("PATCH");
    const patchBody = JSON.parse(String(patchCall?.[1]?.body || "{}")) as {
      actor_id?: string;
      reason?: string;
      corrections?: Record<string, unknown>;
    };
    expect(patchBody.actor_id).toBe("reviewer-ui");
    expect(patchBody.reason).toBeUndefined();
    expect(patchBody.corrections?.category).toBe("uncategorized");
  });

  it("disables item patch when selected document has no items", async () => {
    renderReviewQueueRoute("/review-queue/doc-empty?status=needs_review&threshold=0.85&offset=0");

    await waitFor(() => {
      expect(screen.getByText("ID: doc-empty")).toBeInTheDocument();
    });

    const patchButton = screen.getByRole("button", { name: "Apply item patch" });
    expect(patchButton).toBeDisabled();

    const itemPatchCalls = vi
      .mocked(fetch)
      .mock.calls.filter((call) => String(call[0]).includes("/items/") && String(call[1]?.method) === "PATCH");
    expect(itemPatchCalls).toHaveLength(0);
  });

  it("shows zero-safe pagination text for an empty queue", async () => {
    renderReviewQueueRoute("/review-queue?status=approved");

    await waitFor(() => {
      expect(screen.getByText("No documents matched the selected filters.")).toBeInTheDocument();
      expect(screen.getByText("Showing 0 of 0")).toBeInTheDocument();
    });
  });

  it("blocks transaction patch when corrections JSON is invalid", async () => {
    renderReviewQueueRoute("/review-queue/doc-1?status=needs_review&threshold=0.85&offset=0");

    await waitFor(() => {
      expect(screen.getByText("ID: doc-1")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Transaction corrections JSON"), {
      target: { value: "{invalid-json" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply transaction patch" }));

    await waitFor(() => {
      expect(screen.getByText("Transaction corrections must be valid JSON.")).toBeInTheDocument();
    });

    const transactionPatchCalls = vi
      .mocked(fetch)
      .mock.calls.filter(
        (call) => String(call[0]).includes("/transaction") && String(call[1]?.method) === "PATCH"
      );
    expect(transactionPatchCalls).toHaveLength(0);
  });

  it("blocks item patch when corrections JSON is invalid", async () => {
    renderReviewQueueRoute("/review-queue/doc-1?status=needs_review&threshold=0.85&offset=0");

    await waitFor(() => {
      expect(screen.getByText("ID: doc-1")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Item corrections JSON"), {
      target: { value: "{invalid-json" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply item patch" }));

    await waitFor(() => {
      expect(screen.getByText("Item corrections must be valid JSON.")).toBeInTheDocument();
    });

    const itemPatchCalls = vi
      .mocked(fetch)
      .mock.calls.filter((call) => String(call[0]).includes("/items/") && String(call[1]?.method) === "PATCH");
    expect(itemPatchCalls).toHaveLength(0);
  });
});
