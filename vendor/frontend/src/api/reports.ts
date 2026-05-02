import { z } from "zod";

import { apiClient } from "@/lib/api-client";

export type ReportSankeyMode = "combined" | "outflow_only";
export type ReportSankeyBreakdown = "merchant" | "subcategory_only" | "subcategory" | "subcategory_source" | "source";
export type ReportScopeOverride = "personal" | `group:${string}`;

const ReportTemplateSchema = z.object({
  slug: z.string(),
  title: z.string(),
  description: z.string(),
  format: z.string(),
  payload: z.unknown()
});

const ReportTemplatesSchema = z.object({
  period: z.object({
    from_date: z.string(),
    to_date: z.string()
  }),
  count: z.number(),
  templates: z.array(ReportTemplateSchema)
});

const ReportPatternsSchema = z.object({
  period: z.object({ from_date: z.string(), to_date: z.string() }),
  value_mode: z.string(),
  daily_heatmap: z.array(z.object({ date: z.string(), amount_cents: z.number(), count: z.number() })),
  weekday_heatmap: z.array(z.object({ weekday: z.number(), amount_cents: z.number(), count: z.number() })),
  weekday_hour_matrix: z.array(z.object({ weekday: z.number(), hour: z.number(), amount_cents: z.number(), count: z.number() })),
  merchant_profiles: z.array(z.object({ merchant: z.string(), amount_cents: z.number(), count: z.number(), average_cents: z.number() })),
  merchant_comparison: z.array(z.object({ merchant: z.string(), amount_cents: z.number(), count: z.number(), average_cents: z.number() })),
  insights: z.array(z.record(z.string(), z.unknown()))
});

const ReportSankeyResponseSchema = z.object({
  period: z.object({ from_date: z.string(), to_date: z.string() }),
  mode: z.enum(["combined", "outflow_only"]),
  breakdown: z.enum(["merchant", "subcategory_only", "subcategory", "subcategory_source", "source"]),
  model: z.object({
    kind: z.string(),
    transaction_provenance_supported: z.boolean()
  }),
  flags: z.object({
    aggregated_inflows: z.boolean(),
    aggregated_categories: z.boolean(),
    aggregated_merchants: z.boolean(),
    aggregated_subcategories: z.boolean(),
    aggregated_sources: z.boolean(),
    manual_inflows_excluded_by_source_filter: z.boolean(),
    synthetic_inflow_bucket: z.boolean()
  }),
  summary: z.object({
    total_outflow_cents: z.number(),
    total_inflow_basis_cents: z.number(),
    node_count: z.number(),
    link_count: z.number()
  }),
  nodes: z.array(z.object({
    id: z.string(),
    label: z.string(),
    kind: z.string(),
    layer: z.number(),
    amount_cents: z.number(),
    basis_amount_cents: z.number().optional(),
    category_id: z.string().nullable().optional(),
    merchant_name: z.string().nullable().optional(),
    source_id: z.string().nullable().optional()
  })),
  links: z.array(z.object({
    source: z.string(),
    target: z.string(),
    value_cents: z.number(),
    kind: z.string()
  }))
});

export type ReportTemplate = z.infer<typeof ReportTemplateSchema>;
export type ReportTemplatesResponse = z.infer<typeof ReportTemplatesSchema>;
export type ReportPatternsResponse = z.infer<typeof ReportPatternsSchema>;
export type ReportSankeyResponse = z.infer<typeof ReportSankeyResponseSchema>;

function workspaceCompareModelKind(breakdown: ReportSankeyBreakdown): string {
  if (breakdown === "subcategory_only") {
    return "workspace_compare_outflow_category_to_subcategory";
  }
  if (breakdown === "subcategory") {
    return "workspace_compare_outflow_category_to_subcategory_merchant";
  }
  if (breakdown === "subcategory_source") {
    return "workspace_compare_outflow_category_to_subcategory_source";
  }
  if (breakdown === "source") {
    return "workspace_compare_outflow_category_to_source";
  }
  return "workspace_compare_outflow_category_to_merchant";
}

export function buildWorkspaceComparisonSankey(args: {
  breakdown: ReportSankeyBreakdown;
  group: ReportSankeyResponse;
  groupLabel: string;
  personal: ReportSankeyResponse;
  personalLabel?: string;
}): ReportSankeyResponse {
  const { breakdown, group, groupLabel, personal, personalLabel = "Personal" } = args;
  const responses = [personal, group];
  const [fromDate, toDate] = [personal.period.from_date, personal.period.to_date];
  if (
    responses.some((entry) => (
      entry.mode !== "outflow_only"
      || entry.breakdown !== breakdown
      || entry.period.from_date !== fromDate
      || entry.period.to_date !== toDate
    ))
  ) {
    throw new Error("workspace comparison sankey requires matching outflow-only sankey payloads");
  }

  const workspaceNodes: ReportSankeyResponse["nodes"] = [
    {
      id: "workspace:personal",
      label: personalLabel,
      kind: "workspace",
      layer: 0,
      amount_cents: personal.summary.total_outflow_cents,
      basis_amount_cents: 0,
    },
    {
      id: "workspace:shared_group",
      label: groupLabel,
      kind: "workspace",
      layer: 0,
      amount_cents: group.summary.total_outflow_cents,
      basis_amount_cents: 0,
    },
  ];
  const nodeMap = new Map<string, ReportSankeyResponse["nodes"][number]>();
  const linkMap = new Map<string, ReportSankeyResponse["links"][number]>();

  const mergeNode = (node: ReportSankeyResponse["nodes"][number]) => {
    const existing = nodeMap.get(node.id);
    if (!existing) {
      nodeMap.set(node.id, {
        ...node,
        layer: node.layer + 1,
        basis_amount_cents: node.basis_amount_cents ?? 0,
      });
      return;
    }
    existing.amount_cents += node.amount_cents;
    existing.basis_amount_cents = (existing.basis_amount_cents ?? 0) + (node.basis_amount_cents ?? 0);
  };

  const mergeLink = (link: ReportSankeyResponse["links"][number]) => {
    const key = `${link.source}->${link.target}`;
    const existing = linkMap.get(key);
    if (!existing) {
      linkMap.set(key, { ...link });
      return;
    }
    existing.value_cents += link.value_cents;
  };

  const attachWorkspace = (
    workspaceId: "workspace:personal" | "workspace:shared_group",
    payload: ReportSankeyResponse,
  ) => {
    for (const node of payload.nodes) {
      if (node.kind === "inflow") {
        continue;
      }
      mergeNode(node);
      if (node.kind === "outflow_category") {
        mergeLink({
          source: workspaceId,
          target: node.id,
          value_cents: node.amount_cents,
          kind: "workspace_to_category",
        });
      }
    }
    for (const link of payload.links) {
      if (link.source.startsWith("inflow:")) {
        continue;
      }
      mergeLink(link);
    }
  };

  attachWorkspace("workspace:personal", personal);
  attachWorkspace("workspace:shared_group", group);

  const nodes = [...workspaceNodes, ...nodeMap.values()].sort((left, right) => (
    left.layer - right.layer
    || right.amount_cents - left.amount_cents
    || left.id.localeCompare(right.id)
  ));
  const links = [...linkMap.values()].sort((left, right) => (
    left.source.localeCompare(right.source)
    || left.target.localeCompare(right.target)
  ));

  return {
    period: { from_date: fromDate, to_date: toDate },
    mode: "outflow_only",
    breakdown,
    model: {
      kind: workspaceCompareModelKind(breakdown),
      transaction_provenance_supported: false,
    },
    flags: {
      aggregated_inflows: false,
      aggregated_categories: personal.flags.aggregated_categories || group.flags.aggregated_categories,
      aggregated_merchants: personal.flags.aggregated_merchants || group.flags.aggregated_merchants,
      aggregated_subcategories: personal.flags.aggregated_subcategories || group.flags.aggregated_subcategories,
      aggregated_sources: personal.flags.aggregated_sources || group.flags.aggregated_sources,
      manual_inflows_excluded_by_source_filter: personal.flags.manual_inflows_excluded_by_source_filter || group.flags.manual_inflows_excluded_by_source_filter,
      synthetic_inflow_bucket: false,
    },
    summary: {
      total_outflow_cents: personal.summary.total_outflow_cents + group.summary.total_outflow_cents,
      total_inflow_basis_cents: 0,
      node_count: nodes.length,
      link_count: links.length,
    },
    nodes,
    links,
  };
}

export async function fetchReportTemplates(
  fromDate: string,
  toDate: string
): Promise<ReportTemplatesResponse> {
  return apiClient.get("/api/v1/reports/templates", ReportTemplatesSchema, {
    from_date: fromDate,
    to_date: toDate
  });
}

export async function fetchReportPatterns(filters: {
  fromDate: string;
  toDate: string;
  merchants?: string[];
  financeCategoryId?: string;
  direction?: string;
  sourceId?: string;
  sourceIds?: string[];
  valueMode?: string;
}): Promise<ReportPatternsResponse> {
  return apiClient.get("/api/v1/reports/patterns", ReportPatternsSchema, {
    from_date: filters.fromDate,
    to_date: filters.toDate,
    merchants: filters.merchants && filters.merchants.length > 0 ? filters.merchants.join(",") : undefined,
    finance_category_id: filters.financeCategoryId,
    direction: filters.direction,
    source_id: filters.sourceId,
    source_ids: filters.sourceIds && filters.sourceIds.length > 0 ? filters.sourceIds.join(",") : undefined,
    value_mode: filters.valueMode
  });
}

export async function fetchReportSankey(filters: {
  fromDate: string;
  toDate: string;
  merchants?: string[];
  financeCategoryId?: string;
  direction?: string;
  mode?: ReportSankeyMode;
  breakdown?: ReportSankeyBreakdown;
  sourceId?: string;
  sourceIds?: string[];
  scopeOverride?: ReportScopeOverride;
  topN?: number;
}): Promise<ReportSankeyResponse> {
  return apiClient.get("/api/v1/reports/sankey", ReportSankeyResponseSchema, {
    from_date: filters.fromDate,
    to_date: filters.toDate,
    merchants: filters.merchants && filters.merchants.length > 0 ? filters.merchants.join(",") : undefined,
    finance_category_id: filters.financeCategoryId,
    direction: filters.direction,
    mode: filters.mode,
    breakdown: filters.breakdown,
    source_id: filters.sourceId,
    source_ids: filters.sourceIds && filters.sourceIds.length > 0 ? filters.sourceIds.join(",") : undefined,
    top_n: filters.topN
  }, filters.scopeOverride);
}
