export type RequestScope = "personal" | "group";

export type ActiveWorkspace =
  | { kind: "personal" }
  | { kind: "shared-group"; groupId: string };

const WORKSPACE_STORAGE_KEY = "outlays.workspace.v1";
const LEGACY_WORKSPACE_STORAGE_KEY = "lidltool.workspace.v1";
const DEFAULT_WORKSPACE: ActiveWorkspace = { kind: "personal" };

let initialized = false;
let currentWorkspace: ActiveWorkspace = DEFAULT_WORKSPACE;
const listeners = new Set<(workspace: ActiveWorkspace) => void>();

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isActiveWorkspace(value: unknown): value is ActiveWorkspace {
  if (!isObject(value) || typeof value.kind !== "string") {
    return false;
  }
  if (value.kind === "personal") {
    return true;
  }
  return value.kind === "shared-group" && typeof value.groupId === "string" && value.groupId.trim().length > 0;
}

function isRequestScope(value: string | null): value is RequestScope {
  return value === "personal" || value === "group";
}

function normalizeWorkspace(value: ActiveWorkspace): ActiveWorkspace {
  if (value.kind === "personal") {
    return DEFAULT_WORKSPACE;
  }
  return {
    kind: "shared-group",
    groupId: value.groupId.trim()
  };
}

function readStoredWorkspace(): ActiveWorkspace {
  if (typeof window === "undefined" || typeof window.localStorage?.getItem !== "function") {
    return DEFAULT_WORKSPACE;
  }
  try {
    const stored =
      window.localStorage.getItem(WORKSPACE_STORAGE_KEY) ??
      window.localStorage.getItem(LEGACY_WORKSPACE_STORAGE_KEY);
    if (!stored) {
      return DEFAULT_WORKSPACE;
    }
    const parsed: unknown = JSON.parse(stored);
    return isActiveWorkspace(parsed) ? normalizeWorkspace(parsed) : DEFAULT_WORKSPACE;
  } catch {
    return DEFAULT_WORKSPACE;
  }
}

function writeStoredWorkspace(workspace: ActiveWorkspace): void {
  if (typeof window === "undefined" || typeof window.localStorage?.setItem !== "function") {
    return;
  }
  try {
    window.localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify(workspace));
    window.localStorage.removeItem(LEGACY_WORKSPACE_STORAGE_KEY);
  } catch {
    // Ignore storage write failures and keep in-memory state.
  }
}

function ensureInitialized(): void {
  if (initialized) {
    return;
  }
  currentWorkspace = readStoredWorkspace();
  initialized = true;
}

function workspaceEquals(left: ActiveWorkspace, right: ActiveWorkspace): boolean {
  if (left.kind !== right.kind) {
    return false;
  }
  if (left.kind === "personal") {
    return true;
  }
  return right.kind === "shared-group" && left.groupId === right.groupId;
}

export function getActiveWorkspace(): ActiveWorkspace {
  ensureInitialized();
  return currentWorkspace;
}

export function getRequestScope(): RequestScope {
  return getActiveWorkspace().kind === "personal" ? "personal" : "group";
}

export function getRequestScopeQueryParam(): string | undefined {
  const workspace = getActiveWorkspace();
  if (workspace.kind === "personal") {
    return undefined;
  }
  return `group:${workspace.groupId}`;
}

export function setActiveWorkspace(workspace: ActiveWorkspace): void {
  ensureInitialized();
  const normalized = normalizeWorkspace(workspace);
  if (workspaceEquals(currentWorkspace, normalized)) {
    return;
  }
  currentWorkspace = normalized;
  writeStoredWorkspace(normalized);
  for (const listener of listeners) {
    listener(normalized);
  }
}

export function setRequestScope(scope: RequestScope, groupId?: string): void {
  if (scope === "personal") {
    setActiveWorkspace(DEFAULT_WORKSPACE);
    return;
  }
  if (!groupId || !groupId.trim()) {
    throw new Error("group scope requires a concrete groupId");
  }
  setActiveWorkspace({ kind: "shared-group", groupId: groupId.trim() });
}

export function subscribeActiveWorkspace(listener: (workspace: ActiveWorkspace) => void): () => void {
  ensureInitialized();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function subscribeRequestScope(listener: (scope: RequestScope) => void): () => void {
  return subscribeActiveWorkspace((workspace) => {
    listener(workspace.kind === "personal" ? "personal" : "group");
  });
}
