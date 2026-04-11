import type * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DocumentsUploadPage } from "../DocumentsUploadPage";

function renderWithQueryClient(ui: React.JSX.Element): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });
  render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function stubDocumentApi(statusTimeline: string[]): void {
  let statusRequests = 0;

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      const method = init?.method ?? "GET";

      if (method === "POST" && url.pathname === "/api/v1/documents/upload") {
        return {
          ok: true,
          json: async () => ({
            ok: true,
            result: {
              document_id: "doc-1",
              storage_uri: "file:///tmp/doc-1.png",
              sha256: "abc123",
              mime_type: "image/png",
              status: "pending"
            },
            warnings: [],
            error: null
          })
        };
      }

      if (method === "POST" && url.pathname === "/api/v1/documents/doc-1/process") {
        return {
          ok: true,
          json: async () => ({
            ok: true,
            result: {
              document_id: "doc-1",
              job_id: "job-1",
              status: "queued",
              reused: false
            },
            warnings: [],
            error: null
          })
        };
      }

      if (method === "GET" && url.pathname === "/api/v1/documents/doc-1/status") {
        const index = Math.min(statusRequests, Math.max(statusTimeline.length - 1, 0));
        const status = statusTimeline[index] ?? "queued";
        statusRequests += 1;
        return {
          ok: true,
          json: async () => ({
            ok: true,
            result: {
              document_id: "doc-1",
              transaction_id: null,
              source_id: "ocr_upload",
              status,
              review_status: status === "completed" ? "approved" : "needs_review",
              ocr_provider: "external_api",
              ocr_confidence: 0.88,
              ocr_fallback_used: false,
              ocr_latency_ms: 420,
              processed_at: "2026-02-19T12:00:00Z",
              job: { status }
            },
            warnings: [],
            error: null
          })
        };
      }

      throw new Error(`Unexpected request: ${method} ${url.pathname}`);
    })
  );
}

function assertNoLegacyApiKeyTransport(): void {
  const calls = vi.mocked(fetch).mock.calls;

  for (const call of calls) {
    const url = new URL(String(call[0]));
    expect(url.searchParams.has("api_key")).toBe(false);
  }

  const uploadCall = calls.find((call) => new URL(String(call[0])).pathname === "/api/v1/documents/upload");
  const processCall = calls.find(
    (call) => new URL(String(call[0])).pathname === "/api/v1/documents/doc-1/process"
  );

  expect(uploadCall).toBeDefined();
  expect(processCall).toBeDefined();

  expect(uploadCall?.[1]?.body).toBeInstanceOf(FormData);
  expect(processCall?.[1]?.body).toBeInstanceOf(FormData);
  expect((uploadCall?.[1]?.body as FormData).has("api_key")).toBe(false);
  expect((processCall?.[1]?.body as FormData).has("api_key")).toBe(false);
}

describe("DocumentsUploadPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("polls OCR status from queued to processing to completed", async () => {
    stubDocumentApi(["queued", "processing", "completed"]);
    renderWithQueryClient(<DocumentsUploadPage />);

    const fileInput = screen.getByLabelText("Choose document file");
    const file = new File(["fake"], "receipt.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    fireEvent.click(screen.getByRole("button", { name: "Upload and process" }));

    await waitFor(() => {
      expect(screen.getByText("OCR processing triggered. Status will update automatically.")).toBeInTheDocument();
      expect(screen.getByText("Status queued")).toBeInTheDocument();
    });

    await waitFor(
      () => {
        expect(screen.getByText("Status processing")).toBeInTheDocument();
      },
      { timeout: 7000 }
    );

    await waitFor(
      () => {
        expect(screen.getByText("Status completed")).toBeInTheDocument();
        expect(screen.getByText("State: done")).toBeInTheDocument();
      },
      { timeout: 7000 }
    );

    assertNoLegacyApiKeyTransport();
  });

  it("polls OCR status from queued to failed", async () => {
    stubDocumentApi(["queued", "failed"]);
    renderWithQueryClient(<DocumentsUploadPage />);

    const fileInput = screen.getByLabelText("Choose document file");
    const file = new File(["fake"], "receipt.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    fireEvent.click(screen.getByRole("button", { name: "Upload and process" }));

    await waitFor(() => {
      expect(screen.getByText("OCR processing triggered. Status will update automatically.")).toBeInTheDocument();
      expect(screen.getByText("Status queued")).toBeInTheDocument();
    });

    await waitFor(
      () => {
        expect(screen.getByText("Status failed")).toBeInTheDocument();
        expect(screen.getByText("State: error")).toBeInTheDocument();
      },
      { timeout: 7000 }
    );
  });

  it("blocks upload when metadata JSON is invalid", async () => {
    stubDocumentApi(["queued"]);
    renderWithQueryClient(<DocumentsUploadPage />);

    const fileInput = screen.getByLabelText("Choose document file");
    const file = new File(["fake"], "receipt.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    fireEvent.click(screen.getByRole("button", { name: "Advanced upload details" }));
    fireEvent.change(screen.getByLabelText("Metadata JSON"), {
      target: { value: "{invalid-json" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload and process" }));

    await waitFor(() => {
      expect(screen.getByText("Metadata must be valid JSON.")).toBeInTheDocument();
    });

    const uploadCall = vi
      .mocked(fetch)
      .mock.calls.find((call) => String(call[0]).includes("/api/v1/documents/upload"));
    expect(uploadCall).toBeUndefined();
  });

  it("blocks upload when source is missing", async () => {
    stubDocumentApi(["queued"]);
    renderWithQueryClient(<DocumentsUploadPage />);

    const fileInput = screen.getByLabelText("Choose document file");
    const file = new File(["fake"], "receipt.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Advanced upload details" }));
    fireEvent.change(screen.getByLabelText("Source"), { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "Upload and process" }));

    await waitFor(() => {
      expect(screen.getByText("Source is required.")).toBeInTheDocument();
    });

    const uploadCall = vi
      .mocked(fetch)
      .mock.calls.find((call) => String(call[0]).includes("/api/v1/documents/upload"));
    expect(uploadCall).toBeUndefined();
  });
});
