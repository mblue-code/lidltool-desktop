import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatWorkspacePage } from "@/pages/ChatWorkspacePage";

const mocks = vi.hoisted(() => ({
  promptMock: vi.fn(async () => undefined),
  createSpendingAgentMock: vi.fn(),
  fetchAIAgentConfigMock: vi.fn()
}));

class FakeAgent {
  state = { messages: [] as any[] };

  replaceMessages = vi.fn((messages: any[]) => {
    this.state.messages = [...messages];
  });

  subscribe = vi.fn(() => () => undefined);

  async prompt(): Promise<void> {
    await mocks.promptMock();
  }
}

vi.mock("@/agent", () => ({
  createSpendingAgent: mocks.createSpendingAgentMock
}));

vi.mock("@/api/aiSettings", () => ({
  fetchAIAgentConfig: mocks.fetchAIAgentConfigMock
}));

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  render(
    <QueryClientProvider client={queryClient}>
      <ChatWorkspacePage />
    </QueryClientProvider>
  );
}

describe("ChatWorkspacePage model selector", () => {
  const storage = new Map<string, string>();

  beforeEach(() => {
    const localStorageStub = {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        storage.set(key, value);
      },
      removeItem: (key: string) => {
        storage.delete(key);
      }
    };
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: localStorageStub
    });

    mocks.promptMock.mockReset();
    mocks.promptMock.mockResolvedValue(undefined);
    mocks.createSpendingAgentMock.mockReset();
    mocks.createSpendingAgentMock.mockImplementation(() => new FakeAgent());
  });

  afterEach(() => {
    cleanup();
    storage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("defaults to the local tiny model and persists it for runs", async () => {
    mocks.fetchAIAgentConfigMock.mockResolvedValue({
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
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();

        if (url.pathname === "/api/v1/chat/threads" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                items: [
                  {
                    thread_id: "t1",
                    user_id: "u1",
                    title: "Existing thread",
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
          };
        }

        if (url.pathname === "/api/v1/chat/threads/t1/messages" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: { items: [], total: 0 },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/chat/threads/t1/messages" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread: {
                  thread_id: "t1",
                  user_id: "u1",
                  title: "Existing thread",
                  stream_status: "idle",
                  created_at: "2026-02-22T00:00:00Z",
                  updated_at: "2026-02-22T00:00:00Z",
                  archived_at: null
                },
                message: {
                  message_id: "m1",
                  thread_id: "t1",
                  role: "user",
                  content_json: [{ type: "text", text: "hello" }],
                  tool_name: null,
                  tool_call_id: null,
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

        if (url.pathname === "/api/v1/chat/threads/t1" && method === "PATCH") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread_id: "t1",
                user_id: "u1",
                title: "Existing thread",
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

        if (url.pathname === "/api/v1/chat/threads/t1/runs" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread: {
                  thread_id: "t1",
                  user_id: "u1",
                  title: "Existing thread",
                  stream_status: "idle",
                  created_at: "2026-02-22T00:00:00Z",
                  updated_at: "2026-02-22T00:00:00Z",
                  archived_at: null
                },
                messages: [],
                run: {
                  run_id: "r1",
                  thread_id: "t1",
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

    renderPage();

    expect(await screen.findByLabelText("Model")).toHaveValue("qwen3.5:0.8b");
    expect(
      screen.getByText(
        "Very small shipped local fallback model. Private and available by default, but weaker for deeper analysis."
      )
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(mocks.createSpendingAgentMock).toHaveBeenCalledWith(
        "http://localhost",
        "token",
        "qwen3.5:0.8b"
      );
    });

    fireEvent.change(screen.getByPlaceholderText(/Ask about your spending, products/), {
      target: { value: "hello" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      const runCall = vi.mocked(fetch).mock.calls.find((call) => {
        const url = new URL(String(call[0]));
        return url.pathname === "/api/v1/chat/threads/t1/runs";
      });
      expect(runCall).toBeDefined();
      expect(JSON.parse(String(runCall?.[1]?.body))).toMatchObject({
        model_id: "qwen3.5:0.8b"
      });
    });
  });

  it("keeps the local tiny model as default when ChatGPT is connected and allows switching", async () => {
    mocks.fetchAIAgentConfigMock.mockResolvedValue({
      proxy_url: "http://localhost",
      auth_token: "token",
      model: "qwen3.5:0.8b",
      default_model: "qwen3.5:0.8b",
      local_model: "qwen3.5:0.8b",
      preferred_model: "qwen3.5:0.8b",
      oauth_provider: "openai-codex",
      oauth_connected: true,
      available_models: [
        {
          id: "qwen3.5:0.8b",
          label: "Local Qwen (tiny)",
          source: "local",
          enabled: true,
          description: "Very small shipped local fallback model. Private and available by default, but weaker for deeper analysis."
        },
        {
          id: "gpt-5.2-codex",
          label: "ChatGPT",
          source: "oauth",
          enabled: true,
          description: "Uses your ChatGPT sign-in when connected."
        }
      ]
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();

        if (url.pathname === "/api/v1/chat/threads" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                items: [
                  {
                    thread_id: "t1",
                    user_id: "u1",
                    title: "Existing thread",
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
          };
        }

        if (url.pathname === "/api/v1/chat/threads/t1/messages" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: { items: [], total: 0 },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/chat/threads/t1/messages" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread: {
                  thread_id: "t1",
                  user_id: "u1",
                  title: "Existing thread",
                  stream_status: "idle",
                  created_at: "2026-02-22T00:00:00Z",
                  updated_at: "2026-02-22T00:00:00Z",
                  archived_at: null
                },
                message: {
                  message_id: "m1",
                  thread_id: "t1",
                  role: "user",
                  content_json: [{ type: "text", text: "hello" }],
                  tool_name: null,
                  tool_call_id: null,
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

        if (url.pathname === "/api/v1/chat/threads/t1" && method === "PATCH") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread_id: "t1",
                user_id: "u1",
                title: "Existing thread",
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

        if (url.pathname === "/api/v1/chat/threads/t1/runs" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread: {
                  thread_id: "t1",
                  user_id: "u1",
                  title: "Existing thread",
                  stream_status: "idle",
                  created_at: "2026-02-22T00:00:00Z",
                  updated_at: "2026-02-22T00:00:00Z",
                  archived_at: null
                },
                messages: [],
                run: {
                  run_id: "r1",
                  thread_id: "t1",
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

    renderPage();

    expect(await screen.findByLabelText("Model")).toHaveValue("qwen3.5:0.8b");

    fireEvent.change(screen.getByLabelText("Model"), {
      target: { value: "gpt-5.2-codex" }
    });

    await waitFor(() => {
      expect(mocks.createSpendingAgentMock).toHaveBeenLastCalledWith(
        "http://localhost",
        "token",
        "gpt-5.2-codex"
      );
    });

    fireEvent.change(screen.getByPlaceholderText(/Ask about your spending, products/), {
      target: { value: "hello" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      const runCall = vi.mocked(fetch).mock.calls.find((call) => {
        const url = new URL(String(call[0]));
        return url.pathname === "/api/v1/chat/threads/t1/runs";
      });
      expect(runCall).toBeDefined();
      expect(JSON.parse(String(runCall?.[1]?.body))).toMatchObject({
        model_id: "gpt-5.2-codex"
      });
    });
  });
});
