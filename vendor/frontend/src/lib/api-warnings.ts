import { warningCacheKey, type ApiWarning } from "@/lib/api-messages";

type ApiWarningListener = (warning: ApiWarning) => void;

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

export function emitApiWarnings(warnings: ApiWarning[]): void {
  if (warnings.length === 0) {
    return;
  }

  const now = Date.now();
  pruneWarningCache(now);

  for (const rawWarning of warnings) {
    const warning = {
      code: rawWarning.code ?? null,
      message: rawWarning.message.trim()
    };
    if (!warning.message) {
      continue;
    }

    const cacheKey = warningCacheKey(warning);
    const seenAt = warningCache.get(cacheKey);
    if (seenAt !== undefined && now - seenAt < WARNING_TTL_MS) {
      continue;
    }

    warningCache.set(cacheKey, now);
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
