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
  });

  it("defaults to the local model when OAuth is not connected", async () => {
    mocks.fetchAIAgentConfigMock.mockResolvedValue({
      proxy_url: "http://localhost",
      auth_token: "token",
      model: "Qwen/Qwen3.5-0.8B",
      default_model: "Qwen/Qwen3.5-0.8B",
      local_model: "Qwen/Qwen3.5-0.8B",
      preferred_model: "Qwen/Qwen3.5-0.8B",
      oauth_provider: null,
      oauth_connected: false,
      available_models: [
        { id: "Qwen/Qwen3.5-0.8B", label: "Qwen", source: "local", enabled: true }
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
                  model_id: "Qwen/Qwen3.5-0.8B",
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

    const modelSelect = await screen.findByLabelText("Model");
    expect(modelSelect).toHaveValue("Qwen/Qwen3.5-0.8B");
    await waitFor(() => {
      expect(mocks.createSpendingAgentMock).toHaveBeenCalledWith(
        "http://localhost",
        "token",
        "Qwen/Qwen3.5-0.8B"
      );
    });

    fireEvent.change(screen.getByPlaceholderText(/Ask about your spending, products, or trends/), {
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
        model_id: "Qwen/Qwen3.5-0.8B"
      });
    });
  });

  it("prefers ChatGPT when connected and allows switching back to the local model", async () => {
    mocks.fetchAIAgentConfigMock.mockResolvedValue({
      proxy_url: "http://localhost",
      auth_token: "token",
      model: "gpt-5.2-codex",
      default_model: "Qwen/Qwen3.5-0.8B",
      local_model: "Qwen/Qwen3.5-0.8B",
      preferred_model: "gpt-5.2-codex",
      oauth_provider: "openai-codex",
      oauth_connected: true,
      available_models: [
        { id: "Qwen/Qwen3.5-0.8B", label: "Qwen", source: "local", enabled: true },
        { id: "gpt-5.2-codex", label: "ChatGPT", source: "oauth", enabled: true }
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
                  model_id: "Qwen/Qwen3.5-0.8B",
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

    const modelSelect = await screen.findByLabelText("Model");
    expect(modelSelect).toHaveValue("gpt-5.2-codex");

    fireEvent.change(modelSelect, { target: { value: "Qwen/Qwen3.5-0.8B" } });
    await waitFor(() => {
      expect(screen.getByLabelText("Model")).toHaveValue("Qwen/Qwen3.5-0.8B");
      expect(mocks.createSpendingAgentMock).toHaveBeenLastCalledWith(
        "http://localhost",
        "token",
        "Qwen/Qwen3.5-0.8B"
      );
    });

    fireEvent.change(screen.getByPlaceholderText(/Ask about your spending, products, or trends/), {
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
        model_id: "Qwen/Qwen3.5-0.8B"
      });
    });

    expect(JSON.parse(storage.get("chat.workspace.model-selection.v1") ?? "{}")).toMatchObject({
      t1: "Qwen/Qwen3.5-0.8B"
    });
  });
});
