const SUPPORTED_DESKTOP_OCR_PROVIDERS = new Set([
  "glm_ocr_local",
  "openai_compatible",
  "external_api"
]);

export function normalizeDesktopOcrProvider(value: string | null | undefined): string {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (SUPPORTED_DESKTOP_OCR_PROVIDERS.has(normalized)) {
    return normalized;
  }
  return "glm_ocr_local";
}

export function buildBackendServeArgs(dbPath: string, port: number): string[] {
  return [
    "--db",
    dbPath,
    "serve",
    "--host",
    "127.0.0.1",
    "--port",
    String(port)
  ];
}
