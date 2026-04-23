import type { ConnectorSourceId, ExportRequest, SyncRequest } from "@shared/contracts";

export function buildSyncArgs(payload: SyncRequest, dbPath: string): string[] {
  const globalOptions: string[] = ["--db", dbPath, "--json", "connectors", "sync", "--source-id", payload.source];
  return [...globalOptions, ...buildConnectorSyncArgs(payload.source, payload)];
}

export function buildConnectorSyncArgs(source: ConnectorSourceId, payload: SyncRequest): string[] {
  const args: string[] = [];

  if (source.startsWith("lidl_plus_")) {
    if (payload.full) {
      args.push("--full");
    }
    return args;
  }

  const headless = payload.headless ?? true;
  args.push("--option", `headless=${headless ? "true" : "false"}`);

  if (payload.domain?.trim()) {
    args.push("--option", `domain=${payload.domain.trim()}`);
  }

  if (source.startsWith("amazon_")) {
    if (payload.years && payload.years > 0) {
      args.push("--option", `years=${String(payload.years)}`);
    }
    if (payload.maxPages && payload.maxPages > 0) {
      args.push("--option", `max_pages_per_year=${String(payload.maxPages)}`);
    }
    return args;
  }

  if (payload.maxPages && payload.maxPages > 0) {
    args.push("--option", `max_pages=${String(payload.maxPages)}`);
  }

  return args;
}

export function buildExportArgs(payload: ExportRequest, dbPath: string): string[] {
  const formatName = payload.format ?? "json";
  return ["--db", dbPath, "--json", "export", "--out", payload.outPath.trim(), "--format", formatName];
}
