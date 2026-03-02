import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const SystemBackupResultSchema = z.object({
  provider: z.string(),
  output_dir: z.string(),
  db_artifact: z.string(),
  token_artifact: z.string().nullable(),
  documents_artifact: z.string().nullable(),
  credential_key_artifact: z.string().nullable(),
  export_artifact: z.string().nullable(),
  export_records: z.number().nullable(),
  manifest_path: z.string(),
  copied: z.array(z.string()),
  skipped: z.array(z.string())
});

export type SystemBackupResult = z.infer<typeof SystemBackupResultSchema>;

export type SystemBackupRequest = {
  output_dir?: string;
  include_documents?: boolean;
  include_export_json?: boolean;
};

export async function runSystemBackup(payload: SystemBackupRequest): Promise<SystemBackupResult> {
  return apiClient.post("/api/v1/system/backup", SystemBackupResultSchema, payload);
}
