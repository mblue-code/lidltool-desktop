import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "@/components/ChatPanel";

class FakeAgent {
  state: { messages: Array<Record<string, unknown>> } = {
    messages: []
  };

  private subscribers: Array<(event: any) => void> = [];

  replaceMessages(messages: Array<Record<string, unknown>>): void {
    this.state.messages = [...messages];
  }

  clearMessages(): void {
    this.state.messages = [];
  }

  subscribe(callback: (event: any) => void): () => void {
    this.subscribers.push(callback);
    return () => {
      this.subscribers = this.subscribers.filter((entry) => entry !== callback);
    };
  }

  async prompt(prompt: string): Promise<void> {
    const newMessages = [
      { role: "user", content: prompt, timestamp: Date.now() },
      {
        role: "assistant",
        content: [{ type: "text", text: `Reply for: ${prompt}` }],
        timestamp: Date.now()
      }
    ];
    this.state.messages = [...this.state.messages, ...newMessages];
    for (const subscriber of this.subscribers) {
      subscriber({ type: "agent_end", messages: newMessages });
    }
  }
}

const fakeAgent = new FakeAgent();

vi.mock("@/agent", () => ({
  createSpendingAgent: vi.fn(() => fakeAgent)
}));

vi.mock("@/api/aiSettings", () => ({
  fetchAIAgentConfig: vi.fn(async () => ({
    proxy_url: "http://localhost",
    auth_token: "token",
    model: "gpt-5.2-codex"
  }))
}));

describe("ChatPanel history behavior", () => {
  const storage = new Map<string, string>();

  function installChatApiFetchStub(): void {
    let createdThreadId: string | null = null;

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();

        if (url.pathname === "/api/v1/chat/threads" && method === "POST") {
          const rawBody = typeof init?.body === "string" ? init.body : null;
          if (rawBody) {
            const parsedBody = JSON.parse(rawBody) as { thread_id?: string };
            createdThreadId = parsedBody.thread_id ?? null;
          }
          const threadId = createdThreadId ?? "panel-thread";
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread_id: threadId,
                user_id: "u1",
                title: "Panel thread",
                stream_status: "idle",
                created_at: "2026-02-22T00:00:00Z",
                updated_at: "2026-02-22T00:00:00Z",
                archived_at: null
              },
              warnings: [],
              error: null
            })
          };
        }

        if (
          method === "POST" &&
          createdThreadId &&
          url.pathname === `/api/v1/chat/threads/${createdThreadId}/messages`
        ) {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread: {
                  thread_id: createdThreadId,
                  user_id: "u1",
                  title: "Panel thread",
                  stream_status: "idle",
                  created_at: "2026-02-22T00:00:00Z",
                  updated_at: "2026-02-22T00:00:00Z",
                  archived_at: null
                },
                message: {
                  message_id: "m-user-1",
                  thread_id: createdThreadId,
                  role: "user",
                  content_json: [{ type: "text", text: "first prompt" }],
                  tool_name: null,
                  tool_call_id: null,
                  idempotency_key: "msg-1",
                  usage_json: null,
                  error: null,
                  created_at: "2026-02-22T00:00:00Z"
                }
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "PATCH" && createdThreadId && url.pathname === `/api/v1/chat/threads/${createdThreadId}`) {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread_id: createdThreadId,
                user_id: "u1",
                title: "Panel thread",
                stream_status: "idle",
                created_at: "2026-02-22T00:00:00Z",
                updated_at: "2026-02-22T00:00:00Z",
                archived_at: null
              },
              warnings: [],
              error: null
            })
          };
        }

        if (
          method === "POST" &&
          createdThreadId &&
          url.pathname === `/api/v1/chat/threads/${createdThreadId}/runs`
        ) {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread: {
                  thread_id: createdThreadId,
                  user_id: "u1",
                  title: "Panel thread",
                  stream_status: "idle",
                  created_at: "2026-02-22T00:00:00Z",
                  updated_at: "2026-02-22T00:00:00Z",
                  archived_at: null
                },
                messages: [],
                run: {
                  run_id: "r1",
                  thread_id: createdThreadId,
                  message_id: null,
                  model_id: "gpt-5.2-codex",
                  prompt_tokens: null,
                  completion_tokens: null,
                  latency_ms: 10,
                  status: "ok",
                  created_at: "2026-02-22T00:00:00Z"
                }
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

  function installLocalStorageStub(): void {
    const localStorageStub = {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        storage.set(key, value);
      },
      removeItem: (key: string) => {
        storage.delete(key);
      },
      clear: () => {
        storage.clear();
      }
    };
    vi.stubGlobal("localStorage", localStorageStub);
  }

  afterEach(() => {
    storage.clear();
    fakeAgent.clearMessages();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps earlier turns after a second prompt completes", async () => {
    installLocalStorageStub();
    installChatApiFetchStub();
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false }
      }
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ChatPanel
          open
          onOpenChange={() => undefined}
          enabled
          panelWidth={420}
          onPanelWidthChange={() => undefined}
        />
      </QueryClientProvider>
    );

    const textarea = await screen.findByPlaceholderText("Ask about spending, prices, and products...");

    fireEvent.change(textarea, { target: { value: "first prompt" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("first prompt");
    await screen.findByText("Reply for: first prompt");

    fireEvent.change(textarea, { target: { value: "second prompt" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("second prompt");
    await screen.findByText("Reply for: second prompt");
    await waitFor(() => {
      expect(screen.getByText("first prompt")).toBeInTheDocument();
      expect(screen.getByText("Reply for: first prompt")).toBeInTheDocument();
    });
  });
});
