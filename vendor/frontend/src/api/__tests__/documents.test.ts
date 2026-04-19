import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchDocumentStatus, processDocument, uploadDocument } from "@/api/documents";

function okEnvelope(result: unknown): Record<string, unknown> {
  return {
    ok: true,
    result,
    warnings: [],
    error: null
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("documents API transport", () => {
  it("does not send legacy api_key query/form fields for upload, process, and status calls", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = init?.method ?? "GET";

        if (method === "POST" && url.pathname === "/api/v1/documents/upload") {
          return {
            ok: true,
            json: async () =>
              okEnvelope({
                document_id: "doc-1",
                storage_uri: "file:///tmp/doc-1.png",
                sha256: "abc123",
                mime_type: "image/png",
                status: "pending"
              })
          };
        }

        if (method === "POST" && url.pathname === "/api/v1/documents/doc-1/process") {
          return {
            ok: true,
            json: async () =>
              okEnvelope({
                document_id: "doc-1",
                job_id: "job-1",
                status: "queued",
                reused: false
              })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/documents/doc-1/status") {
          return {
            ok: true,
            json: async () =>
              okEnvelope({
                document_id: "doc-1",
                transaction_id: null,
                source_id: "ocr_upload",
                status: "queued",
                review_status: "needs_review",
                ocr_provider: "external_api",
                ocr_confidence: 0.82,
                ocr_fallback_used: false,
                ocr_latency_ms: 250,
                processed_at: null,
                job: {
                  job_id: "job-1",
                  status: "queued",
                  started_at: null,
                  finished_at: null,
                  timeline: [],
                  error: null
                }
              })
          };
        }

        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      })
    );

    const file = new File(["fake"], "receipt.png", { type: "image/png" });
    await uploadDocument({
      file,
      source: "ocr_upload",
      metadata: { channel: "manual_upload" }
    });
    await processDocument("doc-1", { callerToken: "caller-1" });
    await fetchDocumentStatus("doc-1", { jobId: "job-1" });

    const calls = vi.mocked(fetch).mock.calls;

    const uploadCall = calls.find((call) => new URL(String(call[0])).pathname === "/api/v1/documents/upload");
    const processCall = calls.find((call) => new URL(String(call[0])).pathname === "/api/v1/documents/doc-1/process");
    const statusCall = calls.find((call) => new URL(String(call[0])).pathname === "/api/v1/documents/doc-1/status");

    expect(uploadCall).toBeDefined();
    expect(processCall).toBeDefined();
    expect(statusCall).toBeDefined();

    for (const call of calls) {
      const url = new URL(String(call[0]));
      expect(url.searchParams.has("api_key")).toBe(false);
    }

    const uploadBody = uploadCall?.[1]?.body;
    expect(uploadBody).toBeInstanceOf(FormData);
    expect((uploadBody as FormData).has("api_key")).toBe(false);

    const processBody = processCall?.[1]?.body;
    expect(processBody).toBeInstanceOf(FormData);
    expect((processBody as FormData).has("api_key")).toBe(false);

    const statusUrl = new URL(String(statusCall?.[0]));
    expect(statusUrl.searchParams.get("job_id")).toBe("job-1");
    expect(statusUrl.searchParams.has("api_key")).toBe(false);
  });
});
