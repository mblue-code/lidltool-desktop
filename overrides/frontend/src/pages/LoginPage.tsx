import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { checkSetupRequired, login } from "@/api/auth";
import { fetchCurrentUser } from "@/api/users";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { openDesktopControlCenter } from "@/lib/desktop-shell";

type SetupStatus = boolean | null;

function controlCenterLabel(locale: "en" | "de"): string {
  return locale === "de" ? "Kontrollzentrum öffnen" : "Open control center";
}

function controlCenterDescription(locale: "en" | "de"): string {
  return locale === "de"
    ? "Zurück zu lokalen Importen, Anbindungen und Backups, ohne sich erst anzumelden."
    : "Go back to local imports, connectors, and backups without signing in first.";
}

export function LoginPage() {
  const navigate = useNavigate();
  const { locale, t } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function resolveEntryState() {
      let setupRequired: SetupStatus = null;

      try {
        setupRequired = await checkSetupRequired();
      } catch {
        setupRequired = null;
      }

      if (cancelled) return;

      if (setupRequired === true) {
        navigate("/setup", { replace: true });
        return;
      }

      try {
        await fetchCurrentUser();
        if (!cancelled) {
          navigate("/", { replace: true });
        }
        return;
      } catch {
        if (!cancelled) {
          setChecking(false);
        }
      }
    }

    void resolveEntryState();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(resolveApiErrorMessage(err, t, t("auth.login.invalid")));
    } finally {
      setBusy(false);
    }
  }

  if (checking) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        {t("common.loading")}
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 px-4 dark:bg-transparent">
      <div className="app-soft-surface w-full max-w-sm space-y-6 rounded-[28px] border border-border/70 p-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">{t("auth.login.title")}</h1>
          <p className="text-sm text-muted-foreground">{t("auth.login.subtitle")}</p>
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
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
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
            {busy ? t("auth.login.submitting") : t("auth.login.submit")}
          </Button>
        </form>

        <div className="app-section-divider space-y-3">
          <p className="text-sm text-muted-foreground">{controlCenterDescription(locale)}</p>
          <Button type="button" variant="outline" className="w-full" onClick={() => void openDesktopControlCenter()}>
            {controlCenterLabel(locale)}
          </Button>
        </div>
      </div>
    </div>
  );
}
