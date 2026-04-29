import { Bot, Copy, Database, PaintBucket, QrCode, RefreshCw, ShieldCheck, Smartphone, StopCircle, Users } from "lucide-react";
import * as QRCode from "qrcode";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { z } from "zod";

import { PageHeader } from "@/components/shared/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useI18n } from "@/i18n";
import { apiClient } from "@/lib/api-client";
import { getDesktopMobileBridge, type DesktopMobileBridgeStatus } from "@/lib/desktop-api";

const mobilePairingPayloadSchema = z.object({
  protocol_version: z.number(),
  desktop_id: z.string(),
  desktop_name: z.string(),
  endpoint_url: z.string(),
  pairing_token: z.string(),
  public_key_fingerprint: z.string(),
  expires_at: z.string(),
  transport: z.string(),
  listener_expires_at: z.string()
});

const mobilePairingSessionSchema = z.object({
  session_id: z.string(),
  status: z.string(),
  payload: mobilePairingPayloadSchema,
  qr_payload: mobilePairingPayloadSchema,
  expires_at: z.string(),
  listener_expires_at: z.string()
});

type MobilePairingSession = z.infer<typeof mobilePairingSessionSchema>;

async function createMobilePairingSession(endpointUrl: string): Promise<MobilePairingSession> {
  return apiClient.post("/api/mobile-pair/v1/sessions", mobilePairingSessionSchema, {
    bridge_endpoint_url: endpointUrl,
    endpoint_url: endpointUrl,
    expires_in_seconds: 600,
    transport: "lan_http"
  });
}

function formatCountdown(expiresAt: string | null): string {
  if (!expiresAt) {
    return "Not open";
  }
  const remainingSeconds = Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 1000));
  const minutes = Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function SettingsPage() {
  const { locale, t } = useI18n();
  const [mobileSession, setMobileSession] = useState<MobilePairingSession | null>(null);
  const [mobileBridgeStatus, setMobileBridgeStatus] = useState<DesktopMobileBridgeStatus | null>(null);
  const [mobilePairingBusy, setMobilePairingBusy] = useState(false);
  const [mobilePairingError, setMobilePairingError] = useState<string | null>(null);
  const [mobileRiskDialogOpen, setMobileRiskDialogOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const mobileBridge = useMemo(() => getDesktopMobileBridge(), []);
  const mobilePairingText = useMemo(
    () => (mobileSession ? JSON.stringify(mobileSession.qr_payload, null, 2) : ""),
    [mobileSession]
  );
  const mobileCountdown = formatCountdown(mobileBridgeStatus?.expiresAt ?? mobileSession?.listener_expires_at ?? null);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!mobileBridge) {
      return;
    }
    const bridge = mobileBridge;
    let active = true;
    async function refreshBridgeStatus(): Promise<void> {
      try {
        const status = await bridge.getMobileBridgeStatus();
        if (active) {
          setMobileBridgeStatus(status);
        }
      } catch {
        if (active) {
          setMobileBridgeStatus(null);
        }
      }
    }
    void refreshBridgeStatus();
    const timer = window.setInterval(() => void refreshBridgeStatus(), 3_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [mobileBridge]);

  useEffect(() => {
    if (!mobileBridgeStatus?.running && mobileSession) {
      setMobileSession(null);
    }
  }, [mobileBridgeStatus?.running, mobileSession]);
  const sections = [
    {
      title: locale === "de" ? "Anbindungsverwaltung" : "Connector management",
      description:
        locale === "de"
          ? "Pakete installieren, den Händler-Authentifizierungsstatus prüfen und Einmal-Synchronisierungen verwalten."
          : "Install packs, check retailer auth state, and manage one-off sync surfaces.",
      to: "/connectors",
      icon: Database
    },
    {
      title: locale === "de" ? "KI-Assistent" : "AI assistant",
      description:
        locale === "de"
          ? "Anbietereinstellungen und das desktop-sichere Assistentenverhalten anpassen."
          : "Adjust provider settings and desktop-safe assistant behavior.",
      to: "/settings/ai",
      icon: Bot
    },
    {
      title: locale === "de" ? "Benutzer und Zugriff" : "Users and access",
      description:
        locale === "de"
          ? "Desktop-lokale Benutzer und Sitzungsgrenzen prüfen."
          : "Review desktop-local users and session boundaries.",
      to: "/settings/users",
      icon: Users
    },
    {
      title: locale === "de" ? "Mobile Kopplung" : "Mobile pairing",
      description:
        locale === "de"
          ? "Ein iPhone oder Android-Telefon lokal mit diesem Desktop koppeln."
          : "Pair an iPhone or Android phone locally with this desktop.",
      to: "#mobile-pairing",
      icon: Smartphone
    },
    {
      title: locale === "de" ? "Darstellung" : "Appearance",
      description:
        locale === "de"
          ? "Design-Presets, Farben, Typografie und Dichte der Desktop-Shell lokal anpassen."
          : "Adjust desktop shell presets, colors, typography, and density locally.",
      to: "/settings/appearance",
      icon: PaintBucket
    },
    {
      title: locale === "de" ? "Desktop-Konfiguration" : "Desktop posture",
      description:
        locale === "de"
          ? "Die Paket-App lokal-first halten und mit dem Kontrollzentrum abstimmen."
          : "Keep the packaged app local-first and aligned with the control center model.",
      to: "/setup",
      icon: ShieldCheck
    }
  ] as const;

  async function handleCreateMobilePairingSession(): Promise<void> {
    if (!mobileBridge) {
      setMobilePairingError("Local phone pairing is only available inside Outlays.");
      return;
    }
    setMobilePairingBusy(true);
    setMobilePairingError(null);
    try {
      const bridgeStatus = await mobileBridge.startMobileBridge({ expiresInSeconds: 600 });
      setMobileBridgeStatus(bridgeStatus);
      if (!bridgeStatus.endpointUrl) {
        throw new Error("Mobile bridge did not return a LAN endpoint.");
      }
      setMobileSession(await createMobilePairingSession(bridgeStatus.endpointUrl));
      setMobileRiskDialogOpen(false);
    } catch (error) {
      setMobilePairingError(error instanceof Error ? error.message : String(error));
    } finally {
      setMobilePairingBusy(false);
    }
  }

  async function handleStopMobileBridge(): Promise<void> {
    if (!mobileBridge) {
      return;
    }
    setMobilePairingBusy(true);
    setMobilePairingError(null);
    try {
      const status = await mobileBridge.stopMobileBridge();
      setMobileBridgeStatus(status);
      setMobileSession(null);
    } catch (error) {
      setMobilePairingError(error instanceof Error ? error.message : String(error));
    } finally {
      setMobilePairingBusy(false);
    }
  }

  async function handleCopyMobilePayload(): Promise<void> {
    if (!mobilePairingText) {
      return;
    }
    await navigator.clipboard?.writeText(mobilePairingText);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("nav.item.settings")}
        description={
          locale === "de"
            ? "Verwaltungsfunktionen bleiben von der Haupt-Finanzansicht getrennt, während jede desktopspezifische Oberfläche mit einem Klick erreichbar bleibt."
            : "Keep operational controls off the main finance rail while leaving every desktop-specific surface one click away."
        }
      />

      <div className="grid gap-4 xl:grid-cols-2">
        {sections.map((section) => (
          <Card key={section.title} className="app-dashboard-surface border-border/60">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <section.icon className="h-4 w-4" />
                {section.title}
              </CardTitle>
              <CardDescription>{section.description}</CardDescription>
            </CardHeader>
            <CardContent>
              {section.to.startsWith("#") ? (
                <Button variant="outline" asChild>
                  <a href={section.to}>{t("common.open")}</a>
                </Button>
              ) : (
                <Button asChild variant="outline">
                  <Link to={section.to}>{t("common.open")}</Link>
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <section id="mobile-pairing" className="space-y-4">
        <Card className="app-dashboard-surface border-border/60">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <QrCode className="h-4 w-4" />
              {locale === "de" ? "Telefon koppeln" : "Pair mobile"}
            </CardTitle>
            <CardDescription>
              {locale === "de"
                ? "Erzeugen Sie einen kurzlebigen lokalen Kopplungs-Payload und scannen oder kopieren Sie ihn in der nativen Companion-App."
                : "Create a short-lived local pairing payload, then scan or copy it into the native companion app."}
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 lg:grid-cols-[280px_1fr]">
            <div className="space-y-3">
              <PairingMatrix value={mobilePairingText} />
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => setMobileRiskDialogOpen(true)} disabled={mobilePairingBusy}>
                  <RefreshCw className="mr-2 h-4 w-4" />
                  {mobilePairingBusy
                    ? locale === "de"
                      ? "Wird erzeugt..."
                      : "Creating..."
                    : locale === "de"
                      ? "Lokale Telefonkopplung aktivieren"
                      : "Enable local phone pairing"}
                </Button>
                <Button variant="outline" onClick={handleCopyMobilePayload} disabled={!mobilePairingText}>
                  <Copy className="mr-2 h-4 w-4" />
                  {locale === "de" ? "Kopieren" : "Copy"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => void handleStopMobileBridge()}
                  disabled={!mobileBridgeStatus?.running || mobilePairingBusy}
                >
                  <StopCircle className="mr-2 h-4 w-4" />
                  {locale === "de" ? "Freigabe stoppen" : "Stop sharing"}
                </Button>
              </div>
            </div>
            <div className="space-y-3">
              <Alert>
                <ShieldCheck className="h-4 w-4" />
                <AlertTitle>
                  {mobileBridgeStatus?.running
                    ? locale === "de"
                      ? "Lokales Kopplungsfenster geöffnet"
                      : "Local pairing window open"
                    : locale === "de"
                      ? "Standardmäßig nur lokal"
                      : "Localhost-only by default"}
                </AlertTitle>
                <AlertDescription>
                  {mobileBridgeStatus?.running
                    ? locale === "de"
                      ? "Nur mobile Endpunkte sind über die temporäre lokale Netzwerkadresse erreichbar."
                      : "Only mobile endpoints are reachable through the temporary local network address."
                    : locale === "de"
                      ? "Die Desktop-App bleibt auf 127.0.0.1 beschränkt, bis Sie das temporäre lokale Kopplungsfenster öffnen."
                      : "The desktop app stays bound to 127.0.0.1 until you open the temporary local pairing window."}
                </AlertDescription>
              </Alert>
              <dl className="grid gap-2 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">{locale === "de" ? "Status" : "Status"}</dt>
                  <dd className="font-medium">
                    {mobileBridgeStatus?.running
                      ? locale === "de"
                        ? "Geöffnet"
                        : "Open"
                      : locale === "de"
                        ? "Geschlossen"
                        : "Closed"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">{locale === "de" ? "Countdown" : "Countdown"}</dt>
                  <dd className="font-medium" data-now={now}>{mobileCountdown}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">{locale === "de" ? "Schnittstelle" : "Interface"}</dt>
                  <dd className="font-medium">
                    {mobileBridgeStatus?.interface
                      ? `${mobileBridgeStatus.interface.name} (${mobileBridgeStatus.interface.address})`
                      : locale === "de"
                        ? "Nicht ausgewählt"
                        : "Not selected"}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">{locale === "de" ? "Letzte Anfrage" : "Last request"}</dt>
                  <dd className="font-medium">
                    {mobileBridgeStatus?.lastMobileRequest
                      ? `${mobileBridgeStatus.lastMobileRequest.method} ${mobileBridgeStatus.lastMobileRequest.path} (${mobileBridgeStatus.lastMobileRequest.statusCode ?? "..."})`
                      : locale === "de"
                        ? "Noch keine"
                        : "None yet"}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-muted-foreground">{locale === "de" ? "LAN-Endpunkt" : "LAN endpoint"}</dt>
                  <dd className="break-all font-medium">{mobileBridgeStatus?.endpointUrl ?? "127.0.0.1 only"}</dd>
                </div>
              </dl>
              {mobileSession ? (
                <>
                  <dl className="grid gap-2 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-muted-foreground">{locale === "de" ? "Desktop" : "Desktop"}</dt>
                      <dd className="font-medium">{mobileSession.payload.desktop_name}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">{locale === "de" ? "Gültig bis" : "Expires"}</dt>
                      <dd className="font-medium">{new Date(mobileSession.expires_at).toLocaleString()}</dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-muted-foreground">{locale === "de" ? "Endpunkt" : "Endpoint"}</dt>
                      <dd className="break-all font-medium">{mobileSession.payload.endpoint_url}</dd>
                    </div>
                  </dl>
                  <textarea
                    className="min-h-48 w-full resize-y rounded-md border border-border bg-background p-3 font-mono text-xs text-foreground"
                    readOnly
                    value={mobilePairingText}
                    aria-label={locale === "de" ? "Mobile Kopplungs-Payload" : "Mobile pairing payload"}
                  />
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {locale === "de"
                    ? "Noch kein Payload erzeugt. Öffnen Sie danach die mobile App und nutzen Sie die Kopplungsansicht."
                    : "No payload created yet. After creating one, open the mobile app and use its pairing screen."}
                </p>
              )}
              {mobilePairingError ? <p className="text-sm text-destructive">{mobilePairingError}</p> : null}
            </div>
          </CardContent>
        </Card>
      </section>

      <Dialog open={mobileRiskDialogOpen} onOpenChange={setMobileRiskDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{locale === "de" ? "Lokale Telefonkopplung öffnen" : "Open local phone pairing"}</DialogTitle>
            <DialogDescription>
              Local phone pairing opens a temporary network port on this Mac so your phone can connect over the same Wi-Fi network. Other devices on this network may be able to reach that port while it is open. Only continue on a trusted home or private network.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMobileRiskDialogOpen(false)} disabled={mobilePairingBusy}>
              Cancel
            </Button>
            <Button onClick={() => void handleCreateMobilePairingSession()} disabled={mobilePairingBusy}>
              {mobilePairingBusy ? "Opening..." : "Open temporary pairing window"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PairingMatrix({ value }: { value: string }) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    if (!value) {
      setDataUrl(null);
      return;
    }
    void QRCode.toDataURL(value, {
      errorCorrectionLevel: "M",
      margin: 2,
      scale: 6,
      color: {
        dark: "#111827",
        light: "#ffffff"
      }
    }).then((nextDataUrl) => {
      if (active) {
        setDataUrl(nextDataUrl);
      }
    });
    return () => {
      active = false;
    };
  }, [value]);

  return (
    <div className="flex aspect-square w-full max-w-64 items-center justify-center rounded-md border border-border bg-white p-3">
      {dataUrl ? (
        <img src={dataUrl} alt="Mobile pairing QR code" className="h-full w-full object-contain" />
      ) : (
        <QrCode className="h-20 w-20 text-muted-foreground" aria-hidden="true" />
      )}
    </div>
  );
}
