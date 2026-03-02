import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const AutomationRuleSchema = z.object({
  id: z.string(),
  name: z.string(),
  rule_type: z.string(),
  enabled: z.boolean(),
  trigger_config: z.record(z.string(), z.unknown()),
  action_config: z.record(z.string(), z.unknown()),
  next_run_at: z.string().nullable(),
  last_run_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string()
});

const AutomationRuleListResponseSchema = z.object({
  count: z.number(),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  items: z.array(AutomationRuleSchema)
});

const AutomationExecutionSchema = z.object({
  id: z.string(),
  rule_id: z.string(),
  rule_name: z.string().nullable(),
  rule_type: z.string().nullable(),
  status: z.string(),
  triggered_at: z.string(),
  executed_at: z.string().nullable(),
  result: z.record(z.string(), z.unknown()).nullable(),
  error: z.string().nullable(),
  created_at: z.string()
});

const AutomationExecutionListResponseSchema = z.object({
  count: z.number(),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  items: z.array(AutomationExecutionSchema)
});

const DeleteAutomationRuleSchema = z.object({
  deleted: z.boolean(),
  id: z.string(),
  name: z.string()
});

export type AutomationRule = z.infer<typeof AutomationRuleSchema>;
export type AutomationRuleListResponse = z.infer<typeof AutomationRuleListResponseSchema>;
export type AutomationExecution = z.infer<typeof AutomationExecutionSchema>;
export type AutomationExecutionListResponse = z.infer<typeof AutomationExecutionListResponseSchema>;

export type CreateAutomationRuleRequest = {
  name: string;
  rule_type: string;
  enabled?: boolean;
  trigger_config: Record<string, unknown>;
  action_config: Record<string, unknown>;
  actor_id?: string;
};

export type UpdateAutomationRuleRequest = Partial<CreateAutomationRuleRequest>;

export async function fetchAutomationRules(limit = 100, offset = 0): Promise<AutomationRuleListResponse> {
  return apiClient.get("/api/v1/automations", AutomationRuleListResponseSchema, {
      limit: String(limit),
      offset: String(offset)
    });
}

export async function createAutomationRule(payload: CreateAutomationRuleRequest): Promise<AutomationRule> {
  return apiClient.post("/api/v1/automations", AutomationRuleSchema, payload);
}

export async function updateAutomationRule(
  ruleId: string,
  payload: UpdateAutomationRuleRequest
): Promise<AutomationRule> {
  return apiClient.patch(`/api/v1/automations/${ruleId}`, AutomationRuleSchema, payload);
}

export async function deleteAutomationRule(ruleId: string): Promise<{ deleted: boolean; id: string; name: string }> {
  return apiClient.delete(`/api/v1/automations/${ruleId}`, DeleteAutomationRuleSchema);
}

export async function runAutomationRule(
  ruleId: string,
  actorId?: string
): Promise<AutomationExecution> {
  return apiClient.post(`/api/v1/automations/${ruleId}/run`, AutomationExecutionSchema, {
    actor_id: actorId
  });
}

export async function fetchAutomationExecutions(filters?: {
  status?: string;
  ruleType?: string;
  limit?: number;
  offset?: number;
}): Promise<AutomationExecutionListResponse> {
  return apiClient.get("/api/v1/automations/executions", AutomationExecutionListResponseSchema, {
      status: filters?.status,
      rule_type: filters?.ruleType,
      limit: String(filters?.limit ?? 100),
      offset: String(filters?.offset ?? 0)
    });
}
