import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "@/components/ChatPanel";

const mocks = vi.hoisted(() => ({
  promptMock: vi.fn(async (_prompt: string) => undefined),
  createSpendingAgentMock: vi.fn(),
  fetchAIAgentConfigMock: vi.fn()
}));

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
    await mocks.promptMock(prompt);
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
  createSpendingAgent: mocks.createSpendingAgentMock
}));

vi.mock("@/api/aiSettings", () => ({
  fetchAIAgentConfig: mocks.fetchAIAgentConfigMock
}));

describe("ChatPanel history behavior", () => {
  const storage = new Map<string, string>();

  beforeEach(() => {
    mocks.promptMock.mockReset();
    mocks.promptMock.mockResolvedValue(undefined);
    mocks.createSpendingAgentMock.mockReset();
    mocks.createSpendingAgentMock.mockImplementation(() => fakeAgent);
    mocks.fetchAIAgentConfigMock.mockReset();
    mocks.fetchAIAgentConfigMock.mockResolvedValue({
      proxy_url: "http://localhost",
      auth_token: "token",
      model: "Qwen/Qwen3.5-0.8B",
      default_model: "Qwen/Qwen3.5-0.8B",
      local_model: "Qwen/Qwen3.5-0.8B",
      preferred_model: "Qwen/Qwen3.5-0.8B",
      oauth_connected: true,
      oauth_provider: "openai-codex",
      available_models: [
        {
          id: "Qwen/Qwen3.5-0.8B",
          label: "Local Qwen (tiny)",
          source: "local",
          enabled: true,
          description: "Very small local fallback model. Private and easy to run, but weaker for deeper analysis."
        },
        {
          id: "gpt-5.2-codex",
          label: "ChatGPT",
          source: "oauth",
          enabled: true,
          description: "Uses your ChatGPT sign-in. Good for stronger reasoning when you choose it."
        }
      ]
    });
  });

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
    cleanup();
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

  it("defaults to the local model even when ChatGPT is connected and persists that model id", async () => {
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

    const modelSelect = await screen.findByLabelText("Chat model");
    expect(modelSelect).toHaveValue("Qwen/Qwen3.5-0.8B");
    expect(
      screen.getByText("Very small local fallback model. Private and easy to run, but weaker for deeper analysis.")
    ).toBeInTheDocument();

    fireEvent.change(await screen.findByPlaceholderText("Ask about spending, prices, and products..."), {
      target: { value: "preferred model prompt" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Reply for: preferred model prompt");

    const runCall = vi.mocked(fetch).mock.calls.find((call) => {
      const url = new URL(String(call[0]));
      return url.pathname.includes("/runs");
    });
    expect(runCall).toBeDefined();
    expect(JSON.parse(String(runCall?.[1]?.body))).toMatchObject({
      model_id: "Qwen/Qwen3.5-0.8B"
    });
  });

  it("allows switching to ChatGPT and persists the override", async () => {
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

    const modelSelect = await screen.findByLabelText("Chat model");
    fireEvent.change(modelSelect, { target: { value: "gpt-5.2-codex" } });

    await waitFor(() => {
      expect(screen.getByLabelText("Chat model")).toHaveValue("gpt-5.2-codex");
    });

    fireEvent.change(await screen.findByPlaceholderText("Ask about spending, prices, and products..."), {
      target: { value: "local model prompt" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await screen.findByText("Reply for: local model prompt");

    const runCall = [...vi.mocked(fetch).mock.calls].reverse().find((call) => {
      const url = new URL(String(call[0]));
      return url.pathname.includes("/runs");
    });
    expect(runCall).toBeDefined();
    expect(JSON.parse(String(runCall?.[1]?.body))).toMatchObject({
      model_id: "gpt-5.2-codex"
    });
    expect(storage.get("agent.chat.model.v1")).toBe("gpt-5.2-codex");
  });

  it("disables the model selector while a prompt is streaming", async () => {
    installLocalStorageStub();
    installChatApiFetchStub();
    let resolvePrompt: () => void = () => {
      throw new Error("Expected prompt resolution callback to be registered.");
    };
    mocks.promptMock.mockImplementation(
      () =>
        new Promise<undefined>((resolve) => {
          resolvePrompt = () => resolve(undefined);
        })
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

    fireEvent.change(await screen.findByPlaceholderText("Ask about spending, prices, and products..."), {
      target: { value: "streaming prompt" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Chat model")).toBeDisabled();
    });

    resolvePrompt();
    await screen.findByText("Reply for: streaming prompt");
    expect(screen.getByLabelText("Chat model")).not.toBeDisabled();
  });
});
