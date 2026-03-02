import { afterEach, describe, expect, it, vi } from "vitest";

import { listChatThreads, streamChatThread } from "@/api/chat";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("chat api", () => {
  it("lists chat threads from envelope responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          result: {
            items: [
              {
                thread_id: "t1",
                user_id: "u1",
                title: "First thread",
                stream_status: "idle",
                created_at: "2026-02-22T00:00:00Z",
                updated_at: "2026-02-22T00:00:00Z",
                archived_at: null
              }
            ],
            total: 1
          },
          warnings: [],
          error: null
        })
      })
    );

    const result = await listChatThreads();
    expect(result.total).toBe(1);
    expect(result.items[0]?.thread_id).toBe("t1");
  });

  it("parses SSE stream events", async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          encoder.encode('data: {"type":"start"}\n\ndata: {"type":"text_delta","delta":"Hello"}\n\n')
        );
        controller.enqueue(encoder.encode('data: {"type":"done","reason":"stop"}\n\n'));
        controller.close();
      }
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        body
      })
    );

    const events: Array<{ type: string; delta?: string }> = [];
    await streamChatThread("thread-1", {}, (event) => {
      events.push({ type: event.type, delta: event.delta });
    });

    expect(events.map((event) => event.type)).toEqual(["start", "text_delta", "done"]);
    expect(events[1]?.delta).toBe("Hello");
  });
});
