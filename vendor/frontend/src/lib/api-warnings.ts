type ApiWarningListener = (warning: string) => void;

const WARNING_TTL_MS = 15_000;
const warningListeners = new Set<ApiWarningListener>();
const warningCache = new Map<string, number>();

function pruneWarningCache(now: number): void {
  for (const [warning, seenAt] of warningCache.entries()) {
    if (now - seenAt > WARNING_TTL_MS) {
      warningCache.delete(warning);
    }
  }
}

export function emitApiWarnings(warnings: string[]): void {
  if (warnings.length === 0) {
    return;
  }

  const now = Date.now();
  pruneWarningCache(now);

  for (const rawWarning of warnings) {
    const warning = rawWarning.trim();
    if (!warning) {
      continue;
    }

    const seenAt = warningCache.get(warning);
    if (seenAt !== undefined && now - seenAt < WARNING_TTL_MS) {
      continue;
    }

    warningCache.set(warning, now);
    for (const listener of warningListeners) {
      listener(warning);
    }
  }
}

export function subscribeApiWarnings(listener: ApiWarningListener): () => void {
  warningListeners.add(listener);
  return () => {
    warningListeners.delete(listener);
  };
}
