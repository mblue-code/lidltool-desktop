import { FormEvent, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { createSpendingAgent } from "@/agent";
import { ALL_TOOLS } from "@/agent/tools";
import { fetchAIAgentConfig } from "@/api/aiSettings";
import { fetchOfferMerchantItems, type OfferSource, type OfferWatchlist } from "@/api/offers";
import {
  enabledAgentModels,
  readStoredString,
  resolveAgentModelSelection,
  writeStoredString
} from "@/chat/model-selection";
import { messageTextFromContent } from "@/chat/ui/content";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type OfferAgentCardProps = {
  aiEnabled: boolean;
  sources: OfferSource[];
  watchlists: OfferWatchlist[];
};

type OfferAssistantMessage = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  toolName?: string | null;
};

const OFFERS_AGENT_MODEL_STORAGE_KEY = "offers.agent.model.v1";
const TOOL_LABELS = Object.fromEntries(ALL_TOOLS.map((tool) => [tool.name, tool.label]));
const OFFER_PAGE_CONTEXT = [
  "Page context: Offers.",
  "This route is agent-first.",
  "Offer sources are merchant offer URLs created in the frontend.",
  "Use offer tools to create, update, and remove sources; inspect merchant purchase history; create watchlists; trigger refreshes; and create or update offer_refresh automations.",
  "Never claim there is a deterministic fallback or hidden internet-wide crawling."
].join(" ");

const PROMPT_SUGGESTIONS = [
  "Add an offer source for https://www.edeka.de/maerkte/402268/angebote/ and refresh it every Monday at 20:00.",
  "Watch for oat milk at https://www.edeka.de/maerkte/402268/angebote/ and only alert me if the discount is at least 20%.",
  "Use my existing dm purchases to set up a diaper watchlist and refresh offers every Monday at 08:00."
];

function runtimeMessageText(message: any): string {
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

function buildMessages(messages: any[]): OfferAssistantMessage[] {
  return messages
    .filter(
      (message) =>
        message?.role === "user" || message?.role === "assistant" || message?.role === "toolResult"
    )
    .map((message, index) => ({
      id: `${message.role}-${index}-${message.timestamp ?? Date.now()}`,
      role: message.role === "toolResult" ? "tool" : message.role,
      content: runtimeMessageText(message),
      toolName: message.role === "toolResult" ? (typeof message.toolName === "string" ? message.toolName : null) : null
    }));
}

function weekdayLabel(value: string): string {
  const labels: Record<string, string> = {
    monday: "Monday",
    tuesday: "Tuesday",
    wednesday: "Wednesday",
    thursday: "Thursday",
    friday: "Friday",
    saturday: "Saturday",
    sunday: "Sunday"
  };
  return labels[value] ?? "Monday";
}

export function OfferAgentCard({ aiEnabled, sources, watchlists }: OfferAgentCardProps) {
  const queryClient = useQueryClient();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<OfferAssistantMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeToolLabel, setActiveToolLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string | null>(() =>
    readStoredString(OFFERS_AGENT_MODEL_STORAGE_KEY)
  );
  const [selectedSourceId, setSelectedSourceId] = useState<string>("");
  const [merchantName, setMerchantName] = useState("");
  const [merchantUrl, setMerchantUrl] = useState("");
  const [selectedMerchantItem, setSelectedMerchantItem] = useState("");
  const [freeTextQuery, setFreeTextQuery] = useState("");
  const [minDiscount, setMinDiscount] = useState("");
  const [scheduleWeekday, setScheduleWeekday] = useState("monday");
  const [scheduleTime, setScheduleTime] = useState("20:00");

  const configQuery = useQuery({
    queryKey: ["ai-agent-config"],
    queryFn: fetchAIAgentConfig,
    enabled: aiEnabled
  });

  const merchantItemsQuery = useQuery({
    queryKey: ["offers", "merchant-items", merchantName],
    queryFn: () => fetchOfferMerchantItems({ merchantName, limit: 50 }),
    enabled: aiEnabled && merchantName.trim().length > 0
  });

  const modelOptions = useMemo(
    () => (configQuery.data ? enabledAgentModels(configQuery.data) : []),
    [configQuery.data]
  );
  const activeModelId = useMemo(() => {
    if (!configQuery.data) {
      return null;
    }
    return resolveAgentModelSelection(configQuery.data, selectedModelId);
  }, [configQuery.data, selectedModelId]);
  const activeModel = useMemo(
    () => modelOptions.find((option) => option.id === activeModelId) ?? null,
    [activeModelId, modelOptions]
  );

  const selectedSource = useMemo(
    () => sources.find((source) => source.source_id === selectedSourceId) ?? null,
    [selectedSourceId, sources]
  );

  const agent = useMemo(() => {
    if (!configQuery.data || !activeModelId) {
      return null;
    }
    return createSpendingAgent(
      configQuery.data.proxy_url,
      configQuery.data.auth_token,
      activeModelId,
      { pageContext: OFFER_PAGE_CONTEXT }
    );
  }, [activeModelId, configQuery.data]);

  useEffect(() => {
    if (!configQuery.data) {
      return;
    }
    const nextModelId = resolveAgentModelSelection(configQuery.data, selectedModelId);
    if (selectedModelId !== nextModelId) {
      setSelectedModelId(nextModelId);
      writeStoredString(OFFERS_AGENT_MODEL_STORAGE_KEY, nextModelId);
    }
  }, [configQuery.data, selectedModelId]);

  useEffect(() => {
    if (!selectedSource) {
      return;
    }
    setMerchantName(selectedSource.merchant_name);
    setMerchantUrl(selectedSource.merchant_url ?? "");
  }, [selectedSource]);

  useEffect(() => {
    if (!agent) {
      return;
    }
    setMessages(buildMessages(agent.state.messages as any[]));
    return agent.subscribe((event) => {
      if (event.type === "message_update") {
        if (event.assistantMessageEvent.type === "error") {
          setError(event.assistantMessageEvent.error.errorMessage || "Offer assistant failed.");
        }
        setMessages(buildMessages(agent.state.messages as any[]));
      }
      if (event.type === "tool_execution_start") {
        setActiveToolLabel(TOOL_LABELS[event.toolName] ?? event.toolName);
      }
      if (event.type === "tool_execution_end") {
        setActiveToolLabel(null);
        setMessages(buildMessages(agent.state.messages as any[]));
      }
      if (event.type === "agent_end") {
        setActiveToolLabel(null);
        setMessages(buildMessages(agent.state.messages as any[]));
      }
    });
  }, [agent]);

  async function runPrompt(prompt: string): Promise<void> {
    if (!prompt.trim() || !agent) {
      return;
    }
    setError(null);
    setIsStreaming(true);
    setActiveToolLabel(null);
    try {
      await agent.prompt(prompt);
      setInput("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["offers"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "overview"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "sources"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "watchlists"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "matches"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "alerts"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "refresh-runs"] }),
        queryClient.invalidateQueries({ queryKey: ["automation-rules"] })
      ]);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Offer assistant failed.");
    } finally {
      setIsStreaming(false);
      setActiveToolLabel(null);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await runPrompt(input.trim());
  }

  function buildSetupPrompt(): string {
    const merchantLabel = merchantName.trim() || selectedSource?.merchant_name || "this merchant";
    const url = merchantUrl.trim() || selectedSource?.merchant_url || "";
    const targetText = selectedMerchantItem || freeTextQuery.trim();
    const parts = [
      url
        ? `Create or reuse an offer source for ${merchantLabel} using ${url}.`
        : `Reuse the existing offer source for ${merchantLabel}.`,
      targetText ? `Create a watchlist for ${targetText}.` : "Create a merchant-level watchlist.",
      minDiscount.trim() ? `Only alert me if the discount is at least ${minDiscount.trim()}%.` : "",
      `Refresh offers every ${weekdayLabel(scheduleWeekday)} at ${scheduleTime}.`,
      selectedMerchantItem ? `Prefer the purchased item "${selectedMerchantItem}" from my receipt history.` : ""
    ];
    return parts.filter(Boolean).join(" ");
  }

  const sourceSummary =
    sources.length > 0
      ? sources.map((source) => `${source.display_name} (${source.source_id})`).join(", ")
      : "No offer sources yet.";
  const watchlistSummary =
    watchlists.length > 0
      ? watchlists
          .slice(0, 5)
          .map((watchlist) => watchlist.product_name ?? watchlist.query_text ?? "Untitled watchlist")
          .join(", ")
      : "No watchlists yet.";
  const merchantItems = merchantItemsQuery.data?.items ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ask Agent to Set Up Offers</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert variant={aiEnabled ? "default" : "destructive"}>
          <AlertTitle>Offer setup runs through the AI assistant</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>
              The frontend creates merchant offer sources from URLs, then the agent can create watchlists, trigger refreshes, and schedule recurring scans.
            </p>
            <p>
              There are no backend JSON feed files to edit. The app only scans merchant offer pages you add here.
            </p>
            {!aiEnabled ? (
              <p>
                AI access is not ready. Connect a model in <Link className="underline" to="/settings/ai">AI Settings</Link> to use this page.
              </p>
            ) : null}
          </AlertDescription>
        </Alert>

        <div className="space-y-1 text-xs text-muted-foreground">
          <p>Offer sources: {sourceSummary}</p>
          <p>Current watchlists: {watchlistSummary}</p>
        </div>

        {configQuery.error instanceof Error ? (
          <Alert variant="destructive">
            <AlertTitle>Offer assistant unavailable</AlertTitle>
            <AlertDescription>{configQuery.error.message}</AlertDescription>
          </Alert>
        ) : null}

        {error ? (
          <Alert variant="destructive">
            <AlertTitle>Offer assistant failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          {activeModel ? <Badge variant="outline">{activeModel.label}</Badge> : null}
          {activeToolLabel ? <Badge>{`Using ${activeToolLabel}`}</Badge> : null}
          {isStreaming ? <Badge variant="secondary">Working</Badge> : null}
        </div>

        {modelOptions.length > 0 ? (
          <label className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span>Model</span>
            <select
              aria-label="Offer agent model"
              className="app-soft-surface h-9 rounded-md border px-2 text-sm text-foreground"
              value={activeModelId ?? ""}
              onChange={(event) => {
                setSelectedModelId(event.target.value);
                writeStoredString(OFFERS_AGENT_MODEL_STORAGE_KEY, event.target.value);
              }}
              disabled={isStreaming}
            >
              {modelOptions.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <div className="app-section-divider grid gap-3 pt-4">
          <p className="text-sm font-medium">Setup helper</p>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Existing source</span>
            <select
              aria-label="Existing offer source"
              className="app-soft-surface h-10 rounded-md border px-3 text-sm text-foreground"
              value={selectedSourceId}
              onChange={(event) => setSelectedSourceId(event.target.value)}
              disabled={isStreaming}
            >
              <option value="">Create a new source</option>
              {sources.map((source) => (
                <option key={source.source_id} value={source.source_id}>
                  {source.display_name}
                </option>
              ))}
            </select>
          </label>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Merchant name</span>
              <Input
                value={merchantName}
                onChange={(event) => setMerchantName(event.target.value)}
                placeholder="Edeka"
                disabled={isStreaming}
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Offer page URL</span>
              <Input
                value={merchantUrl}
                onChange={(event) => setMerchantUrl(event.target.value)}
                placeholder="https://www.edeka.de/maerkte/402268/angebote/"
                disabled={isStreaming}
              />
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Purchased item from this merchant</span>
              <select
                aria-label="Purchased merchant item"
                className="app-soft-surface h-10 rounded-md border px-3 text-sm text-foreground"
                value={selectedMerchantItem}
                onChange={(event) => setSelectedMerchantItem(event.target.value)}
                disabled={isStreaming || merchantName.trim().length === 0}
              >
                <option value="">Choose an existing purchased item</option>
                {merchantItems.map((item) => (
                  <option key={`${item.product_id ?? item.item_name}-${item.last_purchased_at ?? "none"}`} value={item.label}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Free text watch target</span>
              <Input
                value={freeTextQuery}
                onChange={(event) => setFreeTextQuery(event.target.value)}
                placeholder="diapers, oat milk, coffee beans"
                disabled={isStreaming}
              />
            </label>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Minimum discount %</span>
              <Input
                value={minDiscount}
                onChange={(event) => setMinDiscount(event.target.value)}
                placeholder="20"
                inputMode="numeric"
                disabled={isStreaming}
              />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Weekday</span>
              <select
                aria-label="Offer schedule weekday"
                className="app-soft-surface h-10 rounded-md border px-3 text-sm text-foreground"
                value={scheduleWeekday}
                onChange={(event) => setScheduleWeekday(event.target.value)}
                disabled={isStreaming}
              >
                <option value="monday">Monday</option>
                <option value="tuesday">Tuesday</option>
                <option value="wednesday">Wednesday</option>
                <option value="thursday">Thursday</option>
                <option value="friday">Friday</option>
                <option value="saturday">Saturday</option>
                <option value="sunday">Sunday</option>
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-muted-foreground">Time</span>
              <Input
                value={scheduleTime}
                onChange={(event) => setScheduleTime(event.target.value)}
                type="time"
                disabled={isStreaming}
              />
            </label>
          </div>
          <div className="flex justify-end">
            <Button
              type="button"
              variant="outline"
              disabled={
                !aiEnabled ||
                !agent ||
                isStreaming ||
                merchantName.trim().length === 0 ||
                merchantUrl.trim().length === 0 ||
                (selectedMerchantItem.length === 0 && freeTextQuery.trim().length === 0)
              }
              onClick={() => void runPrompt(buildSetupPrompt())}
            >
              Send setup to agent
            </Button>
          </div>
        </div>

        <form className="space-y-3" onSubmit={(event) => void handleSubmit(event)}>
          <Textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Example: Add an offer source for https://www.edeka.de/maerkte/402268/angebote/ and watch for diapers every Monday at 20:00."
            rows={5}
            disabled={!aiEnabled || !agent || isStreaming}
          />
          <div className="flex flex-wrap gap-2">
            {PROMPT_SUGGESTIONS.map((suggestion) => (
              <Button
                key={suggestion}
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setInput(suggestion)}
                disabled={isStreaming || !aiEnabled}
              >
                {suggestion}
              </Button>
            ))}
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={!aiEnabled || !agent || isStreaming || input.trim().length === 0}>
              {isStreaming ? "Running agent..." : "Let agent handle it"}
            </Button>
          </div>
        </form>

        <div className="app-section-divider space-y-3 pt-4">
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Ask for a merchant URL, a product to watch, or a schedule such as “every Monday at 20:00”.
            </p>
          ) : null}
          {messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                "max-w-prose rounded-lg px-3 py-2 text-sm",
                message.role === "user"
                  ? "ml-auto bg-primary text-primary-foreground"
                  : message.role === "tool"
                    ? "app-soft-surface mr-auto border border-dashed"
                    : "mr-auto border border-border/70 bg-card"
              )}
            >
              {message.role === "tool" ? (
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">
                    {TOOL_LABELS[message.toolName ?? ""] ?? message.toolName ?? "tool"}
                  </p>
                  <pre className="whitespace-pre-wrap text-xs">{message.content || "No structured output."}</pre>
                </div>
              ) : (
                message.content
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
