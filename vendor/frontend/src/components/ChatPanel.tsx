import type { CSSProperties, MouseEvent as ReactMouseEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import DOMPurify from "dompurify";
import { marked } from "marked";

import { createSpendingAgent } from "@/agent";
import { ALL_TOOLS } from "@/agent/tools";
import { fetchAIAgentConfig } from "@/api/aiSettings";
import { ChatUiRenderer } from "@/chat/ui/ChatUiRenderer";
import {
  extractUiSpecsFromContent,
  extractUiSpecsFromDetails,
  messageTextFromContent
} from "@/chat/ui/content";
import {
  normalizeRuntimeMessagesForPersistence,
  sanitizeRuntimeMessagesForModel
} from "@/chat/ui/runtime-messages";
import { ChatUiSpec } from "@/chat/ui/spec";
import { createChatMessage, createChatThread, patchChatThread, persistChatRun } from "@/api/chat";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type ChatPanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  enabled: boolean;
  panelWidth: number;
  onPanelWidthChange: (next: number) => void;
  pageContext?: string | null;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  uiSpecs: ChatUiSpec[];
  toolName?: string | null;
  toolCallId?: string | null;
  tools: string[];
  costText: string | null;
};

const STORAGE_KEY = "agent.chat.v1";
const TOOL_LABELS = Object.fromEntries(ALL_TOOLS.map((tool) => [tool.name, tool.label]));
const PANEL_WIDTH_MIN = 320;

function generateId(): string {
  const randomUUID = globalThis.crypto?.randomUUID;
  if (typeof randomUUID === "function") {
    return randomUUID.call(globalThis.crypto);
  }
  return `id-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function extractUsage(messages: any[]): { prompt_tokens?: number; completion_tokens?: number } {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const usage = messages[index]?.usage;
    if (!usage || typeof usage !== "object") continue;
    const promptTokens = usage.prompt_tokens ?? usage.input;
    const completionTokens = usage.completion_tokens ?? usage.output;
    return {
      prompt_tokens: typeof promptTokens === "number" ? promptTokens : undefined,
      completion_tokens: typeof completionTokens === "number" ? completionTokens : undefined
    };
  }
  return {};
}
const PANEL_WIDTH_MAX = 860;

function clampPanelWidth(width: number): number {
  if (!Number.isFinite(width)) {
    return 420;
  }
  const viewportWidth = typeof window !== "undefined" ? window.innerWidth : 1440;
  const maxByViewport = Math.max(PANEL_WIDTH_MIN, Math.min(PANEL_WIDTH_MAX, viewportWidth - 280));
  return Math.min(maxByViewport, Math.max(PANEL_WIDTH_MIN, Math.round(width)));
}

function messageText(message: any): string {
  if (!message) {
    return "";
  }
  if (message.role === "user" && typeof message.content === "string") {
    return message.content;
  }
  if (message.role === "user") {
    return messageTextFromContent(message.content, "\n");
  }
  return messageTextFromContent(message.content, "");
}

function buildChatMessages(messages: any[]): ChatMessage[] {
  return messages
    .filter(
      (message) =>
        message?.role === "user" || message?.role === "assistant" || message?.role === "toolResult"
    )
    .map((message, index) => {
      const role: ChatMessage["role"] = message.role === "toolResult" ? "tool" : message.role;
      const rawCost = message?.usage?.cost?.total;
      const costText =
        typeof rawCost === "number" && Number.isFinite(rawCost) ? `${(rawCost * 100).toFixed(1)}¢` : null;
      const uiSpecs =
        role === "tool"
          ? Array.from(
              new Map(
                [...extractUiSpecsFromContent(message.content), ...extractUiSpecsFromDetails(message.details)].map(
                  (spec) => [JSON.stringify(spec), spec]
                )
              ).values()
            )
          : [];
      return {
        id: `${role}-${index}-${message.timestamp ?? Date.now()}`,
        role,
        content: messageText(message),
        uiSpecs,
        toolName: role === "tool" ? (typeof message.toolName === "string" ? message.toolName : "tool") : null,
        toolCallId: role === "tool" ? (typeof message.toolCallId === "string" ? message.toolCallId : null) : null,
        tools: [],
        costText: role === "assistant" ? costText : null
      };
    });
}

export function ChatPanel({
  open,
  onOpenChange,
  enabled,
  panelWidth,
  onPanelWidthChange,
  pageContext
}: ChatPanelProps) {
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState("");
  const [activeToolLabel, setActiveToolLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastPrompt, setLastPrompt] = useState<string | null>(null);
  const [lastIdempotencyKey, setLastIdempotencyKey] = useState<string | null>(null);
  const [panelThreadId, setPanelThreadId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const runMessagesRef = useRef<any[]>([]);
  const runStartedAtRef = useRef<number>(0);

  const configQuery = useQuery({
    queryKey: ["ai-agent-config"],
    queryFn: fetchAIAgentConfig,
    enabled: open && enabled
  });

  const agent = useMemo(() => {
    if (!configQuery.data) {
      return null;
    }
    return createSpendingAgent(
      configQuery.data.proxy_url,
      configQuery.data.auth_token,
      configQuery.data.model,
      { pageContext }
    );
  }, [configQuery.data, pageContext]);

  useEffect(() => {
    if (!agent) {
      return;
    }
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          agent.replaceMessages(sanitizeRuntimeMessagesForModel(parsed));
        }
      } catch {
        // Ignore malformed local storage payloads.
      }
    }
    setMessages(buildChatMessages(agent.state.messages as any[]));

    return agent.subscribe((event) => {
      if (event.type === "message_update") {
        if (event.assistantMessageEvent.type === "error") {
          setError(event.assistantMessageEvent.error.errorMessage || "Agent stream failed");
        }
        const message = event.message as any;
        if (message.role !== "assistant") {
          return;
        }
        const content = messageText(message);
        setMessages((previous) => {
          const next = [...previous];
          const last = next[next.length - 1];
          if (last?.role === "assistant") {
            last.content = content;
            return next;
          }
          next.push({
            id: `assistant-${Date.now()}`,
            role: "assistant",
            content,
            uiSpecs: [],
            tools: [],
            costText: null
          });
          return next;
        });
      }
      if (event.type === "tool_execution_start") {
        setActiveToolLabel(TOOL_LABELS[event.toolName] ?? event.toolName);
      }
      if (event.type === "tool_execution_end") {
        setActiveToolLabel(null);
        const label = TOOL_LABELS[event.toolName] ?? event.toolName;
        setMessages((previous) => {
          const next = [...previous];
          for (let index = next.length - 1; index >= 0; index -= 1) {
            if (next[index].role !== "assistant") {
              continue;
            }
            if (!next[index].tools.includes(label)) {
              next[index].tools = [...next[index].tools, label];
            }
            break;
          }
          return next;
        });
      }
      if (event.type === "agent_end") {
        runMessagesRef.current = Array.isArray(event.messages) ? (event.messages as any[]) : [];
        setIsStreaming(false);
        setMessages(buildChatMessages(agent.state.messages as any[]));
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(agent.state.messages));
      }
    });
  }, [agent]);

  useEffect(() => {
    if (!listRef.current) {
      return;
    }
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, activeToolLabel, open]);

  async function sendPrompt(promptOverride?: string): Promise<void> {
    const promptValue = promptOverride ?? input;
    if (!agent || !promptValue.trim() || isStreaming) {
      return;
    }
    const prompt = promptValue.trim();
    const retryingLastPrompt = typeof promptOverride === "string" && prompt === (lastPrompt ?? "");
    const idempotencyKey =
      retryingLastPrompt && lastIdempotencyKey ? lastIdempotencyKey : `msg-${generateId()}`;
    setInput("");
    setError(null);
    setIsStreaming(true);
    setLastPrompt(prompt);
    setLastIdempotencyKey(idempotencyKey);
    runMessagesRef.current = [];
    runStartedAtRef.current = performance.now();
    setMessages((previous) => [
      ...previous,
      {
        id: `user-${Date.now()}`,
        role: "user",
        content: prompt,
        uiSpecs: [],
        tools: [],
        costText: null
      },
      {
        id: `assistant-${Date.now() + 1}`,
        role: "assistant",
        content: "",
        uiSpecs: [],
        tools: [],
        costText: null
      }
    ]);

    let threadId = panelThreadId;
    let runPersisted = false;

    try {
      if (!threadId) {
        threadId = generateId();
        setPanelThreadId(threadId);
        await createChatThread({ thread_id: threadId, title: prompt.slice(0, 60) });
      }
      await createChatMessage(threadId, { content: prompt, idempotency_key: idempotencyKey });
      await patchChatThread(threadId, { stream_status: "streaming" });

      await agent.prompt(prompt);

      const elapsedMs = Math.max(1, Math.round(performance.now() - runStartedAtRef.current));
      const persistenceMessages = normalizeRuntimeMessagesForPersistence(runMessagesRef.current);
      await persistChatRun(threadId, {
        messages: persistenceMessages,
        model_id: configQuery.data?.model,
        latency_ms: elapsedMs,
        status: "ok",
        ...extractUsage(runMessagesRef.current)
      });
      runPersisted = true;
    } catch (nextError) {
      const message = nextError instanceof Error ? nextError.message : "Agent request failed";
      setError(message);
      if (threadId) {
        try {
          const elapsedMs = Math.max(1, Math.round(performance.now() - runStartedAtRef.current));
          const persistenceMessages = normalizeRuntimeMessagesForPersistence(runMessagesRef.current);
          await persistChatRun(threadId, {
            messages: persistenceMessages,
            model_id: configQuery.data?.model,
            latency_ms: elapsedMs,
            status: "error",
            error: message
          });
          runPersisted = true;
        } catch {
          try { await patchChatThread(threadId, { stream_status: "failed" }); } catch { /* ignore */ }
        }
      }
    } finally {
      if (threadId && !runPersisted) {
        try { await patchChatThread(threadId, { stream_status: "idle" }); } catch { /* ignore */ }
      }
      setIsStreaming(false);
      void queryClient.invalidateQueries({ queryKey: ["chat", "threads"] });
    }
  }

  function startNewChat(): void {
    if (!agent) {
      return;
    }
    agent.clearMessages();
    setMessages([]);
    setError(null);
    setLastPrompt(null);
    setLastIdempotencyKey(null);
    setPanelThreadId(null);
    window.localStorage.removeItem(STORAGE_KEY);
  }

  function startResize(event: ReactMouseEvent<HTMLDivElement>): void {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    const startingX = event.clientX;
    const startingWidth = panelWidth;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const handleMove = (moveEvent: MouseEvent) => {
      const delta = startingX - moveEvent.clientX;
      onPanelWidthChange(clampPanelWidth(startingWidth + delta));
    };

    const stopResize = () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", stopResize);
    };

    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", stopResize);
  }

  if (!open) {
    return null;
  }

  const panelStyle = {
    "--chat-panel-width": `${panelWidth}px`
  } as CSSProperties;

  return (
    <aside
      className="fixed bottom-0 right-0 top-0 z-40 w-full border-l bg-background shadow-2xl md:w-[var(--chat-panel-width)]"
      style={panelStyle}
    >
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize chat panel"
        className="absolute bottom-0 left-0 top-0 z-10 hidden w-3 -translate-x-1/2 cursor-col-resize items-stretch md:flex"
        onMouseDown={startResize}
      >
        <span className="mx-auto w-px bg-border/80 transition-colors hover:bg-primary/70" />
      </div>
      <div className="flex h-full flex-col">
        <header className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-sm font-semibold">AI Assistant</h2>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={startNewChat}>
              New chat
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          </div>
        </header>

        <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {!enabled ? <p className="text-sm text-muted-foreground">Configure AI settings to use chat.</p> : null}
          {messages.map((message) => (
            <div
              key={message.id}
              className={cn("max-w-[92%] space-y-1", message.role === "user" ? "ml-auto text-right" : "mr-auto")}
            >
              <div
                className={cn(
                  "rounded-lg px-3 py-2 text-sm",
                  message.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : message.role === "tool"
                      ? "border border-dashed bg-muted/25"
                      : "bg-muted"
                )}
              >
                {message.role === "assistant" ? (
                  <div
                    className="prose prose-sm max-w-none"
                    dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(marked.parse(message.content || "") as string) }}
                  />
                ) : message.role === "tool" ? (
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
                      <p className="mt-2 text-xs text-muted-foreground">(no output)</p>
                    ) : null}
                  </details>
                ) : (
                  <p>{message.content}</p>
                )}
              </div>
              {message.tools.length > 0 ? (
                <div className="flex flex-wrap gap-1 text-xs text-muted-foreground">
                  {message.tools.map((tool) => (
                    <span key={`${message.id}-${tool}`} className="rounded-full border px-2 py-0.5">
                      Used: {tool}
                    </span>
                  ))}
                </div>
              ) : null}
              {message.role === "assistant" && message.costText ? (
                <p className="text-xs text-muted-foreground">{message.costText}</p>
              ) : null}
            </div>
          ))}
          {activeToolLabel ? (
            <p className="text-xs text-muted-foreground">Searching with {activeToolLabel}...</p>
          ) : null}
          {error ? (
            <div className="space-y-2 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
              <p>{error}</p>
              <Button
                size="sm"
                variant="outline"
                className="h-7"
                disabled={isStreaming || !lastPrompt}
                onClick={() => void sendPrompt(lastPrompt || undefined)}
              >
                Retry
              </Button>
            </div>
          ) : null}
        </div>

        <div className="border-t px-4 py-3">
          <div className="space-y-2">
            <Textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask about spending, prices, and products..."
              disabled={!enabled || isStreaming || !agent}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendPrompt();
                }
              }}
            />
            <Button
              className="w-full"
              disabled={!enabled || isStreaming || !input.trim() || !agent}
              onClick={() => void sendPrompt()}
            >
              {isStreaming ? "Thinking..." : "Send"}
            </Button>
          </div>
        </div>
      </div>
    </aside>
  );
}
