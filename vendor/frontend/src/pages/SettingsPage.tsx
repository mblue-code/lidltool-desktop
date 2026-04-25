import { Bot, Database, PaintBucket, ShieldCheck, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/i18n";

export function SettingsPage() {
  const { locale, t } = useI18n();
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
              <Button asChild variant="outline">
                <Link to={section.to}>{t("common.open")}</Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
