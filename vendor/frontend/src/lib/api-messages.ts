export type ApiWarning = {
  code: string | null;
  message: string;
};

export function warningCacheKey(warning: ApiWarning): string {
  return `${warning.code ?? ""}::${warning.message}`;
}

export function normalizeApiWarnings(
  warnings: string[],
  warningDetails: Array<{ code?: string | null; message: string }> = []
): ApiWarning[] {
  const normalized: ApiWarning[] = [];
  const seen = new Set<string>();

  for (const detail of warningDetails) {
    const message = detail.message.trim();
    if (!message) {
      continue;
    }
    const warning = {
      code: detail.code ?? null,
      message
    };
    const key = warningCacheKey(warning);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    normalized.push(warning);
  }

  for (const rawWarning of warnings) {
    const message = rawWarning.trim();
    if (!message) {
      continue;
    }
    const warning = { code: null, message };
    const key = warningCacheKey(warning);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    normalized.push(warning);
  }

  return normalized;
}
