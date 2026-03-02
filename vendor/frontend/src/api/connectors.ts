import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const ConnectorBootstrapStatusSchema = z.object({
  source_id: z.string(),
  status: z.enum(["idle", "running", "succeeded", "failed"]),
  command: z.string().nullable(),
  pid: z.number().nullable(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  return_code: z.number().nullable(),
  output_tail: z.array(z.string()),
  can_cancel: z.boolean(),
  remote_login_url: z.string().nullable().optional()
});

const ConnectorBootstrapStartSchema = z.object({
  source_id: z.string(),
  reused: z.boolean(),
  bootstrap: ConnectorBootstrapStatusSchema,
  remote_login_url: z.string().nullable().optional()
});

const ConnectorBootstrapCancelSchema = z.object({
  source_id: z.string(),
  canceled: z.boolean(),
  bootstrap: ConnectorBootstrapStatusSchema.nullable()
});

const ConnectorSyncStatusSchema = z.object({
  source_id: z.string(),
  status: z.enum(["idle", "running", "succeeded", "failed"]),
  command: z.string().nullable(),
  pid: z.number().nullable(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  return_code: z.number().nullable(),
  output_tail: z.array(z.string()),
  can_cancel: z.boolean()
});

const ConnectorSyncStartSchema = z.object({
  source_id: z.string(),
  reused: z.boolean(),
  sync: ConnectorSyncStatusSchema
});

const ConnectorCascadeSourceSchema = z.object({
  source_id: z.string(),
  state: z.enum([
    "pending",
    "bootstrapping",
    "bootstrap_failed",
    "syncing",
    "sync_failed",
    "completed",
    "canceled",
    "skipped"
  ]),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  error: z.string().nullable(),
  bootstrap: ConnectorBootstrapStatusSchema.nullable(),
  sync: ConnectorSyncStatusSchema.nullable()
});

const ConnectorCascadeStatusSchema = z.object({
  status: z.enum(["idle", "running", "canceling", "completed", "partial_success", "failed", "canceled"]),
  source_ids: z.array(z.string()),
  full: z.boolean(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  current_source_id: z.string().nullable(),
  current_step: z.string().nullable(),
  can_cancel: z.boolean(),
  remote_login_url: z.string().nullable(),
  summary: z.object({
    total_sources: z.number(),
    completed: z.number(),
    failed: z.number(),
    canceled: z.number(),
    pending: z.number(),
    skipped: z.number()
  }),
  sources: z.array(ConnectorCascadeSourceSchema)
});

const ConnectorCascadeStartSchema = z.object({
  reused: z.boolean(),
  cascade: ConnectorCascadeStatusSchema
});

const ConnectorCascadeCancelSchema = z.object({
  canceled: z.boolean(),
  cascade: ConnectorCascadeStatusSchema
});

const ConnectorCascadeRetrySchema = z.object({
  reused: z.boolean(),
  cascade: ConnectorCascadeStatusSchema
});

export type ConnectorBootstrapStatus = z.infer<typeof ConnectorBootstrapStatusSchema>;
export type ConnectorBootstrapStartResult = z.infer<typeof ConnectorBootstrapStartSchema>;
export type ConnectorBootstrapCancelResult = z.infer<typeof ConnectorBootstrapCancelSchema>;
export type ConnectorSyncStatus = z.infer<typeof ConnectorSyncStatusSchema>;
export type ConnectorSyncStartResult = z.infer<typeof ConnectorSyncStartSchema>;
export type ConnectorCascadeStatus = z.infer<typeof ConnectorCascadeStatusSchema>;
export type ConnectorCascadeStartResult = z.infer<typeof ConnectorCascadeStartSchema>;
export type ConnectorCascadeCancelResult = z.infer<typeof ConnectorCascadeCancelSchema>;
export type ConnectorCascadeRetryResult = z.infer<typeof ConnectorCascadeRetrySchema>;

export async function startConnectorBootstrap(sourceId: string): Promise<ConnectorBootstrapStartResult> {
  return apiClient.post(`/api/v1/connectors/${sourceId}/bootstrap/start`, ConnectorBootstrapStartSchema);
}

export async function fetchConnectorBootstrapStatus(sourceId: string): Promise<ConnectorBootstrapStatus> {
  return apiClient.get(
    `/api/v1/connectors/${sourceId}/bootstrap/status`,
    ConnectorBootstrapStatusSchema
  );
}

export async function cancelConnectorBootstrap(sourceId: string): Promise<ConnectorBootstrapCancelResult> {
  return apiClient.post(`/api/v1/connectors/${sourceId}/bootstrap/cancel`, ConnectorBootstrapCancelSchema);
}

export async function startConnectorSync(sourceId: string, full = false): Promise<ConnectorSyncStartResult> {
  const path = full
    ? `/api/v1/connectors/${sourceId}/sync?full=true`
    : `/api/v1/connectors/${sourceId}/sync`;
  return apiClient.post(path, ConnectorSyncStartSchema);
}

export async function fetchConnectorSyncStatus(sourceId: string): Promise<ConnectorSyncStatus> {
  return apiClient.get(`/api/v1/connectors/${sourceId}/sync/status`, ConnectorSyncStatusSchema);
}

export async function startConnectorCascade(
  sourceIds: string[],
  full = false
): Promise<ConnectorCascadeStartResult> {
  return apiClient.post("/api/v1/connectors/cascade/start", ConnectorCascadeStartSchema, {
    source_ids: sourceIds,
    full
  });
}

export async function fetchConnectorCascadeStatus(): Promise<ConnectorCascadeStatus> {
  return apiClient.get("/api/v1/connectors/cascade/status", ConnectorCascadeStatusSchema);
}

export async function cancelConnectorCascade(): Promise<ConnectorCascadeCancelResult> {
  return apiClient.post("/api/v1/connectors/cascade/cancel", ConnectorCascadeCancelSchema);
}

export async function retryConnectorCascade(
  full?: boolean,
  includeSkipped = true
): Promise<ConnectorCascadeRetryResult> {
  return apiClient.post("/api/v1/connectors/cascade/retry", ConnectorCascadeRetrySchema, {
    full,
    include_skipped: includeSkipped
  });
}
