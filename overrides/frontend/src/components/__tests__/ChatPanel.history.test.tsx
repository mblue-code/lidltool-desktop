import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
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
    model: "qwen3.5:0.8b",
    default_model: "qwen3.5:0.8b",
    local_model: "qwen3.5:0.8b",
    preferred_model: "qwen3.5:0.8b",
    oauth_provider: null,
    oauth_connected: false,
    available_models: [
      {
        id: "qwen3.5:0.8b",
        label: "Local Qwen (tiny)",
        source: "local",
        enabled: true,
        description: "Very small shipped local fallback model. Private and available by default, but weaker for deeper analysis."
      }
    ]
  }))
}));

vi.mock("@/api/users", () => ({
  fetchCurrentUser: vi.fn(async () => ({
    user_id: "u1",
    username: "alice",
    display_name: null,
    is_admin: false,
    preferred_locale: "de"
  })),
  updateCurrentUserLocale: vi.fn()
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
                  model_id: "qwen3.5:0.8b",
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

    const textarea = await screen.findByPlaceholderText(/Ask about your spending, products/);

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

  it("renders structured tool visuals inline from persisted chat state", async () => {
    installLocalStorageStub();
    installChatApiFetchStub();
    storage.set(
      "agent.chat.v1",
      JSON.stringify([
        {
          role: "toolResult",
          toolName: "render_ui",
          toolCallId: "tool-1",
          content: [{ type: "text", text: "Rendered 1 UI element(s)." }],
          details: {
            ui_spec: {
              version: "v1",
              layout: "stack",
              elements: [
                {
                  type: "MetricCard",
                  props: {
                    title: "Net Spend",
                    value: "EUR 42.10",
                    subtitle: "Last 30 days"
                  }
                }
              ]
            }
          },
          timestamp: Date.now()
        }
      ])
    );

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

    expect((await screen.findAllByText("Net Spend")).length).toBeGreaterThan(0);
    expect(screen.getByText("Visual artifact")).toBeInTheDocument();
    expect(screen.queryByText("Rendered 1 UI element(s).")).not.toBeInTheDocument();
  });

  it("renders localized chat chrome in german", async () => {
    installLocalStorageStub();
    installChatApiFetchStub();
    window.localStorage.setItem("app.locale", "de");

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false }
      }
    });

    render(
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <ChatPanel
            open
            onOpenChange={() => undefined}
            enabled
            panelWidth={420}
            onPanelWidthChange={() => undefined}
          />
        </I18nProvider>
      </QueryClientProvider>
    );

    expect((await screen.findAllByText("KI-Assistent")).length).toBeGreaterThan(0);
    expect((await screen.findAllByRole("button", { name: "Neuer Chat" })).length).toBeGreaterThan(0);
    expect((await screen.findAllByRole("button", { name: "Schließen" })).length).toBeGreaterThan(0);
    expect((await screen.findAllByRole("button", { name: "Senden" })).length).toBeGreaterThan(0);
    expect((await screen.findAllByLabelText("Modell")).length).toBeGreaterThan(0);
    expect((await screen.findAllByPlaceholderText(/Fragen Sie nach Ausgaben/)).length).toBeGreaterThan(0);
  });
});
