import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { setup } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getDesktopApiBridge } from "@/lib/desktop-api";

export function SetupPage() {
  const navigate = useNavigate();
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
      setError("Username is required.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setBusy(true);
    try {
      await setup(username.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Setup failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRestoreBackup(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!desktopApi) {
      setRestoreStatus("Desktop restore is only available in the desktop app runtime.");
      return;
    }
    if (!restoreDir.trim()) {
      setRestoreStatus("Backup directory is required.");
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
      setRestoreStatus("Backup restored. Continue with Sign in.");
      navigate("/login", { replace: true });
    } catch (err) {
      setRestoreStatus(err instanceof Error ? err.message : "Restore failed.");
    } finally {
      setRestoreBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Welcome to Lidl Receipts</h1>
          <p className="text-sm text-muted-foreground">Create your admin account to get started.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="username">Username</Label>
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
            <Label htmlFor="password">Password</Label>
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
            <Label htmlFor="confirm">Confirm password</Label>
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
            {busy ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <div className="rounded-md border border-border/60 p-4">
          <p className="mb-2 text-sm font-medium">Restore From Backup</p>
          <form className="space-y-3" onSubmit={(event) => void handleRestoreBackup(event)}>
            <div className="space-y-1.5">
              <Label htmlFor="restore-dir">Backup directory</Label>
              <Input
                id="restore-dir"
                value={restoreDir}
                onChange={(event) => setRestoreDir(event.target.value)}
                placeholder="/path/to/backup-folder"
                disabled={restoreBusy || !desktopApi}
              />
            </div>
            {restoreStatus ? (
              <p role="status" className="text-xs text-muted-foreground">
                {restoreStatus}
              </p>
            ) : null}
            <Button type="submit" className="w-full" disabled={restoreBusy || !desktopApi}>
              {restoreBusy ? "Restoring…" : "Restore backup and sign in"}
            </Button>
          </form>
          {!desktopApi ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Restore is available in the packaged desktop app.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
