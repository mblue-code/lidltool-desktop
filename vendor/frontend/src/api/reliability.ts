import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const SloThresholdsSchema = z.object({
  sync_p95_target_ms: z.number(),
  analytics_p95_target_ms: z.number(),
  min_success_rate: z.number()
});

const SloEndpointSchema = z.object({
  route: z.string(),
  count: z.number(),
  success_rate: z.number(),
  error_rate: z.number(),
  p50_duration_ms: z.number().nullable(),
  p95_duration_ms: z.number().nullable(),
  p99_duration_ms: z.number().nullable()
});

const SloFamilySchema = z.object({
  routes: z.number(),
  p95_duration_ms: z.number().nullable(),
  avg_success_rate: z.number(),
  p95_target_ms: z.number(),
  slo_pass: z.boolean()
});

const ReliabilitySloResponseSchema = z.object({
  generated_at: z.string(),
  window_hours: z.number(),
  thresholds: SloThresholdsSchema,
  endpoints: z.array(SloEndpointSchema),
  families: z.record(z.string(), SloFamilySchema)
});

export type ReliabilitySloResponse = z.infer<typeof ReliabilitySloResponseSchema>;
export type ReliabilitySloEndpoint = z.infer<typeof SloEndpointSchema>;
export type ReliabilitySloFamily = z.infer<typeof SloFamilySchema>;

export type ReliabilitySloFilters = {
  windowHours?: number;
  syncP95TargetMs?: number;
  analyticsP95TargetMs?: number;
  minSuccessRate?: number;
};

export async function fetchReliabilitySlo(filters?: ReliabilitySloFilters): Promise<ReliabilitySloResponse> {
  return apiClient.get("/api/v1/reliability/slo", ReliabilitySloResponseSchema, {
    window_hours: filters?.windowHours,
    sync_p95_target_ms: filters?.syncP95TargetMs,
    analytics_p95_target_ms: filters?.analyticsP95TargetMs,
    min_success_rate: filters?.minSuccessRate
  });
}
