import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { setup } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";

type DesktopImportResult = {
  ok: boolean;
  command: string;
  args: string[];
  exitCode: number | null;
  stdout: string;
  stderr: string;
};

type DesktopApiBridge = {
  runImport: (payload: {
    backupDir: string;
    includeDocuments?: boolean;
    includeToken?: boolean;
    includeCredentialKey?: boolean;
    restartBackend?: boolean;
  }) => Promise<DesktopImportResult>;
} | null;

function getDesktopApiBridge(): DesktopApiBridge {
  const desktopApi = (window as unknown as { desktopApi?: DesktopApiBridge }).desktopApi;
  if (!desktopApi || typeof desktopApi.runImport !== "function") {
    return null;
  }
  return desktopApi;
}

export function SetupPage() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const desktopApi = getDesktopApiBridge();
  const [restoreDir, setRestoreDir] = useState("");
  const [restoreBusy, setRestoreBusy] = useState(false);
  const [restoreStatus, setRestoreStatus] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!username.trim()) {
      setError(t("auth.setup.usernameRequired"));
      return;
    }
    if (password.length < 8) {
      setError(t("auth.setup.passwordTooShort"));
      return;
    }
    if (password !== confirm) {
      setError(t("auth.setup.passwordMismatch"));
      return;
    }

    setBusy(true);
    try {
      await setup(username.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(resolveApiErrorMessage(err, t, t("auth.setup.failed")));
    } finally {
      setBusy(false);
    }
  }

  async function handleRestoreBackup(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!desktopApi) {
      setRestoreStatus(t("auth.setup.restoreUnavailable"));
      return;
    }
    if (!restoreDir.trim()) {
      setRestoreStatus(t("auth.setup.restoreRequired"));
      return;
    }

    setRestoreBusy(true);
    setRestoreStatus(null);
    try {
      await desktopApi.runImport({
        backupDir: restoreDir.trim(),
        includeCredentialKey: true,
        includeDocuments: true,
        includeToken: true,
        restartBackend: true
      });
      setRestoreStatus(t("auth.setup.restoreSuccess"));
      navigate("/login", { replace: true });
    } catch (err) {
      setRestoreStatus(err instanceof Error ? err.message : t("auth.setup.restoreFailed"));
    } finally {
      setRestoreBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 px-4 dark:bg-transparent">
      <div className="app-soft-surface w-full max-w-md space-y-6 rounded-[28px] border border-border/70 p-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">{t("auth.setup.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("auth.setup.subtitle")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="username">{t("auth.login.username")}</Label>
            <Input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password">{t("auth.login.password")}</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="confirm">{t("auth.setup.confirmPassword")}</Label>
            <Input
              id="confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}

          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? t("auth.setup.submitting") : t("auth.setup.submit")}
          </Button>
        </form>

        <div className="app-soft-surface rounded-md border border-border/60 p-4">
          <p className="mb-2 text-sm font-medium">{t("auth.setup.restoreTitle")}</p>
          <p className="mb-3 text-sm text-muted-foreground">{t("auth.setup.restoreDescription")}</p>
          <form className="space-y-3" onSubmit={(event) => void handleRestoreBackup(event)}>
            <div className="space-y-1.5">
              <Label htmlFor="restore-dir">{t("auth.setup.restoreDirectory")}</Label>
              <Input
                id="restore-dir"
                value={restoreDir}
                onChange={(event) => setRestoreDir(event.target.value)}
                placeholder={t("auth.setup.restorePlaceholder")}
                disabled={restoreBusy || !desktopApi}
              />
            </div>
            {restoreStatus ? (
              <p role="status" className="text-xs text-muted-foreground">
                {restoreStatus}
              </p>
            ) : null}
            <Button type="submit" className="w-full" disabled={restoreBusy || !desktopApi}>
              {restoreBusy ? t("auth.setup.restoreSubmitting") : t("auth.setup.restoreSubmit")}
            </Button>
          </form>
          {!desktopApi ? (
            <p className="mt-2 text-xs text-muted-foreground">{t("auth.setup.restoreUnavailable")}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
