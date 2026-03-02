import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const OPTIONAL_API_KEY = import.meta.env.VITE_OPENCLAW_API_KEY || "";

const ChatThreadSchema = z.object({
  thread_id: z.string(),
  user_id: z.string(),
  title: z.string(),
  stream_status: z.enum(["idle", "streaming", "failed"]),
  created_at: z.string(),
  updated_at: z.string(),
  archived_at: z.string().nullable()
});

const ChatMessageSchema = z.object({
  message_id: z.string(),
  thread_id: z.string(),
  role: z.enum(["system", "user", "assistant", "tool"]),
  content_json: z.unknown(),
  tool_name: z.string().nullable(),
  tool_call_id: z.string().nullable(),
  idempotency_key: z.string().nullable().optional(),
  usage_json: z.record(z.string(), z.unknown()).nullable(),
  error: z.string().nullable(),
  created_at: z.string()
});

const ChatThreadListSchema = z.object({
  items: z.array(ChatThreadSchema),
  total: z.number()
});

const ChatMessageListSchema = z.object({
  items: z.array(ChatMessageSchema),
  total: z.number()
});

const ChatThreadCreateResultSchema = ChatThreadSchema;

const ChatThreadPatchResultSchema = ChatThreadSchema;

const ChatThreadDeleteResultSchema = z.object({
  deleted: z.boolean(),
  thread: ChatThreadSchema
});

const ChatMessageCreateResultSchema = z.object({
  thread: ChatThreadSchema,
  message: ChatMessageSchema
});

const ChatRunSchema = z.object({
  run_id: z.string(),
  thread_id: z.string(),
  message_id: z.string().nullable(),
  model_id: z.string(),
  prompt_tokens: z.number().nullable(),
  completion_tokens: z.number().nullable(),
  latency_ms: z.number().nullable(),
  status: z.enum(["ok", "error", "timeout"]),
  created_at: z.string()
});

const ChatRunPersistResultSchema = z.object({
  thread: ChatThreadSchema,
  messages: z.array(ChatMessageSchema),
  run: ChatRunSchema
});

export type ChatThread = z.infer<typeof ChatThreadSchema>;
export type ChatMessage = z.infer<typeof ChatMessageSchema>;
export type ChatThreadListResult = z.infer<typeof ChatThreadListSchema>;
export type ChatMessageListResult = z.infer<typeof ChatMessageListSchema>;
export type ChatMessageCreateResult = z.infer<typeof ChatMessageCreateResultSchema>;
export type ChatRunPersistResult = z.infer<typeof ChatRunPersistResultSchema>;

export type ChatStreamEvent = {
  type: string;
  contentIndex?: number;
  delta?: string;
  reason?: string;
  usage?: {
    input?: number;
    output?: number;
    totalTokens?: number;
  };
};

export async function listChatThreads(params?: {
  limit?: number;
  offset?: number;
  include_archived?: boolean;
}): Promise<ChatThreadListResult> {
  return apiClient.get("/api/v1/chat/threads", ChatThreadListSchema, params);
}

export async function createChatThread(payload?: {
  thread_id?: string;
  title?: string;
}): Promise<ChatThread> {
  return apiClient.post("/api/v1/chat/threads", ChatThreadCreateResultSchema, payload ?? {});
}

export async function getChatThread(threadId: string): Promise<ChatThread> {
  return apiClient.get(`/api/v1/chat/threads/${threadId}`, ChatThreadSchema);
}

export async function patchChatThread(
  threadId: string,
  payload: {
    title?: string;
    archived?: boolean;
    abandon_stream?: boolean;
    stream_status?: "idle" | "streaming" | "failed";
  }
): Promise<ChatThread> {
  return apiClient.patch(`/api/v1/chat/threads/${threadId}`, ChatThreadPatchResultSchema, payload);
}

export async function deleteChatThread(threadId: string): Promise<z.infer<typeof ChatThreadDeleteResultSchema>> {
  return apiClient.delete(`/api/v1/chat/threads/${threadId}`, ChatThreadDeleteResultSchema);
}

export async function listChatMessages(threadId: string): Promise<ChatMessageListResult> {
  return apiClient.get(`/api/v1/chat/threads/${threadId}/messages`, ChatMessageListSchema);
}

export async function createChatMessage(
  threadId: string,
  payload: {
    content: string;
    idempotency_key?: string;
  }
): Promise<ChatMessageCreateResult> {
  return apiClient.post(
    `/api/v1/chat/threads/${threadId}/messages`,
    ChatMessageCreateResultSchema,
    payload
  );
}

export async function persistChatRun(
  threadId: string,
  payload: {
    messages: any[];
    model_id?: string;
    prompt_tokens?: number;
    completion_tokens?: number;
    latency_ms?: number;
    status: "ok" | "error" | "timeout";
    error?: string;
  }
): Promise<ChatRunPersistResult> {
  return apiClient.post(`/api/v1/chat/threads/${threadId}/runs`, ChatRunPersistResultSchema, payload);
}

function streamHeaders(): HeadersInit {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (OPTIONAL_API_KEY && !headers.has("X-API-Key")) {
    headers.set("X-API-Key", OPTIONAL_API_KEY);
  }
  return headers;
}

export async function streamChatThread(
  threadId: string,
  payload: { model_id?: string },
  onEvent: (event: ChatStreamEvent) => void
): Promise<void> {
  const url = apiClient.buildUrl(`/api/v1/chat/threads/${threadId}/stream`);
  const response = await fetch(url.toString(), {
    method: "POST",
    credentials: "include",
    headers: streamHeaders(),
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`stream request failed with status ${response.status}`);
  }
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("stream response body is unavailable");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const lines = chunk
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.startsWith("data:"));
      for (const line of lines) {
        const payloadRaw = line.slice(5).trim();
        if (!payloadRaw) {
          continue;
        }
        const parsed = JSON.parse(payloadRaw) as ChatStreamEvent;
        onEvent(parsed);
      }
    }
  }
}
