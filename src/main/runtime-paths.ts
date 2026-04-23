import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

import type {
  ConnectorCatalogEntry,
  DesktopReleaseMetadata,
  DesktopRuntimeDiagnostics
} from "@shared/contracts";

export interface RuntimePathContext {
  appPath: string;
  resourcesPath: string;
  isPackaged: boolean;
  homeDir: string;
  platform: NodeJS.Platform;
}

export interface BackendInvocation {
  command: string;
  argsPrefix: string[];
}

export function resolveUserPath(value: string, homeDir: string): string {
  if (value === "~") {
    return homeDir;
  }
  if (value.startsWith("~/") || value.startsWith("~\\")) {
    return resolve(homeDir, value.slice(2));
  }
  return resolve(value);
}

export function resolveDesktopConfigDir(userDataDir: string): string {
  return join(userDataDir, "config");
}

export function resolveConfigDirPath(
  userDataDir: string,
  env: NodeJS.ProcessEnv,
  homeDir: string
): string {
  const configDirRaw = env.LIDLTOOL_CONFIG_DIR?.trim();
  if (configDirRaw) {
    return resolveUserPath(configDirRaw, homeDir);
  }
  return resolveDesktopConfigDir(userDataDir);
}

export function resolveConfigFilePath(
  userDataDir: string,
  env: NodeJS.ProcessEnv,
  homeDir: string
): string {
  return join(resolveConfigDirPath(userDataDir, env, homeDir), "config.toml");
}

export function resolveTokenFilePath(
  userDataDir: string,
  env: NodeJS.ProcessEnv,
  homeDir: string
): string {
  return join(resolveConfigDirPath(userDataDir, env, homeDir), "token.json");
}

export function resolveDocumentsPath(
  userDataDir: string,
  env: NodeJS.ProcessEnv,
  homeDir: string
): string {
  const documentsPathRaw = env.LIDLTOOL_DOCUMENT_STORAGE_PATH?.trim();
  if (documentsPathRaw) {
    return resolveUserPath(documentsPathRaw, homeDir);
  }
  return join(userDataDir, "documents");
}

export function resolveRepoRootHint(context: RuntimePathContext, env: NodeJS.ProcessEnv): string {
  const override = env.LIDLTOOL_REPO_ROOT?.trim();
  if (override) {
    return override;
  }

  if (context.isPackaged) {
    return join(context.resourcesPath, "backend-src");
  }

  return resolve(context.appPath, "vendor", "backend");
}

export function resolveFrontendDist(context: RuntimePathContext, env: NodeJS.ProcessEnv): string {
  const override = env.LIDLTOOL_FRONTEND_DIST?.trim();
  if (override) {
    return override;
  }

  if (context.isPackaged) {
    return join(context.resourcesPath, "frontend-dist");
  }

  return resolve(context.appPath, "vendor", "frontend", "dist");
}

export function resolveRemoteCatalogUrl(env: NodeJS.ProcessEnv): string | null {
  const raw = env.LIDLTOOL_DESKTOP_CATALOG_URL?.trim();
  return raw ? raw : null;
}

export function readJsonOverrideFromPath(
  env: NodeJS.ProcessEnv,
  envName: string,
  label: string
): unknown | undefined {
  const overridePath = env[envName]?.trim();
  if (!overridePath) {
    return undefined;
  }
  try {
    return JSON.parse(readFileSync(overridePath, "utf-8"));
  } catch (error) {
    throw new Error(`${label} could not be loaded from ${overridePath}. ${String(error)}`);
  }
}

export function resolveTrustRootsOverride(env: NodeJS.ProcessEnv): unknown | undefined {
  return readJsonOverrideFromPath(env, "LIDLTOOL_DESKTOP_TRUST_ROOTS_PATH", "Desktop trust roots override");
}

export function resolveTrustedCatalogOverride(env: NodeJS.ProcessEnv): unknown | undefined {
  return readJsonOverrideFromPath(
    env,
    "LIDLTOOL_DESKTOP_TRUSTED_CATALOG_PATH",
    "Desktop trusted catalog override"
  );
}

export function findCatalogDesktopPackEntry(
  entries: DesktopReleaseMetadata["discovery_catalog"]["entries"],
  entryId: string
): ConnectorCatalogEntry {
  const entry = entries.find((candidate) => candidate.entry_id === entryId);
  if (!entry || entry.entry_type !== "desktop_pack") {
    throw new Error(`Trusted desktop pack catalog entry was not found: ${entryId}`);
  }
  if (entry.availability.blocked_by_policy) {
    throw new Error(entry.availability.block_reason ?? `Catalog entry ${entryId} is blocked.`);
  }
  if (entry.install_methods.includes("download_url") === false || !entry.download_url) {
    throw new Error(`Catalog entry ${entryId} does not support trusted URL install.`);
  }
  return entry;
}

export function isPathLike(command: string): boolean {
  return command.startsWith(".") || command.startsWith("/") || command.includes("\\") || command.includes("/");
}

export function resolveBundledExecutable(context: RuntimePathContext): string | null {
  if (!context.isPackaged) {
    return null;
  }

  const candidate =
    context.platform === "win32"
      ? join(context.resourcesPath, "backend-venv", "Scripts", "lidltool.exe")
      : join(context.resourcesPath, "backend-venv", "bin", "lidltool");

  return existsSync(candidate) ? candidate : null;
}

export function resolveManagedDevExecutable(context: RuntimePathContext): string | null {
  if (context.isPackaged) {
    return null;
  }

  const candidate =
    context.platform === "win32"
      ? join(context.appPath, ".backend", "venv", "Scripts", "lidltool.exe")
      : join(context.appPath, ".backend", "venv", "bin", "lidltool");

  return existsSync(candidate) ? candidate : null;
}

export function resolvePythonExecutable(context: RuntimePathContext): string {
  if (context.isPackaged) {
    const bundled =
      context.platform === "win32"
        ? join(context.resourcesPath, "backend-venv", "Scripts", "python.exe")
        : join(context.resourcesPath, "backend-venv", "bin", "python");
    if (existsSync(bundled)) {
      return bundled;
    }
  }

  const managedDev =
    context.platform === "win32"
      ? join(context.appPath, ".backend", "venv", "Scripts", "python.exe")
      : join(context.appPath, ".backend", "venv", "bin", "python");
  if (existsSync(managedDev)) {
    return managedDev;
  }

  return context.platform === "win32" ? "python" : "python3";
}

export function inspectBackendCommand(
  context: RuntimePathContext,
  env: NodeJS.ProcessEnv
): {
  command: string;
  source: DesktopRuntimeDiagnostics["backendCommandSource"];
  status: DesktopRuntimeDiagnostics["backendCommandStatus"];
} {
  const override = env.LIDLTOOL_EXECUTABLE?.trim();
  if (override) {
    if (isPathLike(override)) {
      return {
        command: override,
        source: "env_override",
        status: existsSync(override) ? "ready" : "missing"
      };
    }
    return {
      command: override,
      source: "env_override",
      status: "lookup"
    };
  }

  if (context.isPackaged) {
    const bundledPython = resolvePythonExecutable(context);
    if (isPathLike(bundledPython) && existsSync(bundledPython)) {
      return {
        command: `${bundledPython} -m lidltool.cli`,
        source: "bundled",
        status: "ready"
      };
    }
  }

  const bundledExecutable = resolveBundledExecutable(context);
  if (bundledExecutable) {
    return {
      command: bundledExecutable,
      source: "bundled",
      status: "ready"
    };
  }

  const managedDevExecutable = resolveManagedDevExecutable(context);
  if (managedDevExecutable) {
    return {
      command: managedDevExecutable,
      source: "managed_dev",
      status: "ready"
    };
  }

  return {
    command: context.platform === "win32" ? "lidltool.exe" : "lidltool",
    source: "path_lookup",
    status: "lookup"
  };
}

export function resolveBackendInvocation(
  context: RuntimePathContext,
  env: NodeJS.ProcessEnv,
  strictOverride: boolean
): BackendInvocation {
  const override = env.LIDLTOOL_EXECUTABLE?.trim();
  if (override) {
    if (strictOverride || !isPathLike(override) || existsSync(override)) {
      return { command: override, argsPrefix: [] };
    }
  }

  if (context.isPackaged) {
    const bundledPython = resolvePythonExecutable(context);
    if (isPathLike(bundledPython) && existsSync(bundledPython)) {
      return {
        command: bundledPython,
        argsPrefix: ["-m", "lidltool.cli"]
      };
    }
  }

  const bundledExecutable = resolveBundledExecutable(context);
  if (bundledExecutable) {
    return { command: bundledExecutable, argsPrefix: [] };
  }

  const managedDevExecutable = resolveManagedDevExecutable(context);
  if (managedDevExecutable) {
    return { command: managedDevExecutable, argsPrefix: [] };
  }

  return {
    command: context.platform === "win32" ? "lidltool.exe" : "lidltool",
    argsPrefix: []
  };
}

export function resolveOcrIdleTimeoutSeconds(env: NodeJS.ProcessEnv): number {
  const raw = env.LIDLTOOL_DESKTOP_OCR_IDLE_TIMEOUT_S?.trim();
  if (!raw) {
    return 600;
  }
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed) || parsed < 60) {
    return 600;
  }
  return parsed;
}
