import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { createSpendingAgent } from "@/agent";
import { ALL_TOOLS } from "@/agent/tools";
import { fetchAIAgentConfig } from "@/api/aiSettings";
import {
  ChatMessage,
  createChatMessage,
  createChatThread,
  listChatMessages,
  listChatThreads,
  patchChatThread,
  persistChatRun
} from "@/api/chat";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChatUiRenderer } from "@/chat/ui/ChatUiRenderer";
import { extractUiSpecsFromContent, messageTextFromContent } from "@/chat/ui/content";
import { normalizeRuntimeMessagesForPersistence } from "@/chat/ui/runtime-messages";
import { ChatUiSpec } from "@/chat/ui/spec";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type DisplayMessage = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  uiSpecs: ChatUiSpec[];
  toolName?: string | null;
  toolCallId?: string | null;
};

const TOOL_LABELS = Object.fromEntries(ALL_TOOLS.map((tool) => [tool.name, tool.label]));

function runtimeMessageText(message: any): string {
  if (!message) {
    return "";
  }
  if (message.role === "user") {
    if (typeof message.content === "string") {
      return message.content;
    }
    if (Array.isArray(message.content)) {
      return messageTextFromContent(message.content, "\n");
    }
    return "";
  }
  if (message.role === "assistant") {
    return messageTextFromContent(message.content, "");
  }
  return "";
}

function toDisplayMessages(messages: ChatMessage[]): DisplayMessage[] {
  return messages
    .filter((message): message is ChatMessage & { role: "user" | "assistant" | "tool" } =>
      message.role === "user" || message.role === "assistant" || message.role === "tool"
    )
    .map((message) => ({
      id: message.message_id,
      role: message.role,
      content: messageTextFromContent(message.content_json, ""),
      uiSpecs: extractUiSpecsFromContent(message.content_json),
      toolName: message.tool_name,
      toolCallId: message.tool_call_id
    }));
}

function toAgentContextMessages(messages: ChatMessage[]): any[] {
  const context: any[] = [];
  for (const message of messages) {
    if (message.role === "user") {
      context.push({ role: "user", content: messageTextFromContent(message.content_json, "") });
      continue;
    }
    if (message.role === "assistant") {
      const content = Array.isArray(message.content_json)
        ? message.content_json
        : [{ type: "text", text: messageTextFromContent(message.content_json, "") }];
      context.push({ role: "assistant", content });
      continue;
    }
    if (message.role === "tool") {
      const contentText = messageTextFromContent(message.content_json, "\n");
      const content = contentText ? [{ type: "text", text: contentText }] : [];
      context.push({
        role: "toolResult",
        toolCallId: message.tool_call_id ?? `tool-${message.message_id}`,
        toolName: message.tool_name ?? "tool",
        content
      });
    }
  }
  return context;
}

function extractUsage(messages: any[]): { prompt_tokens?: number; completion_tokens?: number } {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const usage = messages[index]?.usage;
    if (!usage || typeof usage !== "object") {
      continue;
    }
    const promptTokens = usage.prompt_tokens ?? usage.input;
    const completionTokens = usage.completion_tokens ?? usage.output;
    return {
      prompt_tokens: typeof promptTokens === "number" ? promptTokens : undefined,
      completion_tokens: typeof completionTokens === "number" ? completionTokens : undefined
    };
  }
  return {};
}

function fallbackThreadId(): string {
  const randomUUID = globalThis.crypto?.randomUUID;
  if (typeof randomUUID === "function") {
    return randomUUID.call(globalThis.crypto);
  }
  return `thread-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function createMessageIdempotencyKey(): string {
  return `msg-${fallbackThreadId()}`;
}

export function ChatWorkspacePage() {
  const queryClient = useQueryClient();
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [isComposingNewThread, setIsComposingNewThread] = useState(false);
  const [input, setInput] = useState("");
  const [draftIdempotencyKey, setDraftIdempotencyKey] = useState<string>(() =>
    createMessageIdempotencyKey()
  );
  const [streaming, setStreaming] = useState(false);
  const [activeToolLabel, setActiveToolLabel] = useState<string | null>(null);
  const [pendingUserMessage, setPendingUserMessage] = useState<string | null>(null);
  const [pendingAssistantMessage, setPendingAssistantMessage] = useState("");
  const [streamError, setStreamError] = useState<string | null>(null);
  const runMessagesRef = useRef<any[]>([]);
  const runStartedAtRef = useRef<number>(0);

  const configQuery = useQuery({
    queryKey: ["ai-agent-config"],
    queryFn: fetchAIAgentConfig
  });

  const agent = useMemo(() => {
    if (!configQuery.data) {
      return null;
    }
    return createSpendingAgent(
      configQuery.data.proxy_url,
      configQuery.data.auth_token,
      configQuery.data.model
    );
  }, [configQuery.data]);

  const threadsQuery = useQuery({
    queryKey: ["chat", "threads"],
    queryFn: () => listChatThreads({ limit: 200, offset: 0 })
  });

  const selectedThread = useMemo(
    () => threadsQuery.data?.items.find((thread) => thread.thread_id === selectedThreadId) ?? null,
    [selectedThreadId, threadsQuery.data?.items]
  );

  const messagesQuery = useQuery({
    queryKey: ["chat", "messages", selectedThreadId],
    enabled: Boolean(selectedThreadId),
    queryFn: () => listChatMessages(selectedThreadId as string)
  });

  useEffect(() => {
    if (selectedThreadId || isComposingNewThread) {
      return;
    }
    const firstThread = threadsQuery.data?.items[0];
    if (firstThread) {
      setSelectedThreadId(firstThread.thread_id);
    }
  }, [isComposingNewThread, selectedThreadId, threadsQuery.data?.items]);

  useEffect(() => {
    if (!agent) {
      return;
    }
    return agent.subscribe((event) => {
      if (event.type === "message_update") {
        if (event.assistantMessageEvent.type === "error") {
          setStreamError(event.assistantMessageEvent.error.errorMessage || "Agent stream failed");
        }
        const message = event.message as any;
        if (message.role === "assistant") {
          setPendingAssistantMessage(runtimeMessageText(message));
        }
      }
      if (event.type === "tool_execution_start") {
        setActiveToolLabel(TOOL_LABELS[event.toolName] ?? event.toolName);
      }
      if (event.type === "tool_execution_end") {
        setActiveToolLabel(null);
      }
      if (event.type === "agent_end") {
        runMessagesRef.current = Array.isArray(event.messages) ? (event.messages as any[]) : [];
        const latestAssistant = [...(agent.state.messages as any[])].reverse().find((entry) => entry?.role === "assistant");
        if (latestAssistant) {
          setPendingAssistantMessage(runtimeMessageText(latestAssistant));
        }
      }
    });
  }, [agent]);

  const abandonMutation = useMutation({
    mutationFn: async (threadId: string) =>
      patchChatThread(threadId, { abandon_stream: true, stream_status: "idle" }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["chat", "threads"] }),
        queryClient.invalidateQueries({ queryKey: ["chat", "messages", selectedThreadId] })
      ]);
    }
  });

  const persistedMessages = useMemo(
    () => toDisplayMessages(messagesQuery.data?.items ?? []),
    [messagesQuery.data?.items]
  );

  const displayMessages = useMemo(() => {
    if (!streaming) {
      return persistedMessages;
    }
    const next = [...persistedMessages];
    if (pendingUserMessage) {
      next.push({
        id: "pending-user",
        role: "user",
        content: pendingUserMessage,
        uiSpecs: []
      });
      next.push({
        id: "pending-assistant",
        role: "assistant",
        content: pendingAssistantMessage,
        uiSpecs: []
      });
    }
    return next;
  }, [pendingAssistantMessage, pendingUserMessage, persistedMessages, streaming]);

  async function handleSend(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (streaming) {
      return;
    }
    const content = input.trim();
    if (!content) {
      return;
    }
    if (!agent || !configQuery.data) {
      setStreamError("AI agent configuration is unavailable.");
      return;
    }

    const targetThreadId = selectedThreadId ?? fallbackThreadId();
    if (!selectedThreadId) {
      setSelectedThreadId(targetThreadId);
      setIsComposingNewThread(false);
      await createChatThread({ thread_id: targetThreadId, title: content.slice(0, 60) });
    }
    setInput("");
    setStreamError(null);
    setStreaming(true);
    setActiveToolLabel(null);
    setPendingUserMessage(content);
    setPendingAssistantMessage("");
    runMessagesRef.current = [];
    runStartedAtRef.current = performance.now();
    let runPersisted = false;
    let userMessagePersisted = false;

    try {
      const contextMessages = toAgentContextMessages(messagesQuery.data?.items ?? []);
      agent.replaceMessages(contextMessages);

      await createChatMessage(targetThreadId, {
        content,
        idempotency_key: draftIdempotencyKey
      });
      userMessagePersisted = true;
      await patchChatThread(targetThreadId, { stream_status: "streaming" });

      await agent.prompt(content);

      const elapsedMs = Math.max(1, Math.round(performance.now() - runStartedAtRef.current));
      const runMessages = runMessagesRef.current;
      const persistenceMessages = normalizeRuntimeMessagesForPersistence(runMessages);
      const usage = extractUsage(runMessages);
      await persistChatRun(targetThreadId, {
        messages: persistenceMessages,
        model_id: configQuery.data.model,
        latency_ms: elapsedMs,
        status: "ok",
        ...usage
      });
      runPersisted = true;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Chat stream failed";
      setStreamError(message);
      const elapsedMs = Math.max(1, Math.round(performance.now() - runStartedAtRef.current));
      try {
        const persistenceMessages = normalizeRuntimeMessagesForPersistence(runMessagesRef.current);
        await persistChatRun(targetThreadId, {
          messages: persistenceMessages,
          model_id: configQuery.data.model,
          latency_ms: elapsedMs,
          status: "error",
          error: message
        });
        runPersisted = true;
      } catch {
        try {
          await patchChatThread(targetThreadId, { stream_status: "failed" });
        } catch {
          // Ignore; final idle cleanup below is the last-resort recovery.
        }
      }
    } finally {
      if (!runPersisted) {
        try {
          await patchChatThread(targetThreadId, { stream_status: "idle" });
        } catch {
          // Ignore cleanup failures; the reconnect banner still allows manual recovery.
        }
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["chat", "threads"] }),
        queryClient.invalidateQueries({ queryKey: ["chat", "messages", targetThreadId] })
      ]);
      setStreaming(false);
      setActiveToolLabel(null);
      setPendingUserMessage(null);
      setPendingAssistantMessage("");
      if (userMessagePersisted) {
        setDraftIdempotencyKey(createMessageIdempotencyKey());
      }
    }
  }

  const threads = threadsQuery.data?.items ?? [];

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Chat</h2>
          <p className="text-sm text-muted-foreground">Persistent threads with server-side history.</p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setSelectedThreadId(null);
            setIsComposingNewThread(true);
            setStreamError(null);
          }}
        >
          New chat
        </Button>
      </div>

      <div className="grid min-h-[70vh] gap-4 md:grid-cols-[280px_1fr]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b py-3">
            <h3 className="text-sm font-semibold">Threads</h3>
          </CardHeader>
          <CardContent className="max-h-[70vh] space-y-2 overflow-y-auto py-3">
            {threadsQuery.isPending ? <p className="text-sm text-muted-foreground">Loading threads...</p> : null}
            {threads.length === 0 ? <p className="text-sm text-muted-foreground">No threads yet.</p> : null}
            {threads.map((thread) => (
              <button
                key={thread.thread_id}
                type="button"
                onClick={() => {
                  setSelectedThreadId(thread.thread_id);
                  setIsComposingNewThread(false);
                }}
                className={cn(
                  "w-full rounded-md border p-2 text-left transition-colors",
                  selectedThreadId === thread.thread_id
                    ? "border-primary bg-primary/5"
                    : "border-border hover:bg-muted/40"
                )}
              >
                <p className="truncate text-sm font-medium">{thread.title}</p>
                <p className="mt-1 text-xs text-muted-foreground">{new Date(thread.updated_at).toLocaleString()}</p>
                {thread.stream_status !== "idle" ? (
                  <Badge variant={thread.stream_status === "failed" ? "destructive" : "secondary"} className="mt-2">
                    {thread.stream_status}
                  </Badge>
                ) : null}
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="flex min-h-[70vh] flex-col">
          <CardHeader className="border-b py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="truncate text-sm font-semibold">
                {selectedThread?.title ?? (isComposingNewThread ? "New chat" : "Chat")}
              </h3>
              {selectedThread ? (
                <Badge variant={selectedThread.stream_status === "failed" ? "destructive" : "secondary"}>
                  {selectedThread.stream_status}
                </Badge>
              ) : null}
            </div>
          </CardHeader>

          <CardContent className="flex flex-1 flex-col gap-3 py-4">
            {selectedThread?.stream_status === "streaming" ? (
              <Alert>
                <AlertTitle>Response may have been interrupted</AlertTitle>
                <AlertDescription className="flex items-center justify-between gap-2">
                  <span>Thread reconnect detected while generation was still active.</span>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={abandonMutation.isPending}
                    onClick={() => void abandonMutation.mutateAsync(selectedThread.thread_id)}
                  >
                    Abandon stream
                  </Button>
                </AlertDescription>
              </Alert>
            ) : null}

            {activeToolLabel ? (
              <p className="text-xs text-muted-foreground">Searching with {activeToolLabel}...</p>
            ) : null}

            {streamError ? (
              <Alert variant="destructive">
                <AlertTitle>Chat failed</AlertTitle>
                <AlertDescription>{streamError}</AlertDescription>
              </Alert>
            ) : null}

            <div className="flex-1 space-y-3 overflow-y-auto rounded-md border bg-muted/20 p-3">
              {messagesQuery.isPending && selectedThreadId ? (
                <p className="text-sm text-muted-foreground">Loading conversation...</p>
              ) : null}
              {displayMessages.length === 0 ? (
                <p className="text-sm text-muted-foreground">Send a message to start this thread.</p>
              ) : null}
              {displayMessages.map((message) => (
                <div
                  key={message.id}
                  className={cn(
                    "max-w-[92%] rounded-lg px-3 py-2 text-sm",
                    message.role === "user"
                      ? "ml-auto bg-primary text-primary-foreground"
                      : message.role === "tool"
                        ? "mr-auto border border-dashed bg-muted/30"
                        : "mr-auto bg-background"
                  )}
                >
                  {message.role === "tool" ? (
                    <details>
                      <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                        Tool result: {message.toolName ?? "tool"}
                        {message.toolCallId ? ` (${message.toolCallId})` : ""}
                      </summary>
                      {message.uiSpecs.length > 0 ? (
                        <div className="mt-2 space-y-2">
                          {message.uiSpecs.map((spec, index) => (
                            <ChatUiRenderer key={`${message.id}-ui-${index}`} spec={spec} />
                          ))}
                        </div>
                      ) : null}
                      {message.content ? (
                        <pre className="mt-2 whitespace-pre-wrap text-xs">{message.content}</pre>
                      ) : message.uiSpecs.length === 0 ? (
                        <pre className="mt-2 whitespace-pre-wrap text-xs">(no output)</pre>
                      ) : null}
                    </details>
                  ) : (
                    message.content || (message.role === "assistant" && streaming ? "..." : "")
                  )}
                </div>
              ))}
            </div>

            <form className="space-y-2" onSubmit={(event) => void handleSend(event)}>
              <Textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey && !streaming && input.trim()) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder="Ask about your spending, products, or trends... (Enter to send, Shift+Enter for newline)"
                rows={4}
                disabled={streaming}
              />
              <div className="flex justify-end">
                <Button type="submit" disabled={streaming || input.trim().length === 0 || !agent}>
                  {streaming ? "Generating..." : "Send"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
