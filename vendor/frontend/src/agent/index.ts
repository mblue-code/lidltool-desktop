import { Agent, streamProxy } from "@mariozechner/pi-agent-core";

import { ALL_TOOLS } from "@/agent/tools";

type SpendingAgentOptions = {
  pageContext?: string | null;
};

function buildSystemPrompt(pageContext?: string | null): string {
  const normalizedPageContext = pageContext?.trim() ?? "";
  const pageContextSection = normalizedPageContext
    ? `\n\nUI page context (side panel only):\n${normalizedPageContext}`
    : "";

  return `You are a personal grocery and household spending analyst with access to the user's complete shopping history across all retailers (Lidl, Rewe, Kaufland, Amazon, dm, Rossmann, and others).

You can search receipts, analyse spending trends, compare prices, find products, and help the user understand their shopping habits. Always respond in the same language the user writes in. Be specific - always use real numbers from the data rather than vague estimates. Today's date: ${
    new Date().toISOString().split("T")[0]
  }.

Visualization rules:
- When the answer benefits from charts, tables, or cards, call the render_ui tool.
- render_ui only accepts a strict spec object with version "v1" and a component catalog. Do not invent component names.
- Always include a short text interpretation in plain language after tool usage.

Financial calculation rules:
- VAT rates are always expressed as VAT ÷ net (not VAT ÷ gross). For example, a 7% VAT rate means €7 on €100 net (€107 gross). To compute the effective VAT rate: effective_rate = total_vat / (total_gross - total_vat).
- line_total_cents in the database is the final amount paid by the customer — discounts are already applied. Never subtract discount amounts from line_total_cents again.${pageContextSection}`;
}

export function createSpendingAgent(
  proxyUrl: string,
  authToken: string,
  modelId?: string,
  options?: SpendingAgentOptions
): Agent {
  const resolvedModel = modelId || "gpt-5.2-codex";
  const model = {
    id: resolvedModel,
    name: resolvedModel,
    provider: "openai",
    api: "openai-completions",
    baseUrl: proxyUrl
  } as any;

  const agent = new Agent({
    initialState: {
      systemPrompt: buildSystemPrompt(options?.pageContext),
      model
    },
    streamFn: (model, context, options) =>
      streamProxy(model, context, { ...options, authToken, proxyUrl })
  });
  agent.setTools(ALL_TOOLS);
  return agent;
}
