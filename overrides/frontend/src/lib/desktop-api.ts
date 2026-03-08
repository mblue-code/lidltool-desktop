export type DesktopImportResult = {
  ok: boolean;
  command: string;
  args: string[];
  exitCode: number | null;
  stdout: string;
  stderr: string;
};

export type DesktopApiBridge = {
  runImport: (payload: {
    backupDir: string;
    includeDocuments?: boolean;
    includeToken?: boolean;
    includeCredentialKey?: boolean;
    restartBackend?: boolean;
  }) => Promise<DesktopImportResult>;
} | null;

export function getDesktopApiBridge(): DesktopApiBridge {
  const desktopApi = (window as unknown as { desktopApi?: DesktopApiBridge }).desktopApi;
  if (!desktopApi || typeof desktopApi.runImport !== "function") {
    return null;
  }
  return desktopApi;
}
