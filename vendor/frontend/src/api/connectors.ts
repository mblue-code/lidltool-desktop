import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const ConnectorActionSchema = z.object({
  kind: z.string().nullable(),
  href: z.string().nullable().optional(),
  enabled: z.boolean()
});

const ConnectorOperatorActionsSchema = z.object({
  full_sync: z.boolean(),
  rescan: z.boolean(),
  reload: z.boolean().optional().default(false),
  install: z.boolean().optional().default(false),
  enable: z.boolean().optional().default(false),
  disable: z.boolean().optional().default(false),
  uninstall: z.boolean().optional().default(false),
  configure: z.boolean().optional().default(false),
  manual_commands: z.record(z.string(), z.string())
});

const ConnectorUiSchema = z.object({
  status: z.enum([
    "setup_required",
    "connected",
    "syncing",
    "ready",
    "needs_attention",
    "error",
    "preview"
  ]),
  visibility: z.enum(["default", "operator_only"]).optional().default("default"),
  description: z.string(),
  actions: z.object({
    primary: ConnectorActionSchema,
    secondary: ConnectorActionSchema,
    operator: ConnectorOperatorActionsSchema
  })
});

const ConnectorDiscoveryRowSchema = z.object({
  source_id: z.string(),
  plugin_id: z.string().nullable(),
  display_name: z.string(),
  origin: z.enum(["builtin", "local_path", "marketplace", "catalog"]),
  origin_label: z.string(),
  runtime_kind: z.string().nullable(),
  install_origin: z.enum(["builtin", "local_path", "marketplace", "catalog"]).nullable().optional(),
  install_state: z.enum(["catalog_only", "discovered", "installed"]),
  enable_state: z.enum(["enabled", "disabled", "blocked", "invalid", "incompatible"]),
  config_state: z.enum(["not_required", "required", "incomplete", "complete"]),
  maturity: z.enum(["verified", "working", "preview", "stub"]),
  maturity_label: z.string(),
  supports_bootstrap: z.boolean(),
  supports_sync: z.boolean(),
  supports_live_session: z.boolean(),
  supports_live_session_bootstrap: z.boolean(),
  trust_class: z.string().nullable(),
  status_detail: z.string().nullable(),
  last_sync_summary: z.string().nullable(),
  last_synced_at: z.string().nullable(),
  ui: ConnectorUiSchema,
  actions: z.object({
    primary: ConnectorActionSchema,
    secondary: ConnectorActionSchema,
    operator: ConnectorOperatorActionsSchema
  }),
  advanced: z.object({
    source_exists: z.boolean(),
    stale: z.boolean().optional().default(false),
    stale_reason: z.string().nullable().optional(),
    auth_state: z.string(),
    latest_sync_output: z.array(z.string()),
    latest_bootstrap_output: z.array(z.string()),
    latest_sync_status: z.string(),
    latest_bootstrap_status: z.string(),
    block_reason: z
      .object({
        code: z.string().nullable().optional(),
        label: z.string().nullable().optional(),
        summary: z.string().nullable().optional(),
        detail: z.string().nullable().optional()
      })
      .nullable(),
    policy: z
      .object({
        blocked: z.boolean(),
        block_reason: z
          .object({
            code: z.string().nullable().optional(),
            label: z.string().nullable().optional(),
            summary: z.string().nullable().optional(),
            detail: z.string().nullable().optional()
          })
          .nullable(),
        status: z.string().nullable(),
        status_detail: z.string().nullable(),
        trust_class: z.string().nullable().optional(),
        external_runtime_enabled: z.boolean().nullable().optional(),
        external_receipt_plugins_enabled: z.boolean().nullable().optional(),
        allowed_trust_classes: z.array(z.string()).optional().default([])
      })
      .optional(),
    release: z.object({
      maturity: z.enum(["verified", "working", "preview", "stub"]),
      label: z.string(),
      support_posture: z.string(),
      description: z.string(),
      default_visibility: z.enum(["default", "operator_only"]),
      graduation_requirements: z.array(z.string())
    }),
    origin: z.object({
      kind: z.string(),
      runtime_kind: z.string().nullable(),
      search_path: z.string().nullable(),
      origin_path: z.string().nullable(),
      origin_directory: z.string().nullable()
    }),
    diagnostics: z.array(z.string()),
    manual_commands: z.record(z.string(), z.string())
  })
});

const ConnectorsDiscoverySchema = z.object({
  generated_at: z.string(),
  viewer: z.object({
    is_admin: z.boolean()
  }),
  operator_actions: z.object({
    can_reload: z.boolean().optional().default(false),
    can_rescan: z.boolean()
  }),
  summary: z.object({
    total_connectors: z.number(),
    by_status: z.record(z.string(), z.number())
  }),
  connectors: z.array(ConnectorDiscoveryRowSchema)
});

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

const ConnectorLifecycleActionResultSchema = z.object({
  source_id: z.string(),
  plugin_id: z.string().nullable(),
  display_name: z.string(),
  install_origin: z.enum(["builtin", "local_path", "marketplace", "catalog"]).nullable().optional(),
  install_state: z.enum(["catalog_only", "discovered", "installed"]),
  enable_state: z.enum(["enabled", "disabled", "blocked", "invalid", "incompatible"]),
  config_state: z.enum(["not_required", "required", "incomplete", "complete"]),
  stale: z.boolean().optional().default(false),
  stale_reason: z.string().nullable().optional(),
  config_preserved: z.boolean().optional()
});

const ConnectorConfigFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  description: z.string().nullable().optional(),
  input_kind: z.enum(["text", "password", "url", "number", "boolean"]),
  required: z.boolean(),
  sensitive: z.boolean(),
  operator_only: z.boolean(),
  placeholder: z.string().nullable().optional(),
  value: z.union([z.string(), z.number(), z.boolean(), z.null()]).optional(),
  has_value: z.boolean().optional()
});

const ConnectorConfigSchema = z.object({
  source_id: z.string(),
  plugin_id: z.string(),
  display_name: z.string(),
  install_origin: z.enum(["builtin", "local_path", "marketplace", "catalog"]).nullable().optional(),
  config_state: z.enum(["not_required", "required", "incomplete", "complete"]),
  fields: z.array(ConnectorConfigFieldSchema)
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
export type ConnectorLifecycleActionResult = z.infer<typeof ConnectorLifecycleActionResultSchema>;
export type ConnectorConfigField = z.infer<typeof ConnectorConfigFieldSchema>;
export type ConnectorConfig = z.infer<typeof ConnectorConfigSchema>;
export type ConnectorCascadeStatus = z.infer<typeof ConnectorCascadeStatusSchema>;
export type ConnectorCascadeStartResult = z.infer<typeof ConnectorCascadeStartSchema>;
export type ConnectorCascadeCancelResult = z.infer<typeof ConnectorCascadeCancelSchema>;
export type ConnectorCascadeRetryResult = z.infer<typeof ConnectorCascadeRetrySchema>;
export type ConnectorsDiscovery = z.infer<typeof ConnectorsDiscoverySchema>;
export type ConnectorDiscoveryRow = z.infer<typeof ConnectorDiscoveryRowSchema>;
export type ConnectorAction = z.infer<typeof ConnectorActionSchema>;

export async function fetchConnectors(): Promise<ConnectorsDiscovery> {
  return apiClient.get("/api/v1/connectors", ConnectorsDiscoverySchema);
}

export async function rescanConnectors(): Promise<ConnectorsDiscovery> {
  return apiClient.post("/api/v1/connectors/rescan", ConnectorsDiscoverySchema);
}

export async function reloadConnectors(): Promise<ConnectorsDiscovery> {
  return apiClient.post("/api/v1/connectors/reload", ConnectorsDiscoverySchema);
}

export async function installConnector(sourceId: string): Promise<ConnectorLifecycleActionResult> {
  return apiClient.post(`/api/v1/connectors/${sourceId}/install`, ConnectorLifecycleActionResultSchema);
}

export async function enableConnector(sourceId: string): Promise<ConnectorLifecycleActionResult> {
  return apiClient.post(`/api/v1/connectors/${sourceId}/enable`, ConnectorLifecycleActionResultSchema);
}

export async function disableConnector(sourceId: string): Promise<ConnectorLifecycleActionResult> {
  return apiClient.post(`/api/v1/connectors/${sourceId}/disable`, ConnectorLifecycleActionResultSchema);
}

export async function uninstallConnector(
  sourceId: string,
  purgeConfig = false
): Promise<ConnectorLifecycleActionResult> {
  return apiClient.post(`/api/v1/connectors/${sourceId}/uninstall`, ConnectorLifecycleActionResultSchema, {
    purge_config: purgeConfig
  });
}

export async function fetchConnectorConfig(sourceId: string): Promise<ConnectorConfig> {
  return apiClient.get(`/api/v1/connectors/${sourceId}/config`, ConnectorConfigSchema);
}

export async function submitConnectorConfig(
  sourceId: string,
  payload: {
    values: Record<string, string | number | boolean | null>;
    clear_secret_keys?: string[];
  }
): Promise<ConnectorConfig> {
  return apiClient.post(`/api/v1/connectors/${sourceId}/config`, ConnectorConfigSchema, payload);
}

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
