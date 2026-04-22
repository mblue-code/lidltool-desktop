import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const GoalProgressSchema = z.object({
  window_from: z.string(),
  window_to: z.string(),
  current_amount_cents: z.number(),
  target_amount_cents: z.number(),
  remaining_amount_cents: z.number(),
  progress_ratio: z.number(),
  status: z.string(),
  unit_label: z.string()
});

const GoalSchema = z.object({
  id: z.string(),
  user_id: z.string(),
  name: z.string(),
  goal_type: z.string(),
  target_amount_cents: z.number(),
  currency: z.string(),
  period: z.string(),
  category: z.string().nullable(),
  merchant_name: z.string().nullable(),
  recurring_bill_id: z.string().nullable(),
  target_date: z.string().nullable(),
  notes: z.string().nullable(),
  active: z.boolean(),
  completed_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  progress: GoalProgressSchema.optional()
});

const GoalListSchema = z.object({
  count: z.number(),
  items: z.array(GoalSchema)
});

const GoalsSummarySchema = z.object({
  count: z.number(),
  completed_count: z.number(),
  at_risk_count: z.number(),
  items: z.array(GoalSchema)
});

const DeletedGoalSchema = z.object({
  deleted: z.boolean(),
  id: z.string()
});

export type Goal = z.infer<typeof GoalSchema>;
export type GoalList = z.infer<typeof GoalListSchema>;
export type GoalsSummary = z.infer<typeof GoalsSummarySchema>;

export async function fetchGoals(fromDate: string, toDate: string, includeInactive = false): Promise<GoalList> {
  return apiClient.get("/api/v1/goals", GoalListSchema, {
    from_date: fromDate,
    to_date: toDate,
    include_inactive: includeInactive ? "true" : undefined
  });
}

export async function fetchGoalsSummary(fromDate: string, toDate: string): Promise<GoalsSummary> {
  return apiClient.get("/api/v1/goals/summary", GoalsSummarySchema, {
    from_date: fromDate,
    to_date: toDate
  });
}

export async function createGoal(payload: {
  name: string;
  goal_type: string;
  target_amount_cents: number;
  currency?: string;
  period?: string;
  category?: string | null;
  merchant_name?: string | null;
  recurring_bill_id?: string | null;
  target_date?: string | null;
  notes?: string | null;
}): Promise<Goal> {
  return apiClient.post("/api/v1/goals", GoalSchema, payload);
}

export async function updateGoal(
  goalId: string,
  payload: Partial<{
    name: string;
    goal_type: string;
    target_amount_cents: number;
    currency: string;
    period: string;
    category: string | null;
    merchant_name: string | null;
    recurring_bill_id: string | null;
    target_date: string | null;
    notes: string | null;
    active: boolean;
  }>
): Promise<Goal> {
  return apiClient.patch(`/api/v1/goals/${goalId}`, GoalSchema, payload);
}

export async function deleteGoal(goalId: string): Promise<z.infer<typeof DeletedGoalSchema>> {
  return apiClient.delete(`/api/v1/goals/${goalId}`, DeletedGoalSchema);
}
