export type RequestScope = "personal" | "family";

const STORAGE_KEY = "lidltool.request_scope.v1";
const DEFAULT_SCOPE: RequestScope = "personal";

let initialized = false;
let currentScope: RequestScope = DEFAULT_SCOPE;
const listeners = new Set<(scope: RequestScope) => void>();

function isRequestScope(value: string | null): value is RequestScope {
  return value === "personal" || value === "family";
}

function readStoredScope(): RequestScope {
  if (typeof window === "undefined" || typeof window.localStorage?.getItem !== "function") {
    return DEFAULT_SCOPE;
  }
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isRequestScope(stored) ? stored : DEFAULT_SCOPE;
  } catch {
    return DEFAULT_SCOPE;
  }
}

function writeStoredScope(scope: RequestScope): void {
  if (typeof window === "undefined" || typeof window.localStorage?.setItem !== "function") {
    return;
  }
  try {
    window.localStorage.setItem(STORAGE_KEY, scope);
  } catch {
    // Ignore storage write failures and keep in-memory state.
  }
}

function ensureInitialized(): void {
  if (initialized) {
    return;
  }
  currentScope = readStoredScope();
  initialized = true;
}

export function getRequestScope(): RequestScope {
  ensureInitialized();
  return currentScope;
}

export function getRequestScopeQueryParam(): RequestScope | undefined {
  const scope = getRequestScope();
  return scope === "family" ? scope : undefined;
}

export function setRequestScope(scope: RequestScope): void {
  ensureInitialized();
  if (currentScope === scope) {
    return;
  }
  currentScope = scope;
  writeStoredScope(scope);
  for (const listener of listeners) {
    listener(scope);
  }
}

export function subscribeRequestScope(listener: (scope: RequestScope) => void): () => void {
  ensureInitialized();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
