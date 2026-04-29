const TOKEN_ASSIGNMENT_PATTERN =
  /\b(access_token|refresh_token|id_token|token|session|sessionid|cookie|authorization|password|credential|secret|api[_-]?key)\b\s*[:=]\s*("[^"]+"|'[^']+'|[^\s,;]+)/gi;
const BEARER_PATTERN = /\bBearer\s+[A-Za-z0-9._~+/=-]+/gi;
const BASIC_PATTERN = /\bBasic\s+[A-Za-z0-9._~+/=-]+/gi;
const LONG_SECRET_PATTERN = /\b[A-Za-z0-9_-]{32,}\b/g;
const URL_QUERY_PATTERN = /([?&])([^=\s&]+)=([^&\s]+)/g;

export function redactSensitiveText(value: string, homeDir?: string | null): string {
  let next = value;
  if (homeDir) {
    next = next.split(homeDir).join("<home>");
  }
  return next
    .replace(TOKEN_ASSIGNMENT_PATTERN, (_match, key) => `${key}=<redacted>`)
    .replace(BEARER_PATTERN, "Bearer <redacted>")
    .replace(BASIC_PATTERN, "Basic <redacted>")
    .replace(URL_QUERY_PATTERN, (_match, separator, key) => `${separator}${key}=<redacted>`)
    .replace(LONG_SECRET_PATTERN, "<redacted>");
}

export function sanitizeDiagnosticValue(value: unknown, homeDir?: string | null): unknown {
  if (typeof value === "string") {
    return redactSensitiveText(value, homeDir);
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeDiagnosticValue(item, homeDir));
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  const redacted: Record<string, unknown> = {};
  for (const [key, nested] of Object.entries(value)) {
    if (/token|secret|credential|cookie|password|authorization|session/i.test(key)) {
      redacted[key] = "<redacted>";
    } else {
      redacted[key] = sanitizeDiagnosticValue(nested, homeDir);
    }
  }
  return redacted;
}

