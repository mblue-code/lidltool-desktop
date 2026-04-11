import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatWorkspacePage } from "@/pages/ChatWorkspacePage";

const promptMock = vi.fn(async () => undefined);

vi.mock("@/agent", () => ({
  createSpendingAgent: vi.fn(() => ({
    state: { messages: [] },
    replaceMessages: vi.fn(),
    prompt: promptMock,
    subscribe: vi.fn(() => () => undefined)
  }))
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

describe("ChatWorkspacePage", () => {
  beforeEach(() => {
    const storage = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => {
          storage.set(key, value);
        },
        removeItem: (key: string) => {
          storage.delete(key);
        }
      }
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

        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      })
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders split view with thread list and conversation", async () => {
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

    await screen.findByText("Chat");
    expect(await screen.findAllByText("Existing thread")).toHaveLength(2);
    expect(
      screen.getByPlaceholderText(/Ask about your spending, products/)
    ).toBeInTheDocument();
  });

  it("keeps new-thread draft selected until the user sends", async () => {
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

    await screen.findByText("Chat");
    fireEvent.click(screen.getByRole("button", { name: "New chat" }));

    expect(screen.getAllByText("Existing thread")).toHaveLength(1);
    expect(screen.getAllByText("New chat").length).toBeGreaterThan(0);
  });

  it("uses runtime path and persists run data instead of /stream", async () => {
    promptMock.mockClear();
    const requests: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();
        requests.push(`${method} ${url.pathname}`);

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
                  message_id: "m-user-1",
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
                stream_status: "streaming",
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

    await screen.findByText("Chat");
    fireEvent.change(screen.getByPlaceholderText(/Ask about your spending, products/), {
      target: { value: "hello" }
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(promptMock).toHaveBeenCalledWith("hello"));
    await waitFor(() => expect(requests).toContain("POST /api/v1/chat/threads/t1/runs"));
    expect(requests).not.toContain("POST /api/v1/chat/threads/t1/stream");
  });

  it("renders tool result messages in a distinct block", async () => {
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
              result: {
                items: [
                  {
                    message_id: "m-tool-1",
                    thread_id: "t1",
                    role: "tool",
                    content_json: [{ type: "text", text: "[]" }],
                    tool_name: "search_transactions",
                    tool_call_id: "call-1",
                    usage_json: null,
                    error: null,
                    created_at: "2026-02-22T00:00:00Z"
                  }
                ],
                total: 1
              },
              warnings: [],
              error: null
            })
          };
        }

        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      })
    );

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

    await screen.findByText("Visual analysis: Search Receipts (call-1)");
    expect(screen.getByText("[]")).toBeInTheDocument();
  });

  it("falls back to idle stream_status if run persistence and failure patch both fail", async () => {
    promptMock.mockReset();
    promptMock.mockImplementationOnce(async () => {
      throw new Error("agent failed");
    });
    const patchStatuses: string[] = [];
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
                  message_id: "m-user-1",
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
          const body = JSON.parse(String(init?.body ?? "{}")) as { stream_status?: string };
          if (body.stream_status) {
            patchStatuses.push(body.stream_status);
          }
          if (body.stream_status === "failed") {
            return { ok: false, status: 500, json: async () => ({ ok: false }) };
          }
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread_id: "t1",
                user_id: "u1",
                title: "Existing thread",
                stream_status: body.stream_status ?? "idle",
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
          return { ok: false, status: 503, json: async () => ({ ok: false }) };
        }

        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      })
    );

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

    await screen.findByText("Chat");
    fireEvent.change(screen.getByPlaceholderText(/Ask about your spending, products/), {
      target: { value: "hello" }
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(patchStatuses).toContain("streaming"));
    await waitFor(() => expect(patchStatuses).toContain("failed"));
    await waitFor(() => expect(patchStatuses).toContain("idle"));
  });

  it("reuses the same idempotency key when the first message write fails and user retries", async () => {
    promptMock.mockReset();
    promptMock.mockImplementation(async () => undefined);

    let postMessageAttempts = 0;
    const postedIdempotencyKeys: string[] = [];
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
          postMessageAttempts += 1;
          const body = JSON.parse(String(init?.body ?? "{}")) as { idempotency_key?: string };
          postedIdempotencyKeys.push(String(body.idempotency_key ?? ""));
          if (postMessageAttempts === 1) {
            return { ok: false, status: 503, json: async () => ({ ok: false }) };
          }
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
                  message_id: "m-user-1",
                  thread_id: "t1",
                  role: "user",
                  content_json: [{ type: "text", text: "hello" }],
                  tool_name: null,
                  tool_call_id: null,
                  idempotency_key: body.idempotency_key ?? null,
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
          const body = JSON.parse(String(init?.body ?? "{}")) as { stream_status?: string };
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                thread_id: "t1",
                user_id: "u1",
                title: "Existing thread",
                stream_status: body.stream_status ?? "idle",
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

    await screen.findByText("Chat");
    fireEvent.change(screen.getByPlaceholderText(/Ask about your spending, products/), {
      target: { value: "hello" }
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(postMessageAttempts).toBe(1));

    fireEvent.change(screen.getByPlaceholderText(/Ask about your spending, products/), {
      target: { value: "hello" }
    });
    await waitFor(() => expect(screen.getByRole("button", { name: "Send" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(postMessageAttempts).toBe(2));

    expect(postedIdempotencyKeys[0]).toMatch(/^msg-/);
    expect(postedIdempotencyKeys[1]).toBe(postedIdempotencyKeys[0]);
  });
});
