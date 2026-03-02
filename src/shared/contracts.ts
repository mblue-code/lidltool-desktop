export type SyncSourceId = "lidl" | "amazon" | "rewe" | "kaufland" | "dm" | "rossmann";

export type ConnectorSourceId = Exclude<SyncSourceId, "lidl">;

export interface BackendConfig {
  apiBaseUrl: string;
  dbPath: string;
  userDataDir: string;
}

export interface BackendStatus {
  running: boolean;
  pid: number | null;
  startedAt: string | null;
  command: string;
}

export interface CommandResult {
  ok: boolean;
  command: string;
  args: string[];
  exitCode: number | null;
  stdout: string;
  stderr: string;
}

export interface SyncRequest {
  source: SyncSourceId;
  full?: boolean;
  headless?: boolean;
  years?: number;
  maxPages?: number;
  domain?: string;
}

export interface CommandLogEvent {
  timestamp: string;
  stream: "stdout" | "stderr";
  line: string;
  source: "backend" | "sync";
}
