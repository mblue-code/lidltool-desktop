import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
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
        description:
          "Very small shipped local fallback model. Private and available by default, but weaker for deeper analysis."
      }
    ]
  }))
}));

describe("ChatWorkspacePage markdown rendering", () => {
  beforeEach(() => {
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
                    title: "Markdown thread",
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
                    message_id: "m-assistant-1",
                    thread_id: "t1",
                    role: "assistant",
                    content_json: [
                      {
                        type: "text",
                        text: "# Spending summary\n\nThe overall spend was down.\n\n- Weekly groceries\n- Household staples"
                      }
                    ],
                    tool_name: null,
                    tool_call_id: null,
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
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders assistant markdown in the workspace transcript", async () => {
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

    expect(
      await screen.findByRole("heading", { level: 1, name: "Spending summary" })
    ).toBeInTheDocument();
    expect(screen.getByText("The overall spend was down.")).toBeInTheDocument();
    expect(screen.getByText("Weekly groceries")).toBeInTheDocument();
    expect(screen.getByText("Household staples")).toBeInTheDocument();
  });
});
