import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  cancelConnectorBootstrap,
  confirmConnectorBootstrap,
  fetchConnectorAuthStatus,
  fetchConnectorConfig,
  fetchConnectorBootstrapStatus,
  fetchConnectors,
  reloadConnectors,
  startConnectorBootstrap,
  startConnectorSync,
  submitConnectorConfig,
  type ConnectorAuthStatus,
  type ConnectorBootstrapStatus,
  type ConnectorConfig,
  type ConnectorConfigField,
  type ConnectorDiscoveryRow
} from "@/api/connectors";
import { PageHeader } from "@/components/shared/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  getDesktopConnectorBridge,
  type DesktopConnectorCatalogEntry,
  type DesktopConnectorCallbackEvent,
  type DesktopExternalBrowserId,
  type DesktopExternalBrowserPreferenceState,
  type DesktopReceiptPluginPackInfo
} from "@/lib/desktop-api";
import { useI18n, type SupportedLocale } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/utils/format";

type SetupState = {
  connector: ConnectorDiscoveryRow;
  mode: "setup" | "reconnect" | "configure";
};

type PackGuideState = {
  pack: DesktopReceiptPluginPackInfo;
  catalogEntry: DesktopConnectorCatalogEntry | null;
  showEnableAction: boolean;
};

type SetupValues = Record<string, string | boolean>;

type ConnectorGuide = {
  headline: string;
  summary: string;
  speedDescription: string;
  caution: string;
  steps: Array<{
    title: string;
    description: string;
  }>;
};

type ConnectorTaskState = "setup_required" | "ready" | "syncing" | "needs_attention";

type FeedbackState = {
  variant: "default" | "destructive";
  title: string;
  message: string;
  dismissAfterMs?: number;
};

type AuthCompletionPromptState = {
  sourceId: string;
  confirmedAt: number;
  detail: string | null;
};

type ConnectorPrimaryActionKind = "set_up" | "reconnect" | "sync_now" | "open_source" | null;

type PendingSyncStartState = Record<
  string,
  {
    full: boolean;
    startedAt: number;
    expiresAt: number;
  }
>;

type FirstRunPromptState = Record<
  string,
  {
    activatedAt: number;
    expiresAt: number;
  }
>;

type ManualCallbackState = Record<string, string>;
type PendingConnectorCallbackState = DesktopConnectorCallbackEvent[];

const SHORT_SUCCESS_DISMISS_MS = 60_000;
const OPTIMISTIC_SYNC_START_MS = 20_000;

function byLocale(locale: SupportedLocale, en: string, de: string): string {
  return locale === "de" ? de : en;
}

async function openExternalUrl(url: string | null | undefined): Promise<void> {
  if (!url) {
    return;
  }
  if (typeof window.desktopApi?.openExternalUrl === "function") {
    await window.desktopApi.openExternalUrl(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

function externalBrowserLabel(browserId: DesktopExternalBrowserId, locale: SupportedLocale): string {
  switch (browserId) {
    case "arc":
      return "Arc";
    case "atlas":
      return "Atlas";
    case "google_chrome":
      return "Google Chrome";
    case "system_default":
    default:
      return byLocale(locale, "System default", "Systemstandard");
  }
}

function preferredBrowserCallToAction(
  sourceId: string,
  preferredBrowser: DesktopExternalBrowserId | null | undefined,
  locale: SupportedLocale
): string {
  if (!isLidlConnector(sourceId)) {
    return byLocale(locale, "Open in your browser", "Im Browser öffnen");
  }
  if (preferredBrowser && preferredBrowser !== "system_default") {
    return byLocale(
      locale,
      `Open Lidl in ${externalBrowserLabel(preferredBrowser, locale)}`,
      `Lidl in ${externalBrowserLabel(preferredBrowser, locale)} öffnen`
    );
  }
  return byLocale(locale, "Open Lidl in your default browser", "Lidl im Standardbrowser öffnen");
}

function manualCallbackTitle(sourceId: string, locale: SupportedLocale): string {
  if (isLidlConnector(sourceId)) {
    return byLocale(
      locale,
      "If the browser finishes but the app does not connect, paste the callback URL here.",
      "Wenn der Browser fertig ist, die App sich aber nicht verbindet, fügen Sie hier die Callback-URL ein."
    );
  }
  return byLocale(
    locale,
    "If the app does not continue automatically, paste the final browser URL here.",
    "Wenn die App nicht automatisch weitergeht, fügen Sie hier die finale Browser-URL ein."
  );
}

function manualCallbackDescription(sourceId: string, locale: SupportedLocale): string {
  if (isLidlConnector(sourceId)) {
    return byLocale(
      locale,
      "Use the full com.lidlplus.app://callback URL if the browser shows it. If Lidl lands on an error page instead, copy the full address from the browser bar and paste it here.",
      "Verwenden Sie die vollständige com.lidlplus.app://callback-URL, falls der Browser sie anzeigt. Wenn Lidl stattdessen auf einer Fehlerseite landet, kopieren Sie die vollständige Adresse aus der Browserleiste und fügen Sie sie hier ein."
    );
  }
  return byLocale(
    locale,
    "Use the full URL from the browser after the PENNY redirect, even if the page looks broken.",
    "Verwenden Sie die vollständige URL aus dem Browser nach der PENNY-Weiterleitung, auch wenn die Seite kaputt aussieht."
  );
}

function manualCallbackPlaceholder(sourceId: string, locale: SupportedLocale): string {
  if (isLidlConnector(sourceId)) {
    return "com.lidlplus.app://callback?code=...";
  }
  return byLocale(
    locale,
    "https://www.penny.de/app/login?code=...",
    "https://www.penny.de/app/login?code=..."
  );
}

function callbackPrefixesFromMetadata(metadata: Record<string, unknown> | undefined): string[] {
  const rawPrefixes = metadata?.callback_url_prefixes;
  if (!Array.isArray(rawPrefixes)) {
    return [];
  }
  return rawPrefixes.filter((value): value is string => typeof value === "string" && value.trim().length > 0);
}

function resolveManualCallbackSourceId(
  callbackUrl: string,
  authStatusBySourceId: Map<string, ConnectorAuthStatus>,
  selectedLidlSourceId: string
): string | null {
  for (const [sourceId, authStatus] of authStatusBySourceId.entries()) {
    if (authStatus.bootstrap?.status !== "running") {
      continue;
    }
    if (authStatus.metadata?.manual_callback_supported !== true) {
      continue;
    }
    const prefixes = callbackPrefixesFromMetadata(authStatus.metadata);
    if (prefixes.some((prefix) => callbackUrl.startsWith(prefix))) {
      return sourceId;
    }
  }
  if (callbackUrl.startsWith("com.lidlplus.app://callback")) {
    return selectedLidlSourceId || "lidl_plus_de";
  }
  return null;
}

function connectorCallbackEventKey(event: DesktopConnectorCallbackEvent): string {
  return [
    String(event.sourceId ?? ""),
    String(event.url ?? ""),
    event.confirmed ? "confirmed" : "pending",
    String(event.confirmedAt ?? "")
  ].join("|");
}

const CONNECTOR_FIELD_LOCALIZATION_OVERRIDES: Record<
  string,
  Record<string, { label?: string; description?: string; placeholder?: string }>
> = {
  amazon_de: {
    years: {
      label: "Zu prüfende Jahre",
      description:
        "Wie viele Amazon-Bestelljahre geprüft werden. Mehr Jahre dauern deutlich länger; rechnen Sie grob mit mehreren Minuten pro Jahr.",
      placeholder: "1"
    },
    headless: {
      label: "Import im Hintergrund ausführen",
      description: "Standardmäßig aktiviert. Nur deaktivieren, wenn Sie Amazon-Seiten während der Fehlersuche sichtbar beobachten möchten."
    },
    dump_html: {
      label: "Debug-HTML-Verzeichnis",
      description: "Optionaler Debug-Ordner für aufgezeichnetes Amazon-Listen- und Detail-HTML während des Connector-Tests.",
      placeholder: "/absoluter/pfad/zu/amazon-debug-html"
    }
  },
  dm_de: {
    store_name: {
      label: "Filialbezeichnung",
      description: "Optionaler Anzeigename für importierte dm-Belege."
    },
    domain: {
      label: "dm-Domain",
      description: "Optionaler Host-Override für Einrichtung und Synchronisierung."
    },
    headless: {
      label: "Headless-Synchronisierung",
      description: "Synchronisierung nach der Einrichtung ohne sichtbares Browserfenster ausführen."
    },
    max_pages: {
      label: "Limit für Belegseiten",
      description: "Optionales Maximum an Bestellverlaufsseiten, die pro Lauf geprüft werden."
    }
  },
  rossmann_de: {
    email: {
      label: "Rossmann E-Mail",
      description: "Die E-Mail-Adresse des Rossmann-Kontos wird nur einmal während der Einrichtung verwendet."
    },
    password: {
      label: "Rossmann Passwort",
      description: "Das Passwort des Rossmann-Kontos wird nur während der Einrichtung oder erneuten Anmeldung verwendet."
    },
    discovery_limit: {
      label: "Seitengröße für Belege",
      description: "Optionales Limit pro Lauf, das nach der hostseitigen Belegerkennung angewendet wird."
    },
    timeout_seconds: {
      label: "HTTP-Timeout",
      description: "Optionales Timeout für Rossmann- und Anybill-API-Aufrufe."
    },
    state_file: {
      label: "Plugin-Statusdatei",
      description: "Optionaler Override für den persistenten Pfad der Rossmann-Plugindaten."
    },
    account_api_base_url: {
      label: "Rossmann Konto-API",
      description: "Optionaler Override der Rossmann-App-Konto-API für Operator-Debugging."
    },
    anybill_base_url: {
      label: "Anybill-Basis-URL",
      description: "Optionaler Override der Anybill-API-Basis-URL für Operator-Debugging."
    }
  },
  kaufland_de: {
    store_name: {
      label: "Filialbezeichnung",
      description: "Optionaler Anzeigename für importierte Kaufland-Belege."
    },
    country_code: {
      label: "Belegland",
      description: "Legt fest, aus welchem Kaufland-Landportal Belege importiert werden."
    },
    preferred_store_id: {
      label: "Bevorzugte Filial-ID",
      description: "Optional. Priorisiert eine bestimmte Kaufland-Filiale während Einrichtung und Import."
    },
    state_file: {
      label: "Plugin-Statusdatei",
      description: "Optionaler Override für den persistenten Pfad der Kaufland-Plugindaten."
    },
    fixture_file: {
      label: "Fixture-Datei",
      description: "Optionaler Fixture-Pfad für Desktop-Debugging und Connector-Tests."
    }
  },
  rewe_de: {
    store_name: {
      label: "Filialbezeichnung",
      description: "Optionaler Anzeigename für importierte REWE-Belege."
    },
    headless: {
      label: "Headless-Synchronisierung",
      description: "Synchronisierung nach der Einrichtung ohne sichtbares Browserfenster ausführen."
    },
    max_records: {
      label: "Beleglimit",
      description: "Optionales Limit für die Anzahl importierter REWE-Belege pro Lauf."
    },
    detail_fetch_limit: {
      label: "Limit für Onlinedetails",
      description: "Optionales Limit dafür, wie viele Detailseiten pro Synchronisierung geladen werden."
    },
    import_storage_state_file: {
      label: "Storage-State-Datei importieren",
      description: "Importiert eine bereits gespeicherte Browser-Sitzung für REWE."
    },
    chrome_live_tab: {
      label: "Live-Chrome-Tab verwenden",
      description: "Verwendet einen bereits geöffneten Chrome-Tab für die Einrichtung oder Fehlersuche."
    },
    chrome_cookie_export: {
      label: "Laufende Chrome-Sitzung verwenden",
      description: "Liest Cookies aus einer laufenden Chrome-Sitzung, statt eine neue Anmeldung zu erzwingen."
    },
    chrome_profile_import: {
      label: "Chrome-Profil importieren",
      description: "Importiert Sitzungsdaten direkt aus einem vorhandenen Chrome-Profil."
    },
    chrome_user_data_dir: {
      label: "Chrome-Benutzerdatenverzeichnis",
      description: "Optionaler Pfad zum Chrome-Benutzerdatenverzeichnis für Profilimporte."
    },
    chrome_profile_name: {
      label: "Chrome-Profilname",
      description: "Optionaler Profilname innerhalb des Chrome-Benutzerdatenverzeichnisses."
    }
  }
};

function localizeConnectorConfigField(field: ConnectorConfigField, sourceId: string, locale: SupportedLocale): ConnectorConfigField {
  if (locale !== "de") {
    return field;
  }
  const overrides = CONNECTOR_FIELD_LOCALIZATION_OVERRIDES[sourceId]?.[field.key];
  if (!overrides) {
    return field;
  }
  return {
    ...field,
    label: overrides.label ?? field.label,
    description: overrides.description ?? field.description,
    placeholder: overrides.placeholder ?? field.placeholder
  };
}

function compareVersions(left: string, right: string): number {
  const leftParts = left.split(/[\.-]/);
  const rightParts = right.split(/[\.-]/);
  const maxLength = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < maxLength; index += 1) {
    const leftPart = leftParts[index] ?? "0";
    const rightPart = rightParts[index] ?? "0";
    const leftNumber = Number(leftPart);
    const rightNumber = Number(rightPart);
    const bothNumeric = Number.isFinite(leftNumber) && Number.isFinite(rightNumber);
    const comparison = bothNumeric
      ? leftNumber - rightNumber
      : leftPart.localeCompare(rightPart, undefined, { numeric: true, sensitivity: "base" });
    if (comparison !== 0) {
      return comparison < 0 ? -1 : 1;
    }
  }
  return 0;
}

function initialSetupValues(config: ConnectorConfig): SetupValues {
  const nextValues: SetupValues = {};
  for (const field of config.fields) {
    if (field.sensitive) {
      nextValues[field.key] = "";
      continue;
    }
    if (typeof field.value === "boolean") {
      nextValues[field.key] = field.value;
    } else if (field.value === null || field.value === undefined) {
      nextValues[field.key] = "";
    } else {
      nextValues[field.key] = String(field.value);
    }
  }
  return nextValues;
}

function fieldsForSetupMode(
  fields: ConnectorConfigField[],
  mode: SetupState["mode"]
): ConnectorConfigField[] {
  if (mode === "configure") {
    return fields;
  }
  return fields.filter((field) => !field.operator_only);
}

function buildConfigPayload(
  config: ConnectorConfig,
  visibleFields: ConnectorConfigField[],
  values: SetupValues,
  clearSecretKeys: string[]
): {
  values: Record<string, string | number | boolean | null>;
  clear_secret_keys?: string[];
} {
  const payloadValues: Record<string, string | number | boolean | null> = {};
  const clearSet = new Set(clearSecretKeys);
  const visibleKeys = new Set(visibleFields.map((field) => field.key));

  for (const field of config.fields) {
    if (!visibleKeys.has(field.key)) {
      continue;
    }
    const rawValue = values[field.key];
    if (field.sensitive) {
      if (typeof rawValue === "string" && rawValue.trim()) {
        payloadValues[field.key] = rawValue.trim();
        clearSet.delete(field.key);
      } else if (!field.has_value) {
        payloadValues[field.key] = null;
      }
      continue;
    }
    if (field.input_kind === "boolean") {
      payloadValues[field.key] = Boolean(rawValue);
      continue;
    }
    if (typeof rawValue === "string") {
      const trimmed = rawValue.trim();
      payloadValues[field.key] = trimmed.length > 0 ? trimmed : null;
    }
  }

  return {
    values: payloadValues,
    clear_secret_keys: clearSet.size > 0 ? Array.from(clearSet) : undefined
  };
}

function trustLabel(trustClass: string | null | undefined, locale: SupportedLocale): string {
  if (trustClass === "official") {
    return byLocale(locale, "Official", "Offiziell");
  }
  if (trustClass === "community_verified") {
    return byLocale(locale, "Community verified", "Community-geprüft");
  }
  if (trustClass === "local_custom") {
    return byLocale(locale, "Local custom", "Lokal angepasst");
  }
  if (trustClass === "community_unsigned") {
    return byLocale(locale, "Community unsigned", "Community-ohne Signatur");
  }
  return byLocale(locale, "Unknown trust", "Unbekannter Vertrauensstatus");
}

function isAmazonConnector(sourceId: string): boolean {
  return sourceId === "amazon_de" || sourceId === "amazon_fr" || sourceId === "amazon_gb";
}

function isLidlConnector(sourceId: string): boolean {
  return sourceId === "lidl_plus_de" || sourceId === "lidl_plus_fr" || sourceId === "lidl_plus_gb";
}

function isReweConnector(sourceId: string): boolean {
  return sourceId === "rewe_de";
}

function isPennyConnector(sourceId: string): boolean {
  return sourceId === "penny_de";
}

function connectorHasDurableAuthState(connector: ConnectorDiscoveryRow): boolean {
  return connector.advanced.auth_state === "connected";
}

function reweConnectorHasUsableSession(connector: ConnectorDiscoveryRow): boolean {
  if (!isReweConnector(connector.source_id)) {
    return false;
  }
  return connectorHasDurableAuthState(connector);
}

function shouldShowBootstrapStatus(
  connector: ConnectorDiscoveryRow,
  bootstrapStatus: ConnectorBootstrapStatus | null
): boolean {
  if (bootstrapStatus === null || bootstrapStatus.status === "idle") {
    return false;
  }
  if (reweConnectorHasUsableSession(connector)) {
    return false;
  }
  return true;
}

function isDesktopBundledBuiltinConnector(sourceId: string): boolean {
  return isAmazonConnector(sourceId) || isLidlConnector(sourceId);
}

function connectorSortOrder(sourceId: string): number {
  if (sourceId.endsWith("_de")) {
    return 0;
  }
  if (sourceId.endsWith("_fr")) {
    return 1;
  }
  if (sourceId.endsWith("_gb")) {
    return 2;
  }
  return 99;
}

function connectorMarketLabel(connector: ConnectorDiscoveryRow, locale: SupportedLocale): string {
  const germany = byLocale(locale, "Germany", "Deutschland");
  const france = byLocale(locale, "France", "Frankreich");
  const unitedKingdom = byLocale(locale, "United Kingdom", "Vereinigtes Königreich");
  if (connector.source_id === "lidl_plus_de") {
    return germany;
  }
  if (connector.source_id === "lidl_plus_fr") {
    return france;
  }
  if (connector.source_id === "lidl_plus_gb") {
    return unitedKingdom;
  }
  if (connector.source_id === "amazon_de") {
    return `${germany} (amazon.de)`;
  }
  if (connector.source_id === "amazon_fr") {
    return `${france} (amazon.fr)`;
  }
  if (connector.source_id === "amazon_gb") {
    return `${unitedKingdom} (amazon.co.uk)`;
  }
  return connector.display_name;
}

function connectorDisplayName(connector: ConnectorDiscoveryRow): string {
  if (isAmazonConnector(connector.source_id)) {
    return "Amazon";
  }
  if (isLidlConnector(connector.source_id)) {
    return "Lidl Plus";
  }
  return connector.display_name;
}

function connectorTaskState(connector: ConnectorDiscoveryRow): ConnectorTaskState {
  if (connector.ui.status === "syncing") {
    return "syncing";
  }
  if (
    connector.actions.primary.kind === "reconnect" ||
    connector.advanced.auth_state === "reauth_required" ||
    connector.advanced.auth_state === "auth_failed" ||
    connector.ui.status === "needs_attention" ||
    connector.ui.status === "error"
  ) {
    return "needs_attention";
  }
  if (
    connector.actions.primary.kind === "set_up" ||
    connector.advanced.auth_state === "not_connected" ||
    connector.ui.status === "setup_required" ||
    connector.ui.status === "preview"
  ) {
    return "setup_required";
  }
  return "ready";
}

function connectorStatusLabel(state: ConnectorTaskState, locale: SupportedLocale): string {
  switch (state) {
    case "setup_required":
      return byLocale(locale, "Setup required", "Einrichtung nötig");
    case "ready":
      return byLocale(locale, "Ready", "Bereit");
    case "syncing":
      return byLocale(locale, "Importing", "Import läuft");
    case "needs_attention":
      return byLocale(locale, "Needs attention", "Aktion nötig");
  }
}

function packStateLabel(pack: DesktopReceiptPluginPackInfo, locale: SupportedLocale): string {
  if (pack.status === "enabled") {
    return byLocale(locale, "Enabled", "Aktiv");
  }
  if (pack.status === "disabled") {
    return byLocale(locale, "Stored locally", "Lokal gespeichert");
  }
  if (pack.status === "revoked") {
    return byLocale(locale, "Blocked", "Blockiert");
  }
  if (pack.status === "incompatible") {
    return byLocale(locale, "Incompatible", "Nicht kompatibel");
  }
  return byLocale(locale, "Needs attention", "Aktion nötig");
}

function findCatalogEntry(
  catalogEntries: DesktopConnectorCatalogEntry[],
  connector: ConnectorDiscoveryRow,
  pack: DesktopReceiptPluginPackInfo | null
): DesktopConnectorCatalogEntry | null {
  const bySource = catalogEntries.find((entry) => entry.source_id === connector.source_id);
  if (bySource) {
    return bySource;
  }
  if (pack) {
    return (
      catalogEntries.find((entry) => entry.plugin_id === pack.pluginId) ??
      (pack.catalogEntryId
        ? catalogEntries.find((entry) => entry.entry_id === pack.catalogEntryId) ?? null
        : null)
    );
  }
  return null;
}

function findCatalogEntryForPack(
  catalogEntries: DesktopConnectorCatalogEntry[],
  pack: DesktopReceiptPluginPackInfo
): DesktopConnectorCatalogEntry | null {
  return (
    (pack.catalogEntryId
      ? catalogEntries.find((entry) => entry.entry_id === pack.catalogEntryId)
      : null) ??
    catalogEntries.find((entry) => entry.plugin_id === pack.pluginId) ??
    catalogEntries.find((entry) => entry.source_id === pack.sourceId) ??
    null
  );
}

function fallbackConnectorGuide(displayName: string, locale: SupportedLocale): ConnectorGuide {
  return {
    headline: byLocale(locale, "Simple first-run setup", "Einfache Ersteinrichtung"),
    summary: byLocale(
      locale,
      `${displayName} needs a quick sign-in before it can import receipts on this computer.`,
      `${displayName} braucht zuerst eine kurze Anmeldung, bevor Belege auf diesem Gerät importiert werden können.`
    ),
    speedDescription: byLocale(
      locale,
      "Normal speed. Time can vary depending on the retailer and your account.",
      "Normale Geschwindigkeit. Die Dauer hängt vom Händler und von Ihrem Konto ab."
    ),
    caution: byLocale(
      locale,
      "If something changes on the retailer site, you may need to reconnect later.",
      "Wenn sich beim Händler etwas ändert, kann später eine erneute Anmeldung nötig sein."
    ),
    steps: [
      {
        title: byLocale(locale, "Turn it on", "Aktivieren"),
        description: byLocale(
          locale,
          "Enable the connector first so this desktop app can load it.",
          "Aktivieren Sie die Anbindung zuerst, damit diese Desktop-App sie laden kann."
        )
      },
      {
        title: byLocale(locale, "Finish setup and import", "Anmelden und importieren"),
        description: byLocale(
          locale,
          "Use the connector card to sign in if needed, then start your first import.",
          "Melden Sie sich bei Bedarf über diese Karte an und starten Sie dann den ersten Import."
        )
      }
    ]
  };
}

function localizedAmazonGuide(locale: SupportedLocale): ConnectorGuide {
  return {
    headline: byLocale(
      locale,
      "Amazon imports use a visible browser session",
      "Amazon-Importe laufen über eine sichtbare Browser-Sitzung"
    ),
    summary: byLocale(
      locale,
      "Amazon does not provide a simple receipt API here. Outlays opens Chrome/Chromium, signs into your Amazon session, walks through the selected order years, opens order and item pages one by one, and then imports what it can parse.",
      "Amazon stellt hier keine einfache Beleg-API bereit. Outlays öffnet Chrome/Chromium, nutzt Ihre Amazon-Sitzung, geht die ausgewählten Bestelljahre durch, öffnet Bestell- und Artikelseiten nacheinander und importiert anschließend, was sicher erkannt werden kann."
    ),
    speedDescription: byLocale(
      locale,
      "Plan for several minutes per year. A large first import, for example around 10 years, can take about half an hour or longer depending on Amazon, CAPTCHA checks, and network speed.",
      "Planen Sie mehrere Minuten pro Jahr ein. Ein großer Erstimport, zum Beispiel etwa 10 Jahre, kann je nach Amazon, CAPTCHA-Prüfungen und Netzwerk ungefähr eine halbe Stunde oder länger dauern."
    ),
    caution: byLocale(
      locale,
      "Leave the browser and Outlays open while the import runs. If Amazon asks for login, MFA, or CAPTCHA, finish it in that browser; if Amazon blocks the session later, reconnect before retrying.",
      "Lassen Sie Browser und Outlays geöffnet, während der Import läuft. Wenn Amazon Login, MFA oder CAPTCHA verlangt, schließen Sie das in diesem Browser ab; wenn Amazon die Sitzung später blockiert, melden Sie die Anbindung vor dem nächsten Versuch erneut an."
    ),
    steps: [
      {
        title: byLocale(locale, "Choose how many years to scan", "Anzahl der Jahre auswählen"),
        description: byLocale(
          locale,
          "The Years field controls how much Amazon history the first full import scans. Start smaller if you want a quick test.",
          "Das Feld Jahre steuert, wie viel Amazon-Historie der Vollimport durchsucht. Wählen Sie weniger Jahre, wenn Sie zuerst schnell testen möchten."
        )
      },
      {
        title: byLocale(locale, "Finish Amazon sign-in in Chrome", "Amazon-Anmeldung in Chrome abschließen"),
        description: byLocale(
          locale,
          "Outlays opens a browser profile for Amazon. Complete login, MFA, and any human check there.",
          "Outlays öffnet ein Browserprofil für Amazon. Schließen Sie dort Login, MFA und mögliche Mensch-Prüfungen ab."
        )
      },
      {
        title: byLocale(locale, "Let the browser work through the history", "Browser die Historie abarbeiten lassen"),
        description: byLocale(
          locale,
          "During a full import the browser may visibly open many order, invoice, and item pages. That activity is expected.",
          "Während eines Vollimports kann der Browser sichtbar viele Bestell-, Rechnungs- und Artikelseiten öffnen. Das ist erwartbar."
        )
      },
      {
        title: byLocale(locale, "Review the result in Outlays", "Ergebnis in Outlays prüfen"),
        description: byLocale(
          locale,
          "When the run finishes, Outlays should show the imported transactions and any warnings instead of staying silently in a syncing state.",
          "Nach Abschluss sollte Outlays die importierten Transaktionen und mögliche Hinweise anzeigen, statt still im Synchronisieren-Zustand zu bleiben."
        )
      }
    ]
  };
}

function localizedKauflandGuide(locale: SupportedLocale): ConnectorGuide {
  return {
    headline: byLocale(locale, "Sign in with your Kaufland account", "Mit Ihrem Kaufland-Konto anmelden"),
    summary: byLocale(
      locale,
      "Kaufland receipt sync uses the same Cidaas browser login flow as the Kaufland Android app.",
      "Der Kaufland-Belegimport nutzt denselben Cidaas-Browser-Login wie die Kaufland-Android-App."
    ),
    speedDescription: byLocale(
      locale,
      "Usually quick once the Kaufland login finishes in the browser window opened by the desktop app.",
      "Normalerweise schnell, sobald die Kaufland-Anmeldung im von der Desktop-App geöffneten Browserfenster abgeschlossen ist."
    ),
    caution: byLocale(
      locale,
      "This connector targets app-backed grocery receipts, not marketplace orders from kaufland.de.",
      "Diese Anbindung richtet sich auf app-basierte Lebensmittelbelege und nicht auf Marktplatzbestellungen von kaufland.de."
    ),
    steps: [
      {
        title: byLocale(locale, "Start connector sign-in", "Anbindung anmelden"),
        description: byLocale(
          locale,
          "Use the normal setup action so the desktop app can open the Kaufland login flow for you.",
          "Nutzen Sie die normale Einrichtungsaktion, damit die Desktop-App den Kaufland-Login für Sie öffnen kann."
        )
      },
      {
        title: byLocale(locale, "Finish the Kaufland login", "Kaufland-Login abschließen"),
        description: byLocale(
          locale,
          "Sign in in the browser window opened by the desktop app and let the redirect finish there.",
          "Melden Sie sich im von der Desktop-App geöffneten Browserfenster an und lassen Sie die Weiterleitung dort vollständig durchlaufen."
        )
      },
      {
        title: byLocale(locale, "Import digital receipts", "Digitale Belege importieren"),
        description: byLocale(
          locale,
          "After the callback succeeds, later imports run through Kaufland's receipt API from the host side.",
          "Sobald der Callback abgeschlossen ist, laufen spätere Importe hostseitig über Kauflands Beleg-API."
        )
      }
    ]
  };
}

function localizedDmGuide(locale: SupportedLocale): ConnectorGuide {
  return {
    headline: byLocale(locale, "Take dm slowly on the first run", "dm beim ersten Lauf bewusst langsam angehen"),
    summary: byLocale(
      locale,
      "dm works best when the first sign-in and import are allowed to run without rushing between screens.",
      "dm funktioniert am zuverlässigsten, wenn die erste Anmeldung und der erste Import ohne Hektik durchlaufen dürfen."
    ),
    speedDescription: byLocale(
      locale,
      "Usually slower than other connectors. The first import can take a while even when everything is working correctly.",
      "Meist langsamer als andere Anbindungen. Der erste Import kann etwas dauern, auch wenn alles korrekt funktioniert."
    ),
    caution: byLocale(
      locale,
      "If dm rejects the first sign-in attempt, start setup once more. A second attempt can still succeed without changing your credentials.",
      "Wenn dm den ersten Anmeldeversuch ablehnt, starten Sie die Einrichtung noch einmal. Ein zweiter Versuch kann trotz gleicher Zugangsdaten erfolgreich sein."
    ),
    steps: [
      {
        title: byLocale(locale, "Enable the connector", "Anbindung aktivieren"),
        description: byLocale(
          locale,
          "Turn dm on first so the desktop app can load the plugin locally.",
          "Aktivieren Sie dm zuerst, damit die Desktop-App das Plugin lokal laden kann."
        )
      },
      {
        title: byLocale(locale, "Finish sign-in", "Anmeldung abschließen"),
        description: byLocale(
          locale,
          "Use Set up and complete the login in the browser window opened by the app.",
          "Nutzen Sie Einrichten und schließen Sie die Anmeldung im von der App geöffneten Browserfenster ab."
        )
      },
      {
        title: byLocale(locale, "Start the first import", "Ersten Import starten"),
        description: byLocale(
          locale,
          "Right after sign-in, use Import receipts for the normal run or Import full history for the one-time catch-up.",
          "Nutzen Sie direkt nach der Anmeldung Belege importieren für den normalen Lauf oder Gesamte Historie laden für den einmaligen Nachimport."
        )
      }
    ]
  };
}

function localizedReweGuide(locale: SupportedLocale): ConnectorGuide {
  return {
    headline: byLocale(locale, "Log into REWE in Chrome first", "Melden Sie sich zuerst in Chrome bei REWE an"),
    summary: byLocale(
      locale,
      "REWE works best when you first open the REWE website in your normal Chrome profile, sign in there, and leave the logged-in tab open before pressing Set up.",
      "REWE funktioniert am besten, wenn Sie zuerst die REWE-Website in Ihrem normalen Chrome-Profil öffnen, sich dort anmelden und den eingeloggten Tab offen lassen, bevor Sie auf Einrichten klicken."
    ),
    speedDescription: byLocale(
      locale,
      "Usually quick once the REWE tab is already logged in in Chrome.",
      "Normalerweise schnell, sobald der REWE-Tab in Chrome bereits angemeldet ist."
    ),
    caution: byLocale(
      locale,
      "If REWE expires the saved session later, repeat the same flow: open Chrome, sign into REWE again, leave the tab open, then run Set up again.",
      "Wenn REWE die gespeicherte Sitzung später beendet, wiederholen Sie einfach denselben Ablauf: Chrome öffnen, erneut bei REWE anmelden, den Tab offen lassen und dann Einrichten erneut starten."
    ),
    steps: [
      {
        title: byLocale(locale, "Open Chrome and sign into REWE", "Chrome öffnen und bei REWE anmelden"),
        description: byLocale(
          locale,
          "Use your everyday Chrome profile and finish the REWE login there, including the emailed code if REWE asks for it.",
          "Nutzen Sie Ihr normales Chrome-Profil und schließen Sie den REWE-Login dort vollständig ab, inklusive E-Mail-Code, falls REWE danach fragt."
        )
      },
      {
        title: byLocale(locale, "Leave the REWE tab open", "REWE-Tab offen lassen"),
        description: byLocale(
          locale,
          "Keep the logged-in REWE tab open so the connector can import that authenticated session.",
          "Lassen Sie den eingeloggten REWE-Tab offen, damit die Anbindung diese authentifizierte Sitzung importieren kann."
        )
      },
      {
        title: byLocale(locale, "Run Set up here", "Hier Einrichten starten"),
        description: byLocale(
          locale,
          "Return to the REWE connector card and press Set up. The connector will try to reuse the logged-in Chrome session first.",
          "Kehren Sie zur REWE-Anbindung zurück und klicken Sie auf Einrichten. Die Anbindung versucht zuerst, die eingeloggte Chrome-Sitzung wiederzuverwenden."
        )
      },
      {
        title: byLocale(locale, "If it stops working later, rerun setup", "Wenn es später nicht mehr funktioniert, erneut einrichten"),
        description: byLocale(
          locale,
          "When REWE expires the session after some days, sign into REWE in Chrome again and press Set up again.",
          "Wenn REWE die Sitzung nach einigen Tagen beendet, melden Sie sich in Chrome erneut bei REWE an und klicken Sie dann wieder auf Einrichten."
        )
      }
    ]
  };
}

function localizedPennyGuide(locale: SupportedLocale): ConnectorGuide {
  return {
    headline: byLocale(locale, "Finish PENNY sign-in in your normal browser", "PENNY-Anmeldung im normalen Browser abschließen"),
    summary: byLocale(
      locale,
      "PENNY opens the real account login in your installed browser profile. After the login finishes, the browser may land on a PENNY page that does not continue. That is expected.",
      "PENNY öffnet die echte Konto-Anmeldung in Ihrem installierten Browserprofil. Nach dem Login kann der Browser auf einer PENNY-Seite landen, die nicht weiterführt. Das ist erwartbar."
    ),
    speedDescription: byLocale(
      locale,
      "Usually quick once the browser accepts the login and any human-check is completed.",
      "Normalerweise schnell, sobald der Browser die Anmeldung akzeptiert und eine eventuelle Mensch-Prüfung abgeschlossen ist."
    ),
    caution: byLocale(
      locale,
      "Do not worry if the browser ends on a PENNY app redirect or not-found page. The desktop app only needs the callback URL and continues from there.",
      "Keine Sorge, wenn der Browser am Ende auf einer PENNY-App-Weiterleitung oder einer Nicht-gefunden-Seite landet. Die Desktop-App braucht nur die Callback-URL und macht danach hier weiter."
    ),
    steps: [
      {
        title: byLocale(locale, "Start sign-in here", "Anmeldung hier starten"),
        description: byLocale(
          locale,
          "Use Set up so the desktop app can open the PENNY login in your installed browser.",
          "Nutzen Sie Einrichten, damit die Desktop-App den PENNY-Login in Ihrem installierten Browser öffnen kann."
        )
      },
      {
        title: byLocale(locale, "Finish login in the browser", "Login im Browser abschließen"),
        description: byLocale(
          locale,
          "Enter your PENNY credentials there and complete any human-check Penny requires.",
          "Geben Sie dort Ihre PENNY-Zugangsdaten ein und schließen Sie eine eventuelle Mensch-Prüfung von PENNY ab."
        )
      },
      {
        title: byLocale(locale, "Return to the app", "Zur App zurückkehren"),
        description: byLocale(
          locale,
          "After the redirect happens, come back here even if the browser page looks broken. The connector will store the sign-in and let you start the first import.",
          "Kehren Sie nach der Weiterleitung hierher zurück, auch wenn die Browserseite kaputt aussieht. Die Anbindung speichert die Anmeldung und lässt Sie dann den ersten Import starten."
        )
      }
    ]
  };
}

function pluginGuideOverride(
  pack: DesktopReceiptPluginPackInfo | null,
  locale: SupportedLocale
): ConnectorGuide | null {
  if (!pack) {
    return null;
  }
  if (pack.sourceId === "kaufland_de") {
    return localizedKauflandGuide(locale);
  }
  if (pack.sourceId === "dm_de") {
    return localizedDmGuide(locale);
  }
  if (pack.sourceId === "rewe_de") {
    return localizedReweGuide(locale);
  }
  if (pack.sourceId === "penny_de") {
    return localizedPennyGuide(locale);
  }
  return null;
}

function primaryActionKind(
  connector: ConnectorDiscoveryRow,
  taskState: ConnectorTaskState,
  firstRunPromptActive: boolean
): ConnectorPrimaryActionKind {
  if (firstRunPromptActive && connector.enable_state === "enabled" && connector.supports_sync && connectorHasDurableAuthState(connector)) {
    return "sync_now";
  }
  if (taskState === "setup_required") {
    return "set_up";
  }
  if (connector.actions.primary.kind === "reconnect") {
    return "reconnect";
  }
  if (connector.actions.primary.kind === "sync_now") {
    return "sync_now";
  }
  if (connector.actions.primary.kind === "open_source") {
    return "open_source";
  }
  return connector.actions.primary.kind as ConnectorPrimaryActionKind;
}

function connectorGuideForPack(
  pack: DesktopReceiptPluginPackInfo | null,
  displayName: string,
  locale: SupportedLocale
): ConnectorGuide {
  const fallback = fallbackConnectorGuide(displayName, locale);
  const override = pluginGuideOverride(pack, locale);
  if (override) {
    return override;
  }
  const onboarding = pack?.onboarding;
  if (!onboarding) {
    return fallback;
  }
  return {
    headline: onboarding.title ?? fallback.headline,
    summary: onboarding.summary ?? fallback.summary,
    speedDescription: onboarding.expectedSpeed ?? fallback.speedDescription,
    caution: onboarding.caution ?? fallback.caution,
    steps: onboarding.steps.length > 0 ? onboarding.steps : fallback.steps
  };
}

function connectorStatusSummary(
  connector: ConnectorDiscoveryRow,
  pack: DesktopReceiptPluginPackInfo | null,
  displayName: string,
  locale: SupportedLocale
): string {
  const taskState = connectorTaskState(connector);
  if (pack?.status === "disabled") {
    return byLocale(
      locale,
      `Turn on ${displayName} to finish adding it to this computer.`,
      `Aktivieren Sie ${displayName}, um die Einrichtung auf diesem Gerät abzuschließen.`
    );
  }
  if (taskState === "syncing") {
    return byLocale(
      locale,
      "Your receipts are being imported now.",
      "Ihre Belege werden gerade importiert."
    );
  }
  if (taskState === "setup_required") {
    if (isReweConnector(connector.source_id)) {
      return byLocale(
        locale,
        "Open REWE in normal Chrome, sign in there, leave the tab open, then press Set up.",
        "Öffnen Sie REWE in normalem Chrome, melden Sie sich dort an, lassen Sie den Tab offen und klicken Sie dann auf Einrichten."
      );
    }
    if (isPennyConnector(connector.source_id)) {
      return byLocale(
        locale,
        "Press Set up, finish the PENNY login in your normal browser, then return here even if the browser shows a PENNY redirect page.",
        "Klicken Sie auf Einrichten, schließen Sie den PENNY-Login in Ihrem normalen Browser ab und kehren Sie dann hierher zurück, auch wenn der Browser eine PENNY-Weiterleitungsseite zeigt."
      );
    }
    return byLocale(
      locale,
      `Sign in once to import receipts from ${displayName}.`,
      `Melden Sie sich einmal an, um Belege von ${displayName} zu importieren.`
    );
  }
  if (taskState === "needs_attention") {
    if (isReweConnector(connector.source_id)) {
      return byLocale(
        locale,
        "REWE needs a quick Chrome reauth before the next import.",
        "REWE braucht vor dem nächsten Import eine kurze erneute Anmeldung in Chrome."
      );
    }
    return byLocale(
      locale,
      "Your sign-in needs a quick refresh before the next import.",
      "Ihre Anmeldung muss vor dem nächsten Import kurz erneuert werden."
    );
  }
  if (connector.last_synced_at) {
    return byLocale(locale, "Everything is ready for the next import.", "Alles ist bereit für den nächsten Import.");
  }
  return byLocale(
    locale,
    "Everything is ready. Start an import whenever you want.",
    "Alles ist bereit. Starten Sie den Import, wann immer Sie möchten."
  );
}

function primaryActionLabel(
  actionKind: ConnectorPrimaryActionKind,
  _taskState: ConnectorTaskState,
  locale: SupportedLocale
): string {
  if (actionKind === "sync_now") {
    return byLocale(locale, "Import receipts", "Belege importieren");
  }
  if (actionKind === "reconnect") {
    return byLocale(locale, "Sign in again", "Erneut anmelden");
  }
  if (actionKind === "open_source") {
    return byLocale(locale, "Open receipts", "Belege öffnen");
  }
  return byLocale(locale, "Set up", "Einrichten");
}

function connectorSecondarySummary(
  connector: ConnectorDiscoveryRow,
  pack: DesktopReceiptPluginPackInfo | null,
  locale: SupportedLocale
): string | null {
  if (connector.last_synced_at) {
    return byLocale(
      locale,
      `Last import: ${formatDateTime(connector.last_synced_at)}`,
      `Letzter Import: ${formatDateTime(connector.last_synced_at)}`
    );
  }
  if (reweConnectorHasUsableSession(connector)) {
    return byLocale(
      locale,
      "The saved Chrome-backed REWE sign-in is ready for the next import.",
      "Die gespeicherte, Chrome-basierte REWE-Anmeldung ist für den nächsten Import bereit."
    );
  }
  if (pack?.status === "disabled") {
    return byLocale(locale, "Saved on this computer, but still turned off.", "Auf diesem Gerät gespeichert, aber noch ausgeschaltet.");
  }
  if (connector.advanced.auth_state === "bootstrap_running") {
    if (isReweConnector(connector.source_id)) {
      return byLocale(
        locale,
        "If Chrome is not already logged into REWE, open Chrome, sign in there, leave the tab open, and then retry setup.",
        "Falls Chrome noch nicht bei REWE angemeldet ist, öffnen Sie Chrome, melden Sie sich dort an, lassen Sie den Tab offen und starten Sie die Einrichtung dann erneut."
      );
    }
    if (isPennyConnector(connector.source_id)) {
      return byLocale(
        locale,
        "Continue the PENNY login in your browser. After the redirect, the browser may show a PENNY page that does not continue. Return here when that happens.",
        "Setzen Sie den PENNY-Login in Ihrem Browser fort. Nach der Weiterleitung kann der Browser eine PENNY-Seite anzeigen, die nicht weiterführt. Kehren Sie dann einfach hierher zurück."
      );
    }
    return byLocale(locale, "Finish sign-in in the browser window the app opened.", "Schließen Sie die Anmeldung im geöffneten Browserfenster ab.");
  }
  if (
    isReweConnector(connector.source_id) &&
    (connector.advanced.auth_state === "reauth_required" || connector.advanced.auth_state === "auth_failed")
  ) {
    return byLocale(
      locale,
      "Open Chrome, sign into REWE again, leave the tab open, then press Sign in again.",
      "Öffnen Sie Chrome, melden Sie sich erneut bei REWE an, lassen Sie den Tab offen und klicken Sie dann auf Erneut anmelden."
    );
  }
  return null;
}

function parseStageValue(line: string, key: string): string | null {
  const match = line.match(new RegExp(`${key}=([^\\s]+)`));
  return match?.[1] ?? null;
}

function blockingBootstrapSourceId(message: string | null | undefined): string | null {
  if (!message) {
    return null;
  }
  const match = message.match(/connector setup is already running for ([^;]+);/i);
  return match?.[1]?.trim() ?? null;
}

function summarizeBootstrapStatus(
  sourceId: string,
  status: ConnectorBootstrapStatus | null,
  latestLine: string | null,
  connector: ConnectorDiscoveryRow,
  locale: SupportedLocale
): string | null {
  const rewe = isReweConnector(sourceId);
  const penny = isPennyConnector(sourceId);
  if (latestLine?.startsWith("Waiting for auth step:")) {
    const step = latestLine.split(":").pop()?.trim();
    if (step === "login_required") {
      if (rewe) {
        return byLocale(
          locale,
          "Open normal Chrome, sign into REWE there, leave the tab open, then run setup again.",
          "Öffnen Sie normales Chrome, melden Sie sich dort bei REWE an, lassen Sie den Tab offen und starten Sie die Einrichtung dann erneut."
        );
      }
      if (penny) {
        return byLocale(
          locale,
          "Finish the PENNY login in your browser. If the browser ends on a PENNY redirect or not-found page, return here; that still counts as a successful handoff.",
          "Schließen Sie den PENNY-Login in Ihrem Browser ab. Wenn der Browser am Ende auf einer PENNY-Weiterleitungs- oder Nicht-gefunden-Seite landet, kehren Sie hierher zurück; das gilt trotzdem als erfolgreicher Handoff."
        );
      }
      return byLocale(locale, "Please finish sign-in in the browser window.", "Bitte schließen Sie die Anmeldung im Browserfenster ab.");
    }
    if (step === "mfa_required") {
      if (rewe) {
        return byLocale(
          locale,
          "Finish the REWE sign-in in normal Chrome, including the emailed code, then rerun setup.",
          "Schließen Sie die REWE-Anmeldung in normalem Chrome ab, inklusive des Codes aus der E-Mail, und starten Sie die Einrichtung dann erneut."
        );
      }
      return byLocale(locale, "Please enter the verification code in the browser window.", "Bitte geben Sie den Bestätigungscode im Browserfenster ein.");
    }
    return byLocale(locale, "Please finish the required step in the browser window.", "Bitte schließen Sie den angezeigten Schritt im Browserfenster ab.");
  }
  if (status?.status === "running") {
    if (rewe) {
      return byLocale(
        locale,
        "REWE is trying to reuse the logged-in normal Chrome session. If it does not complete, open Chrome, sign into REWE there, leave the tab open, and retry setup.",
        "REWE versucht, die angemeldete normale Chrome-Sitzung zu übernehmen. Falls das nicht abgeschlossen wird, öffnen Sie Chrome, melden Sie sich dort bei REWE an, lassen Sie den Tab offen und starten Sie die Einrichtung erneut."
      );
    }
    if (penny) {
      return byLocale(
        locale,
        "The PENNY login is waiting in your browser. After the redirect, the browser may show a dead-end PENNY page. The desktop app will still capture the sign-in and continue here.",
        "Der PENNY-Login wartet in Ihrem Browser. Nach der Weiterleitung kann der Browser eine Sackgassen-Seite von PENNY anzeigen. Die Desktop-App erfasst die Anmeldung trotzdem und macht hier weiter."
      );
    }
    return byLocale(
      locale,
      "Finish sign-in in the browser window opened by the desktop app.",
      "Bitte schließen Sie die Anmeldung im von der Desktop-App geöffneten Browserfenster ab."
    );
  }
  if (status?.status === "succeeded") {
    if (penny) {
      return byLocale(
        locale,
        "PENNY sign-in was captured. You can return to the app even if the browser ended on a PENNY error or not-found page.",
        "Die PENNY-Anmeldung wurde erfasst. Sie können zur App zurückkehren, auch wenn der Browser auf einer PENNY-Fehler- oder Nicht-gefunden-Seite geendet hat."
      );
    }
    return byLocale(
      locale,
      "The sign-in was saved successfully.",
      "Die Anmeldung wurde erfolgreich gespeichert."
    );
  }
  if (status?.status === "failed") {
    if (connector.source_id === "dm_de") {
      return byLocale(
        locale,
        "The sign-in was not saved. If dm rejects the first attempt, start setup once more before assuming the connector is broken.",
        "Die Anmeldung wurde nicht gespeichert. Wenn dm den ersten Versuch ablehnt, starten Sie die Einrichtung bitte noch einmal, bevor Sie von einem Defekt ausgehen."
      );
    }
    return byLocale(
      locale,
      "The sign-in did not complete successfully. Start setup again to retry.",
      "Die Anmeldung wurde nicht erfolgreich abgeschlossen. Starten Sie die Einrichtung erneut, um es noch einmal zu versuchen."
    );
  }
  return latestLine;
}

function summarizeSyncStatus(latestLine: string | null, locale: SupportedLocale): string {
  if (!latestLine) {
    return byLocale(
      locale,
      "This connector is importing receipts in the background.",
      "Diese Anbindung importiert Belege gerade im Hintergrund."
    );
  }
  const stage = parseStageValue(latestLine, "stage");
  if (stage === "discovering") {
    const year = parseStageValue(latestLine, "year");
    const page = parseStageValue(latestLine, "page");
    const queued = parseStageValue(latestLine, "queued");
    return byLocale(
      locale,
      `Looking through ${year ?? "the selected"} orders page ${page ?? "?"}. ${queued ?? "0"} orders found so far.`,
      `Suche in ${year ?? "den gewählten"} Bestellungen, Seite ${page ?? "?"}. Bisher ${queued ?? "0"} Bestellungen gefunden.`
    );
  }
  if (stage === "processing") {
    const seen = parseStageValue(latestLine, "seen");
    const newReceipts = parseStageValue(latestLine, "new");
    return byLocale(
      locale,
      `Import in progress. ${seen ?? "0"} checked, ${newReceipts ?? "0"} new receipts saved.`,
      `Import läuft. ${seen ?? "0"} geprüft, ${newReceipts ?? "0"} neue Belege gespeichert.`
    );
  }
  if (stage === "refreshing_auth" || stage === "authenticating" || stage === "healthcheck") {
    return byLocale(
      locale,
      "Checking the saved sign-in before importing.",
      "Die gespeicherte Anmeldung wird vor dem Import geprüft."
    );
  }
  return latestLine;
}

export function ConnectorsPage() {
  const { t, tText, locale } = useI18n();
  const queryClient = useQueryClient();
  const [setupState, setSetupState] = useState<SetupState | null>(null);
  const [setupValues, setSetupValues] = useState<SetupValues>({});
  const [clearSecretKeys, setClearSecretKeys] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);
  const [packGuideState, setPackGuideState] = useState<PackGuideState | null>(null);
  const [highlightedPackId, setHighlightedPackId] = useState<string | null>(null);
  const [selectedLidlSourceId, setSelectedLidlSourceId] = useState<string>("lidl_plus_de");
  const [selectedAmazonSourceId, setSelectedAmazonSourceId] = useState<string>("amazon_de");
  const [pendingSyncStarts, setPendingSyncStarts] = useState<PendingSyncStartState>({});
  const [firstRunPrompts, setFirstRunPrompts] = useState<FirstRunPromptState>({});
  const [manualCallbackValues, setManualCallbackValues] = useState<ManualCallbackState>({});
  const [pendingConnectorCallbacks, setPendingConnectorCallbacks] = useState<PendingConnectorCallbackState>([]);
  const [browserPreference, setBrowserPreference] = useState<DesktopExternalBrowserPreferenceState | null>(null);
  const [authCompletionPrompt, setAuthCompletionPrompt] = useState<AuthCompletionPromptState | null>(null);

  const connectorsQuery = useQuery({
    queryKey: ["connectors"],
    queryFn: fetchConnectors,
    refetchInterval: (query) =>
      query.state.data?.connectors.some((connector) => connector.ui.status === "syncing") ? 2000 : false
  });

  const desktopContextQuery = useQuery({
    queryKey: ["desktop", "connectors", "context"],
    queryFn: async () => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        return {
          available: false,
          releaseMetadata: null,
          receiptPlugins: null
        };
      }
      const [releaseMetadata, receiptPlugins] = await Promise.all([
        bridge.getReleaseMetadata(),
        bridge.listReceiptPlugins()
      ]);
      return {
        available: true,
        releaseMetadata,
        receiptPlugins
      };
    }
  });

  const browserPreferenceQuery = useQuery({
    queryKey: ["desktop", "external-browser-preference"],
    queryFn: async () => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        return null;
      }
      return await bridge.getExternalBrowserPreference();
    },
    staleTime: Number.POSITIVE_INFINITY
  });

  useEffect(() => {
    if (browserPreferenceQuery.data !== undefined) {
      setBrowserPreference(browserPreferenceQuery.data);
    }
  }, [browserPreferenceQuery.data]);

  const setupConfigQuery = useQuery({
    queryKey: ["connectors", "config", setupState?.connector.source_id],
    queryFn: () => fetchConnectorConfig(setupState!.connector.source_id),
    enabled:
      setupState !== null &&
      (setupState.connector.actions.operator.configure || setupState.connector.config_state !== "not_required")
  });

  useEffect(() => {
    if (!setupConfigQuery.data) {
      setSetupValues({});
      setClearSecretKeys([]);
      return;
    }
    setSetupValues(initialSetupValues(setupConfigQuery.data));
    setClearSecretKeys([]);
  }, [setupConfigQuery.data]);

  useEffect(() => {
    if (!feedback?.dismissAfterMs) {
      return;
    }
    const timer = window.setTimeout(() => {
      setFeedback((current) => (current === feedback ? null : current));
    }, feedback.dismissAfterMs);
    return () => window.clearTimeout(timer);
  }, [feedback]);

  useEffect(() => {
    const activeStarts = Object.entries(pendingSyncStarts);
    if (activeStarts.length === 0) {
      return;
    }
    const now = Date.now();
    const nextExpiry = Math.min(...activeStarts.map(([, start]) => start.expiresAt));
    const delay = Math.max(nextExpiry - now, 0);
    const timer = window.setTimeout(() => {
      setPendingSyncStarts((current) =>
        Object.fromEntries(Object.entries(current).filter(([, start]) => start.expiresAt > Date.now()))
      );
    }, delay);
    return () => window.clearTimeout(timer);
  }, [pendingSyncStarts]);

  useEffect(() => {
    if (!connectorsQuery.data || Object.keys(pendingSyncStarts).length === 0) {
      return;
    }
    setPendingSyncStarts((current) => {
      let changed = false;
      const nextEntries = Object.entries(current).filter(([sourceId, pendingStart]) => {
        const connector = connectorsQuery.data?.connectors.find((item) => item.source_id === sourceId);
        if (!connector) {
          changed = true;
          return false;
        }
        const lastSyncedAtMs = connector.last_synced_at ? Date.parse(connector.last_synced_at) : Number.NaN;
        const latestSyncStatus = connector.advanced.latest_sync_status;
        const shouldKeep =
          connector.ui.status !== "syncing" &&
          latestSyncStatus !== "running" &&
          latestSyncStatus !== "failed" &&
          latestSyncStatus !== "canceled" &&
          !(Number.isFinite(lastSyncedAtMs) && lastSyncedAtMs >= pendingStart.startedAt - 1000);
        if (!shouldKeep) {
          changed = true;
        }
        return shouldKeep;
      });
      return changed ? Object.fromEntries(nextEntries) : current;
    });
  }, [connectorsQuery.data, pendingSyncStarts]);

  useEffect(() => {
    const activePrompts = Object.entries(firstRunPrompts);
    if (activePrompts.length === 0) {
      return;
    }
    const now = Date.now();
    const nextExpiry = Math.min(...activePrompts.map(([, prompt]) => prompt.expiresAt));
    const delay = Math.max(nextExpiry - now, 0);
    const timer = window.setTimeout(() => {
      setFirstRunPrompts((current) =>
        Object.fromEntries(Object.entries(current).filter(([, prompt]) => prompt.expiresAt > Date.now()))
      );
    }, delay);
    return () => window.clearTimeout(timer);
  }, [firstRunPrompts]);

  const bootstrapMutation = useMutation({
    mutationFn: (sourceId: string) => startConnectorBootstrap(sourceId),
    onSuccess: async (result, sourceId) => {
      if (isLidlConnector(sourceId) && result.remote_login_url) {
        try {
          await openExternalUrl(result.remote_login_url);
        } catch {
          // Keep the in-app fallback visible even if launching the browser fails.
        }
      }
      setFeedback({
        variant: "default",
        title: byLocale(locale, "Sign-in started", "Anmeldung gestartet"),
        message: t("pages.connectors.feedback.setupStarted", { name: sourceId }),
        dismissAfterMs: 15_000
      });
      queryClient.setQueryData(["connectors", "bootstrap-status", sourceId], result.bootstrap);
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["connectors", "bootstrap-status", sourceId] });
      await queryClient.invalidateQueries({ queryKey: ["connectors", "auth-status", sourceId] });
    },
    onError: (error, sourceId) => {
      const resolvedMessage = resolveApiErrorMessage(error, t, t("pages.connectors.startBootstrapErrorTitle"));
      const blockingSourceId = blockingBootstrapSourceId(resolvedMessage);
      const blockingConnector =
        blockingSourceId === null
          ? null
          : connectors.find((item) => item.source_id === blockingSourceId) ?? null;
      const blockingDisplayName =
        blockingConnector !== null
          ? connectorDisplayName(blockingConnector)
          : blockingSourceId;
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Sign-in failed", "Anmeldung fehlgeschlagen"),
        message:
          blockingSourceId !== null
            ? byLocale(
                locale,
                `Finish or stop ${blockingDisplayName} sign-in before starting ${sourceId}.`,
                `Schließen Sie zuerst die Anmeldung für ${blockingDisplayName} ab oder stoppen Sie sie, bevor Sie ${sourceId} starten.`
              )
            : resolvedMessage
      });
    }
  });

  const browserPreferenceMutation = useMutation({
    mutationFn: async (preferredBrowser: DesktopExternalBrowserId) => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        throw new Error("Desktop browser preference is unavailable in this build.");
      }
      return await bridge.setExternalBrowserPreference(preferredBrowser);
    },
    onSuccess: (result) => {
      setBrowserPreference(result);
      void queryClient.invalidateQueries({ queryKey: ["desktop", "external-browser-preference"] });
    },
    onError: (error) => {
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Browser preference failed", "Browser-Einstellung fehlgeschlagen"),
        message: String(error)
      });
    }
  });

  const syncMutation = useMutation({
    mutationFn: ({ sourceId, full }: { sourceId: string; full: boolean }) =>
      startConnectorSync(sourceId, full),
    onMutate: async ({ sourceId, full }) => {
      const now = Date.now();
      setPendingSyncStarts((current) => ({
        ...current,
        [sourceId]: {
          full,
          startedAt: now,
          expiresAt: now + OPTIMISTIC_SYNC_START_MS
        }
      }));
    },
    onSuccess: async (result, { sourceId, full }) => {
      queryClient.setQueryData(["global-connector-sync-status", sourceId], result.sync);
      setFeedback({
        variant: "default",
        title: full
          ? byLocale(locale, "Full import started", "Vollimport gestartet")
          : byLocale(locale, "Import started", "Import gestartet"),
        message: full
          ? t("pages.connectors.feedback.fullSyncStarted", { name: sourceId })
          : t("pages.connectors.feedback.syncStarted", { name: sourceId }),
        dismissAfterMs: 15_000
      });
      setFirstRunPrompts((current) => {
        if (!current[sourceId]) {
          return current;
        }
        const next = { ...current };
        delete next[sourceId];
        return next;
      });
      await queryClient.invalidateQueries({ queryKey: ["global-connector-sync-status", sourceId] });
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
    },
    onError: (error, { sourceId }) => {
      setPendingSyncStarts((current) => {
        if (!current[sourceId]) {
          return current;
        }
        const next = { ...current };
        delete next[sourceId];
        return next;
      });
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Import failed to start", "Import konnte nicht gestartet werden"),
        message: resolveApiErrorMessage(error, t, t("pages.connectors.startSyncErrorTitle"))
      });
    }
  });

  const reloadMutation = useMutation({
    mutationFn: reloadConnectors,
    onSuccess: async () => {
      setFeedback({
        variant: "default",
        title: byLocale(locale, "Connector list refreshed", "Anbindungsliste aktualisiert"),
        message: t("pages.connectors.feedback.registryReloaded"),
        dismissAfterMs: 15_000
      });
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Refresh failed", "Aktualisierung fehlgeschlagen"),
        message: resolveApiErrorMessage(error, t, t("pages.connectors.loadSourceErrorTitle"))
      });
    }
  });

  const installLocalPackMutation = useMutation({
    mutationFn: async () => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        throw new Error("Desktop pack management is unavailable in this build.");
      }
      return await bridge.installReceiptPluginFromDialog();
    },
    onSuccess: async (result) => {
      if (!result) {
        return;
      }
      setHighlightedPackId(result.pack.pluginId);
      setFeedback({
        variant: "default",
        title: byLocale(locale, "Connector imported", "Anbindung importiert"),
        message:
          result.pack.status === "disabled"
            ? byLocale(
                locale,
                `Imported ${result.pack.displayName}. Use the Enable connector button below to finish adding it.`,
                `${result.pack.displayName} wurde importiert. Aktivieren Sie die Anbindung unten, um sie fertig hinzuzufügen.`
              )
            : byLocale(
                locale,
                `Imported ${result.pack.displayName}. It is already active on this desktop.`,
                `${result.pack.displayName} wurde importiert und ist auf diesem Gerät bereits aktiv.`
              ),
        dismissAfterMs: 15_000
      });
      if (result.pack.status === "disabled") {
        setPackGuideState({
          pack: result.pack,
          catalogEntry: findCatalogEntryForPack(catalogEntries, result.pack),
          showEnableAction: true
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Import failed", "Import fehlgeschlagen"),
        message: byLocale(
          locale,
          `Could not import the local receipt pack. ${String(error)}`,
          `Das lokale Belegpaket konnte nicht importiert werden. ${String(error)}`
        )
      });
    }
  });

  const installCatalogPackMutation = useMutation({
    mutationFn: async (entryId: string) => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        throw new Error("Desktop pack management is unavailable in this build.");
      }
      return await bridge.installReceiptPluginFromCatalogEntry({ entryId });
    },
    onSuccess: async (result) => {
      setHighlightedPackId(result.pack.pluginId);
      setFeedback({
        variant: "default",
        title: byLocale(locale, "Connector installed", "Anbindung installiert"),
        message:
          result.pack.status === "disabled"
            ? byLocale(
                locale,
                `Installed ${result.pack.displayName}. Use the Enable connector button below to finish adding it.`,
                `${result.pack.displayName} wurde installiert. Aktivieren Sie die Anbindung unten, um sie fertig hinzuzufügen.`
              )
            : byLocale(
                locale,
                `Installed ${result.pack.displayName} from the trusted catalog.`,
                `${result.pack.displayName} wurde aus dem vertrauenswürdigen Katalog installiert.`
              ),
        dismissAfterMs: 15_000
      });
      if (result.pack.status === "disabled") {
        setPackGuideState({
          pack: result.pack,
          catalogEntry: findCatalogEntryForPack(catalogEntries, result.pack),
          showEnableAction: true
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Installation failed", "Installation fehlgeschlagen"),
        message: byLocale(
          locale,
          `Could not install the trusted receipt pack. ${String(error)}`,
          `Das vertrauenswürdige Belegpaket konnte nicht installiert werden. ${String(error)}`
        )
      });
    }
  });

  const togglePackMutation = useMutation({
    mutationFn: async ({ pluginId, enabled }: { pluginId: string; enabled: boolean }) => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        throw new Error("Desktop pack management is unavailable in this build.");
      }
      return enabled ? await bridge.enableReceiptPlugin(pluginId) : await bridge.disableReceiptPlugin(pluginId);
    },
    onSuccess: async (result, variables) => {
      setFeedback({
        variant: "default",
        title: variables.enabled
          ? byLocale(locale, "Connector enabled", "Anbindung aktiviert")
          : byLocale(locale, "Connector disabled", "Anbindung deaktiviert"),
        message: variables.enabled
          ? result.pack.sourceId === "rewe_de"
            ? byLocale(
                locale,
                `${result.pack.displayName} is turned on. Next, open Chrome, sign into REWE there, leave the REWE tab open, and use Set up.`,
                `${result.pack.displayName} ist jetzt aktiv. Öffnen Sie als Nächstes Chrome, melden Sie sich dort bei REWE an, lassen Sie den REWE-Tab offen und nutzen Sie dann Einrichten.`
              )
            : byLocale(
                locale,
                `${result.pack.displayName} is turned on. Next, use Set up to sign in if the connector asks for it.`,
                `${result.pack.displayName} ist jetzt aktiv. Nutzen Sie als Nächstes Einrichten, falls die Anbindung eine Anmeldung benötigt.`
              )
          : byLocale(
              locale,
              `${result.pack.displayName} is turned off on this computer.`,
              `${result.pack.displayName} ist auf diesem Gerät jetzt deaktiviert.`
            ),
        dismissAfterMs: 15_000
      });
      if (variables.enabled) {
        setHighlightedPackId(result.pack.pluginId);
      }
      setPackGuideState((current) => (current?.pack.pluginId === result.pack.pluginId ? null : current));
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
      await Promise.all([connectorsQuery.refetch(), desktopContextQuery.refetch()]);
    },
    onError: (error) => {
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Update failed", "Aktualisierung fehlgeschlagen"),
        message: byLocale(
          locale,
          `Could not update the receipt pack state. ${String(error)}`,
          `Der Status des Belegpakets konnte nicht aktualisiert werden. ${String(error)}`
        )
      });
    }
  });

  const uninstallPackMutation = useMutation({
    mutationFn: async (pluginId: string) => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        throw new Error("Desktop pack management is unavailable in this build.");
      }
      return await bridge.uninstallReceiptPlugin(pluginId);
    },
    onSuccess: async (_result, pluginId) => {
      setFeedback({
        variant: "default",
        title: byLocale(locale, "Connector removed", "Anbindung entfernt"),
        message: byLocale(
          locale,
          `Removed ${pluginId} from desktop storage.`,
          `${pluginId} wurde aus dem Desktop-Speicher entfernt.`
        ),
        dismissAfterMs: 15_000
      });
      setHighlightedPackId((current) => (current === pluginId ? null : current));
      setPackGuideState((current) => (current?.pack.pluginId === pluginId ? null : current));
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Removal failed", "Entfernen fehlgeschlagen"),
        message: byLocale(
          locale,
          `Could not remove the receipt pack. ${String(error)}`,
          `Das Belegpaket konnte nicht entfernt werden. ${String(error)}`
        )
      });
    }
  });

  const configMutation = useMutation({
    mutationFn: ({
      sourceId,
      payload
    }: {
      sourceId: string;
      payload: {
        values: Record<string, string | number | boolean | null>;
        clear_secret_keys?: string[];
      };
    }) => submitConnectorConfig(sourceId, payload),
    onSuccess: async (_result, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["connectors", "config", variables.sourceId] });
    },
    onError: (error) => {
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Settings failed", "Einstellungen fehlgeschlagen"),
        message: resolveApiErrorMessage(error, t, t("pages.connectors.loadSourceErrorTitle"))
      });
    }
  });
  const cancelBootstrapMutation = useMutation({
    mutationFn: (sourceId: string) => cancelConnectorBootstrap(sourceId),
    onSuccess: async (_result, sourceId) => {
      setFeedback({
        variant: "default",
        title: byLocale(locale, "Sign-in canceled", "Anmeldung abgebrochen"),
        message: t("pages.connectors.action.bootstrapCanceled", { sourceId }),
        dismissAfterMs: 15_000
      });
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["connectors", "bootstrap-status", sourceId] });
      await queryClient.invalidateQueries({ queryKey: ["connectors", "auth-status", sourceId] });
    },
    onError: (error) => {
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Cancel failed", "Abbrechen fehlgeschlagen"),
        message: resolveApiErrorMessage(error, t, "Failed to cancel connector bootstrap")
      });
    }
  });

  const confirmBootstrapMutation = useMutation({
    mutationFn: ({ sourceId, callbackUrl }: { sourceId: string; callbackUrl: string }) =>
      confirmConnectorBootstrap(sourceId, callbackUrl),
    onSuccess: async (result, variables) => {
      setManualCallbackValues((current) => {
        const next = { ...current };
        delete next[variables.sourceId];
        return next;
      });
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["connectors", "bootstrap-status", variables.sourceId] });
      await queryClient.invalidateQueries({ queryKey: ["connectors", "auth-status", variables.sourceId] });
      activatePostAuthPrompt(
        variables.sourceId,
        isPennyConnector(variables.sourceId)
          ? byLocale(
              locale,
              "PENNY sign-in was captured from the callback URL. If the browser ended on a PENNY redirect or not-found page, you can ignore it and continue here.",
              "Die PENNY-Anmeldung wurde aus der Callback-URL erfasst. Wenn der Browser auf einer PENNY-Weiterleitungs- oder Nicht-gefunden-Seite geendet hat, können Sie das ignorieren und hier fortfahren."
            )
          : result.auth_status.detail ??
              byLocale(locale, "The sign-in was captured successfully.", "Die Anmeldung wurde erfolgreich erfasst."),
        {
          showModal: isLidlConnector(variables.sourceId)
        }
      );
    },
    onError: (error) => {
      setFeedback({
        variant: "destructive",
        title: byLocale(locale, "Sign-in could not be confirmed", "Anmeldung konnte nicht bestätigt werden"),
        message: resolveApiErrorMessage(error, t, "Failed to confirm connector bootstrap")
      });
    }
  });

  const connectors = connectorsQuery.data?.connectors ?? [];
  const viewerIsAdmin = Boolean(connectorsQuery.data?.viewer.is_admin);
  const visibleConnectors = useMemo(
    () =>
      connectors.filter((connector) => {
        if (connector.ui.visibility !== "default") {
          return false;
        }
        if (connector.install_state !== "installed") {
          return false;
        }
        if (connector.install_origin === "builtin") {
          return isDesktopBundledBuiltinConnector(connector.source_id);
        }
        return true;
      }),
    [connectors]
  );
  const bootstrapCapableConnectors = useMemo(
    () => visibleConnectors.filter((connector) => connector.supports_bootstrap),
    [visibleConnectors]
  );
  const connectorBootstrapQueries = useQueries({
    queries: bootstrapCapableConnectors.map((connector) => ({
      queryKey: ["connectors", "bootstrap-status", connector.source_id],
      queryFn: () => fetchConnectorBootstrapStatus(connector.source_id),
      refetchInterval: (query: { state: { data?: ConnectorBootstrapStatus } }) =>
        query.state.data?.status === "running" ? 1500 : false,
      retry: false
    }))
  });
  const bootstrapStatusBySourceId = useMemo(
    () =>
      new Map(
        connectorBootstrapQueries.flatMap((query, index) =>
          query.status === "success" && query.data
            ? [[bootstrapCapableConnectors[index]?.source_id ?? query.data.source_id, query.data] as const]
            : []
        )
      ),
    [bootstrapCapableConnectors, connectorBootstrapQueries]
  );
  const connectorAuthStatusQueries = useQueries({
    queries: bootstrapCapableConnectors.map((connector) => ({
      queryKey: ["connectors", "auth-status", connector.source_id],
      queryFn: () => fetchConnectorAuthStatus(connector.source_id, { validateSession: false }),
      refetchInterval: (query: { state: { data?: ConnectorAuthStatus } }) =>
        query.state.data?.bootstrap?.status === "running" ? 1500 : false,
      retry: false
    }))
  });
  const authStatusBySourceId = useMemo(
    () =>
      new Map(
        connectorAuthStatusQueries.flatMap((query, index) =>
          query.status === "success" && query.data
            ? [[bootstrapCapableConnectors[index]?.source_id ?? query.data.source_id, query.data] as const]
            : []
        )
      ),
    [bootstrapCapableConnectors, connectorAuthStatusQueries]
  );
  const catalogEntries = desktopContextQuery.data?.releaseMetadata?.discovery_catalog.entries ?? [];
  const receiptPlugins = desktopContextQuery.data?.receiptPlugins?.packs ?? [];
  const desktopBridgeAvailable = desktopContextQuery.data?.available ?? false;
  const curatedDesktopPackEntries = useMemo(
    () => catalogEntries.filter((entry) => entry.entry_type === "desktop_pack"),
    [catalogEntries]
  );

  const packBySourceId = useMemo(
    () => new Map(receiptPlugins.map((pack) => [pack.sourceId, pack])),
    [receiptPlugins]
  );
  const connectorCards = useMemo(
    () =>
      visibleConnectors.map((connector) => {
        const pack = packBySourceId.get(connector.source_id) ?? null;
        const catalogEntry = findCatalogEntry(catalogEntries, connector, pack);
        return { connector, pack, catalogEntry };
      }),
    [catalogEntries, packBySourceId, visibleConnectors]
  );

  const enabledConnectorSourceIds = useMemo(
    () =>
      new Set(
        visibleConnectors
          .filter((connector) => connector.enable_state === "enabled")
          .map((connector) => connector.source_id)
      ),
    [visibleConnectors]
  );

  const pendingActivationPacks = useMemo(
    () =>
      receiptPlugins.filter(
        (pack) => pack.status === "disabled" && !enabledConnectorSourceIds.has(pack.sourceId)
      ),
    [enabledConnectorSourceIds, receiptPlugins]
  );

  const pendingActivationPluginIds = useMemo(
    () => new Set(pendingActivationPacks.map((pack) => pack.pluginId)),
    [pendingActivationPacks]
  );

  const visibleConnectorCards = useMemo(
    () =>
      connectorCards.filter(
        ({ pack }) => !(pack && pendingActivationPluginIds.has(pack.pluginId))
      ),
    [connectorCards, pendingActivationPluginIds]
  );

  const amazonConnectorCards = useMemo(
    () =>
      visibleConnectorCards
        .filter(({ connector }) => isAmazonConnector(connector.source_id))
        .sort(
          (left, right) =>
            connectorSortOrder(left.connector.source_id) -
            connectorSortOrder(right.connector.source_id)
        ),
    [visibleConnectorCards]
  );

  const lidlConnectorCards = useMemo(
    () =>
      visibleConnectorCards
        .filter(({ connector }) => isLidlConnector(connector.source_id))
        .sort(
          (left, right) =>
            connectorSortOrder(left.connector.source_id) -
            connectorSortOrder(right.connector.source_id)
        ),
    [visibleConnectorCards]
  );

  const nonAmazonConnectorCards = useMemo(
    () =>
      visibleConnectorCards.filter(
        ({ connector }) => !isAmazonConnector(connector.source_id) && !isLidlConnector(connector.source_id)
      ),
    [visibleConnectorCards]
  );

  useEffect(() => {
    if (lidlConnectorCards.length === 0) {
      return;
    }
    const currentSelectionStillExists = lidlConnectorCards.some(
      ({ connector }) => connector.source_id === selectedLidlSourceId
    );
    if (currentSelectionStillExists) {
      return;
    }
    const preferredConnector =
      lidlConnectorCards.find(({ connector }) => connector.ui.status === "syncing") ??
      lidlConnectorCards.find(({ connector }) => connector.actions.primary.kind === "reconnect") ??
      lidlConnectorCards.find(({ connector }) => connector.source_id === "lidl_plus_de") ??
      lidlConnectorCards[0];
    if (preferredConnector) {
      setSelectedLidlSourceId(preferredConnector.connector.source_id);
    }
  }, [lidlConnectorCards, selectedLidlSourceId]);

  useEffect(() => {
    if (amazonConnectorCards.length === 0) {
      return;
    }
    const currentSelectionStillExists = amazonConnectorCards.some(
      ({ connector }) => connector.source_id === selectedAmazonSourceId
    );
    if (currentSelectionStillExists) {
      return;
    }
    const preferredConnector =
      amazonConnectorCards.find(({ connector }) => connector.ui.status === "syncing") ??
      amazonConnectorCards.find(({ connector }) => connector.actions.primary.kind === "reconnect") ??
      amazonConnectorCards.find(({ connector }) => connector.source_id === "amazon_de") ??
      amazonConnectorCards[0];
    if (preferredConnector) {
      setSelectedAmazonSourceId(preferredConnector.connector.source_id);
    }
  }, [amazonConnectorCards, selectedAmazonSourceId]);

  const selectedLidlCard = useMemo(
    () =>
      lidlConnectorCards.find(({ connector }) => connector.source_id === selectedLidlSourceId) ??
      lidlConnectorCards[0] ??
      null,
    [lidlConnectorCards, selectedLidlSourceId]
  );

  const selectedAmazonCard = useMemo(
    () =>
      amazonConnectorCards.find(({ connector }) => connector.source_id === selectedAmazonSourceId) ??
      amazonConnectorCards[0] ??
      null,
    [amazonConnectorCards, selectedAmazonSourceId]
  );

  const attentionPacks = useMemo(
    () =>
      receiptPlugins.filter(
        (pack) =>
          pack.status !== "enabled" &&
          pack.status !== "disabled" &&
          connectorCards.some((item) => item.pack?.pluginId === pack.pluginId) === false
      ),
    [connectorCards, receiptPlugins]
  );

  const setupDialogFields = useMemo(() => {
    if (!setupConfigQuery.data || !setupState) {
      return [];
    }
    return fieldsForSetupMode(setupConfigQuery.data.fields, setupState.mode).map((field) =>
      localizeConnectorConfigField(field, setupState.connector.source_id, locale)
    );
  }, [locale, setupConfigQuery.data, setupState]);

  const connectorsError = connectorsQuery.error
    ? resolveApiErrorMessage(connectorsQuery.error, t, t("pages.connectors.loadSourceErrorTitle"))
    : null;
  const handledBootstrapCompletionsRef = useRef<Set<string>>(new Set());
  const previousSyncStatusRef = useRef<Map<string, string>>(new Map());
  const seenConnectorCallbackKeysRef = useRef<Set<string>>(new Set());
  const processingConnectorCallbackRef = useRef(false);

  function activatePostAuthPrompt(
    sourceId: string,
    detail: string | null,
    options?: { showModal?: boolean }
  ): void {
    const now = Date.now();
    setFirstRunPrompts((current) => ({
      ...current,
      [sourceId]: {
        activatedAt: now,
        expiresAt: now + SHORT_SUCCESS_DISMISS_MS
      }
    }));
    if (options?.showModal) {
      setAuthCompletionPrompt({
        sourceId,
        confirmedAt: now,
        detail
      });
    }
    setFeedback({
      variant: "default",
      title: byLocale(locale, "Sign-in complete", "Anmeldung abgeschlossen"),
      message: isLidlConnector(sourceId)
        ? byLocale(
            locale,
            "Lidl sign-in was saved. The browser may still show the code page. That is normal.",
            "Die Lidl-Anmeldung wurde gespeichert. Der Browser kann weiterhin die Code-Seite zeigen. Das ist normal."
          )
        : detail ??
          byLocale(
            locale,
            "Your sign-in was saved successfully.",
            "Ihre Anmeldung wurde erfolgreich gespeichert."
          ),
      dismissAfterMs: SHORT_SUCCESS_DISMISS_MS
    });
  }

  useEffect(() => {
    const bridge = getDesktopConnectorBridge();
    if (!bridge) {
      return;
    }
    let canceled = false;
    const appendCallbacks = (events: DesktopConnectorCallbackEvent[]): void => {
      if (events.length === 0 || canceled) {
        return;
      }
      setPendingConnectorCallbacks((current) => {
        const next = [...current];
        for (const event of events) {
          const normalizedUrl = String(event.url ?? "").trim();
          if (!normalizedUrl) {
            continue;
          }
          const normalizedEvent: DesktopConnectorCallbackEvent = {
            url: normalizedUrl,
            sourceId: typeof event.sourceId === "string" && event.sourceId.trim().length > 0 ? event.sourceId : null,
            confirmed: event.confirmed === true,
            confirmedAt: typeof event.confirmedAt === "string" ? event.confirmedAt : null,
            detail: typeof event.detail === "string" ? event.detail : null
          };
          const eventKey = connectorCallbackEventKey(normalizedEvent);
          if (seenConnectorCallbackKeysRef.current.has(eventKey)) {
            continue;
          }
          seenConnectorCallbackKeysRef.current.add(eventKey);
          next.push(normalizedEvent);
        }
        return next;
      });
    };

    void bridge.consumePendingConnectorCallbacks().then((events) => {
      appendCallbacks(events);
    });
    const unsubscribe = bridge.onConnectorCallback((event) => {
      appendCallbacks([event]);
    });
    return () => {
      canceled = true;
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (pendingConnectorCallbacks.length === 0 || processingConnectorCallbackRef.current) {
      return;
    }
    const [nextCallback] = pendingConnectorCallbacks;
    if (!nextCallback) {
      return;
    }
    if (nextCallback.confirmed) {
      const sourceId =
        typeof nextCallback.sourceId === "string" && nextCallback.sourceId.trim().length > 0
          ? nextCallback.sourceId
          : resolveManualCallbackSourceId(
              nextCallback.url,
              authStatusBySourceId,
              selectedLidlSourceId
            );
      if (!sourceId) {
        return;
      }
      processingConnectorCallbackRef.current = true;
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["connectors"] }),
        queryClient.invalidateQueries({ queryKey: ["connectors", "bootstrap-status", sourceId] }),
        queryClient.invalidateQueries({ queryKey: ["connectors", "auth-status", sourceId] })
      ]).finally(() => {
        activatePostAuthPrompt(sourceId, nextCallback.detail ?? null, {
          showModal: isLidlConnector(sourceId)
        });
        processingConnectorCallbackRef.current = false;
        setPendingConnectorCallbacks((current) => current.filter((item) => item !== nextCallback));
      });
      return;
    }
    const sourceId = resolveManualCallbackSourceId(
      nextCallback.url,
      authStatusBySourceId,
      selectedLidlSourceId
    );
    if (!sourceId) {
      return;
    }

    processingConnectorCallbackRef.current = true;
    void confirmBootstrapMutation
      .mutateAsync({
        sourceId,
        callbackUrl: nextCallback.url
      })
      .finally(() => {
        processingConnectorCallbackRef.current = false;
        setPendingConnectorCallbacks((current) => current.filter((item) => item.url !== nextCallback.url));
      });
  }, [
    activatePostAuthPrompt,
    authStatusBySourceId,
    confirmBootstrapMutation,
    pendingConnectorCallbacks,
    queryClient,
    selectedLidlSourceId
  ]);

  useEffect(() => {
    for (const [sourceId, status] of bootstrapStatusBySourceId.entries()) {
      if ((status.status !== "succeeded" && status.status !== "failed") || !status.finished_at) {
        continue;
      }
      const completionKey = `${sourceId}:${status.status}:${status.finished_at}`;
      if (handledBootstrapCompletionsRef.current.has(completionKey)) {
        continue;
      }
      handledBootstrapCompletionsRef.current.add(completionKey);
      if (status.status === "succeeded") {
        const connector = connectors.find((item) => item.source_id === sourceId) ?? null;
        if (connector && connector.supports_sync && !connector.last_synced_at) {
          activatePostAuthPrompt(
            sourceId,
            isPennyConnector(sourceId)
              ? byLocale(
                  locale,
                  "PENNY sign-in was captured successfully. If the browser ended on a PENNY redirect or not-found page, you can ignore it and continue here with the first import.",
                  "Die PENNY-Anmeldung wurde erfolgreich erfasst. Wenn der Browser auf einer PENNY-Weiterleitungs- oder Nicht-gefunden-Seite geendet hat, können Sie das ignorieren und hier mit dem ersten Import fortfahren."
                )
              : byLocale(
                  locale,
                  "Your sign-in was saved. Next, either import new receipts or run the one-time full history import.",
                  "Ihre Anmeldung wurde gespeichert. Als Nächstes können Sie entweder neue Belege importieren oder einmalig die gesamte Historie laden."
                ),
            {
              showModal: false
            }
          );
        }
      }
      if (status.status === "succeeded" || status.status === "failed") {
        void queryClient.invalidateQueries({ queryKey: ["connectors"] });
      }
    }
  }, [activatePostAuthPrompt, bootstrapStatusBySourceId, connectors, locale, queryClient]);

  useEffect(() => {
    for (const connector of connectors) {
      const currentStatus = connector.advanced.latest_sync_status;
      const previousStatus = previousSyncStatusRef.current.get(connector.source_id);
      previousSyncStatusRef.current.set(connector.source_id, currentStatus);
      if (previousStatus !== "running") {
        continue;
      }
      if (currentStatus === "succeeded") {
        setFirstRunPrompts((current) => {
          if (!current[connector.source_id]) {
            return current;
          }
          const next = { ...current };
          delete next[connector.source_id];
          return next;
        });
        setFeedback({
          variant: "default",
          title: byLocale(locale, "Import finished", "Import abgeschlossen"),
          message: byLocale(
            locale,
            `${connectorDisplayName(connector)} finished importing successfully. This message will disappear automatically.`,
            `${connectorDisplayName(connector)} hat den Import erfolgreich abgeschlossen. Diese Meldung verschwindet automatisch.`
          ),
          dismissAfterMs: SHORT_SUCCESS_DISMISS_MS
        });
      } else if (currentStatus === "failed" || currentStatus === "canceled") {
        setFeedback({
          variant: "destructive",
          title:
            currentStatus === "canceled"
              ? byLocale(locale, "Import canceled", "Import abgebrochen")
              : byLocale(locale, "Import failed", "Import fehlgeschlagen"),
          message:
            connector.last_sync_summary ||
            connector.status_detail ||
            byLocale(
              locale,
              "The import did not finish successfully.",
              "Der Import wurde nicht erfolgreich abgeschlossen."
            )
        });
      }
    }
  }, [connectors, locale]);

  async function openSetup(connector: ConnectorDiscoveryRow, mode: SetupState["mode"]): Promise<void> {
    setFeedback(null);
    if (mode !== "configure" && connector.config_state === "not_required" && !connector.actions.operator.configure) {
      await bootstrapMutation.mutateAsync(connector.source_id);
      return;
    }
    setSetupState({ connector, mode });
  }

  function closeSetup(): void {
    setSetupState(null);
    setSetupValues({});
    setClearSecretKeys([]);
  }

  function updateManualCallbackValue(sourceId: string, value: string): void {
    setManualCallbackValues((current) => ({ ...current, [sourceId]: value }));
  }

  function openPackGuide(pack: DesktopReceiptPluginPackInfo, showEnableAction: boolean): void {
    setPackGuideState({
      pack,
      catalogEntry: findCatalogEntryForPack(catalogEntries, pack),
      showEnableAction
    });
  }

  async function handlePrimaryAction(
    connector: ConnectorDiscoveryRow,
    kind: ConnectorPrimaryActionKind,
    enabled: boolean
  ): Promise<void> {
    if (!kind || !enabled) {
      return;
    }
    if (kind === "set_up") {
      await openSetup(connector, "setup");
      return;
    }
    if (kind === "reconnect") {
      await openSetup(connector, "reconnect");
      return;
    }
    if (kind === "sync_now") {
      const authStatus = await fetchConnectorAuthStatus(connector.source_id);
      if (
        authStatus.state === "not_connected" ||
        authStatus.state === "reauth_required" ||
        authStatus.state === "auth_failed"
      ) {
        await queryClient.invalidateQueries({ queryKey: ["connectors"] });
        setFeedback({
          variant: "default",
          title: byLocale(locale, "Sign-in required", "Anmeldung erforderlich"),
          message:
            isReweConnector(connector.source_id)
              ? authStatus.state === "reauth_required" || authStatus.state === "auth_failed"
                ? byLocale(
                    locale,
                    "REWE needs a fresh Chrome session. Open Chrome, sign into REWE again, leave the tab open, then retry setup.",
                    "REWE braucht eine frische Chrome-Sitzung. Öffnen Sie Chrome, melden Sie sich erneut bei REWE an, lassen Sie den Tab offen und starten Sie dann die Einrichtung erneut."
                  )
                : byLocale(
                    locale,
                    "Before the first REWE import, open Chrome, sign into REWE there, leave the tab open, and then continue setup.",
                    "Vor dem ersten REWE-Import öffnen Sie Chrome, melden sich dort bei REWE an, lassen den Tab offen und fahren dann mit der Einrichtung fort."
                  )
              : authStatus.state === "reauth_required" || authStatus.state === "auth_failed"
              ? byLocale(
                  locale,
                  "Saved sign-in expired. Please sign in again.",
                  "Die gespeicherte Anmeldung ist abgelaufen. Bitte erneut anmelden."
                )
              : byLocale(
                  locale,
                  "Please sign in before the first import.",
                  "Bitte melden Sie sich vor dem ersten Import an."
                ),
          dismissAfterMs: 15_000
        });
        await openSetup(
          connector,
          authStatus.state === "not_connected" ? "setup" : "reconnect"
        );
        return;
      }
      await syncMutation.mutateAsync({ sourceId: connector.source_id, full: false });
      return;
    }
    if (kind === "open_source" && connector.actions.secondary.href) {
      return;
    }
  }

  async function handleSaveSetup(): Promise<void> {
    if (!setupState) {
      return;
    }
    const config = setupConfigQuery.data;
    const connector = setupState.connector;
    if (config) {
      const payload = buildConfigPayload(config, setupDialogFields, setupValues, clearSecretKeys);
      await configMutation.mutateAsync({
        sourceId: connector.source_id,
        payload
      });
    }

    if (setupState.mode !== "configure") {
      await bootstrapMutation.mutateAsync(connector.source_id);
    } else {
      setFeedback({
        variant: "default",
        title: byLocale(locale, "Settings saved", "Einstellungen gespeichert"),
        message: t("pages.connectors.feedback.settingsSaved", { name: connector.display_name }),
        dismissAfterMs: 15_000
      });
    }
    closeSetup();
  }

  async function handleGuidePrimaryAction(): Promise<void> {
    if (!packGuideState?.showEnableAction) {
      setPackGuideState(null);
      return;
    }
    await togglePackMutation.mutateAsync({ pluginId: packGuideState.pack.pluginId, enabled: true });
  }

  const renderConnectorCard = (
    {
      connector,
      pack,
      catalogEntry
    }: {
      connector: ConnectorDiscoveryRow;
      pack: DesktopReceiptPluginPackInfo | null;
      catalogEntry: DesktopConnectorCatalogEntry | null;
    },
    options?: {
      key?: string;
      title?: string;
      headerExtra?: ReactNode;
    }
  ) => {
    const updateAvailable =
      pack !== null &&
      catalogEntry?.current_version &&
      compareVersions(pack.version, catalogEntry.current_version) < 0;
    const displayName = options?.title ?? connectorDisplayName(connector);
    const bootstrapStatus = bootstrapStatusBySourceId.get(connector.source_id) ?? null;
    const authStatus = authStatusBySourceId.get(connector.source_id) ?? null;
    const pendingSyncStart = pendingSyncStarts[connector.source_id] ?? null;
    const latestSyncStatus = connector.advanced.latest_sync_status;
    const latestSyncFailed = latestSyncStatus === "failed" || latestSyncStatus === "canceled";
    const optimisticSyncStarting =
      pendingSyncStart !== null &&
      connector.ui.status !== "syncing" &&
      latestSyncStatus !== "running" &&
      !latestSyncFailed;
    const firstRunPrompt = firstRunPrompts[connector.source_id];
    const firstRunPromptActive = Boolean(firstRunPrompt && firstRunPrompt.expiresAt > Date.now());
    const rawTaskState = connectorTaskState(connector);
    const normalizedTaskState = rawTaskState;
    const taskState = optimisticSyncStarting ? "syncing" : normalizedTaskState;
    const primaryKind = primaryActionKind(connector, taskState, firstRunPromptActive);
    const otherRunningBootstrap = Array.from(bootstrapStatusBySourceId.entries()).find(
      ([otherSourceId, status]) =>
        otherSourceId !== connector.source_id && status.status === "running"
    ) ?? null;
    const blockingConnector =
      otherRunningBootstrap === null
        ? null
        : connectors.find((item) => item.source_id === otherRunningBootstrap[0]) ?? null;
    const blockingDisplayName =
      blockingConnector !== null
        ? connectorDisplayName(blockingConnector)
        : otherRunningBootstrap?.[0] ?? null;
    const blockedByOtherBootstrap =
      otherRunningBootstrap !== null && (primaryKind === "set_up" || primaryKind === "reconnect");
    const primaryEnabled =
      primaryKind === "sync_now"
        ? connector.enable_state === "enabled"
        : primaryKind === "set_up" && bootstrapStatus?.status === "running"
          ? false
          : connector.actions.primary.enabled || primaryKind === "set_up";
    const bootstrapLines = bootstrapStatus?.output_tail ?? [];
    const bootstrapLatestLine =
      bootstrapLines.length > 0 ? bootstrapLines[bootstrapLines.length - 1] ?? null : null;
    const manualAuthStartUrl =
      typeof authStatus?.metadata?.auth_start_url === "string" ? authStatus.metadata.auth_start_url : null;
    const manualCallbackSupported = authStatus?.metadata?.manual_callback_supported === true;
    const manualCallbackValue = manualCallbackValues[connector.source_id] ?? "";
    const canSubmitManualCallback =
      manualCallbackSupported &&
      bootstrapStatus?.status === "running" &&
      manualCallbackValue.trim().length > 0 &&
      !confirmBootstrapMutation.isPending;
    const showBootstrapStatus = shouldShowBootstrapStatus(connector, bootstrapStatus);
    const syncLines = viewerIsAdmin ? connector.advanced.latest_sync_output : [];
    const latestSyncLine = syncLines.length > 0 ? syncLines[syncLines.length - 1] ?? null : null;
    const showSyncStatus = connector.ui.status === "syncing" || optimisticSyncStarting || latestSyncFailed;
    const secondarySummary = connectorSecondarySummary(connector, pack, locale);
    const showFirstRunActions =
      firstRunPromptActive &&
      connector.supports_sync &&
      connector.enable_state === "enabled" &&
      connectorHasDurableAuthState(connector);
    const effectivePrimaryKind: ConnectorPrimaryActionKind = showFirstRunActions ? "sync_now" : primaryKind;
    const effectivePrimaryEnabled = showFirstRunActions ? true : primaryEnabled && !blockedByOtherBootstrap;
    const statusSummary = showFirstRunActions
      ? byLocale(
          locale,
          isLidlConnector(connector.source_id)
            ? "Your Lidl sign-in is saved. The browser may still show the code page. Choose the normal import or the one-time full history import next."
            : "Your sign-in is saved. Choose the normal import or the one-time full history import next.",
          isLidlConnector(connector.source_id)
            ? "Ihre Lidl-Anmeldung ist gespeichert. Der Browser kann weiterhin die Code-Seite zeigen. Wählen Sie jetzt entweder den normalen Import oder einmalig die gesamte Historie."
            : "Ihre Anmeldung ist gespeichert. Wählen Sie jetzt entweder den normalen Import oder einmalig die gesamte Historie."
        )
      : optimisticSyncStarting
        ? byLocale(
            locale,
            "The import is starting. Live progress should appear here in a moment.",
            "Der Import wird gestartet. Gleich sollte hier der Live-Fortschritt erscheinen."
          )
      : blockedByOtherBootstrap
        ? byLocale(
            locale,
            `Finish or stop ${blockingDisplayName} sign-in first.`,
            `Schließen Sie zuerst die Anmeldung für ${blockingDisplayName} ab oder stoppen Sie sie.`
          )
      : connectorStatusSummary(connector, pack, displayName, locale);
    const bootstrapTitle =
      bootstrapStatus?.status === "running"
        ? byLocale(locale, "Sign-in in progress", "Anmeldung läuft")
        : bootstrapStatus?.status === "failed"
          ? byLocale(locale, "Sign-in failed", "Anmeldung fehlgeschlagen")
          : bootstrapStatus?.status === "succeeded"
            ? byLocale(locale, "Sign-in complete", "Anmeldung abgeschlossen")
            : byLocale(locale, "Sign-in", "Anmeldung");
    const bootstrapSummary = summarizeBootstrapStatus(
      connector.source_id,
      bootstrapStatus,
      bootstrapLatestLine,
      connector,
      locale
    );
    const syncSummary = latestSyncFailed
      ? summarizeSyncStatus(latestSyncLine, locale) ||
        byLocale(
          locale,
          "The import stopped before it could finish. Sign in again, then retry the import.",
          "Der Import wurde vor dem Abschluss gestoppt. Melden Sie sich erneut an und versuchen Sie den Import danach noch einmal."
        )
      : optimisticSyncStarting
      ? byLocale(
          locale,
          "The import was accepted and is being prepared in the background. The first live update can take a few seconds.",
          "Der Import wurde angenommen und wird im Hintergrund vorbereitet. Das erste Live-Update kann ein paar Sekunden dauern."
        )
      : summarizeSyncStatus(latestSyncLine, locale);
    const primaryButtonBusy =
      (bootstrapMutation.isPending && bootstrapMutation.variables === connector.source_id) ||
      (syncMutation.isPending && syncMutation.variables?.sourceId === connector.source_id) ||
      optimisticSyncStarting;
    const primaryButtonLabel =
      optimisticSyncStarting && effectivePrimaryKind === "sync_now"
        ? byLocale(locale, "Starting import…", "Import wird gestartet…")
        : primaryActionLabel(effectivePrimaryKind, taskState, locale);

    return (
      <Card key={options?.key ?? connector.source_id} className="border-border/60 bg-card/85 shadow-sm">
        <CardHeader className="space-y-3 border-b border-border/50 bg-background/30">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle className="text-lg">{displayName}</CardTitle>
              <CardDescription>{statusSummary}</CardDescription>
              {options?.headerExtra ? <div className="pt-2">{options.headerExtra}</div> : null}
            </div>
            <Badge>{connectorStatusLabel(taskState, locale)}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {secondarySummary ? <p className="text-sm text-muted-foreground">{secondarySummary}</p> : null}
          {connector.last_sync_summary ? (
            <p className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">{byLocale(locale, "Last result:", "Letztes Ergebnis:")}</span>{" "}
              {tText(connector.last_sync_summary)}
            </p>
          ) : null}

          {showFirstRunActions ? (
            <Alert>
              <AlertTitle>{byLocale(locale, "Next step after sign-in", "Nächster Schritt nach der Anmeldung")}</AlertTitle>
              <AlertDescription>
                {byLocale(
                  locale,
                  isLidlConnector(connector.source_id)
                    ? "Your Lidl sign-in is saved. The browser may still show the SMS code page or an error page. That is normal. Start the normal import now, or run the one-time full history import while everything is still fresh. Turn off VPN before importing; Lidl often rejects VPN traffic during this flow."
                    : "Your sign-in is saved. Start the normal import now, or run the one-time full history import while everything is still fresh.",
                  isLidlConnector(connector.source_id)
                    ? "Ihre Lidl-Anmeldung ist gespeichert. Der Browser kann weiterhin die SMS-Code-Seite oder eine Fehlerseite anzeigen. Das ist normal. Starten Sie jetzt den normalen Import oder laden Sie einmalig die gesamte Historie, solange alles noch frisch verbunden ist. Schalten Sie VPN vor dem Import aus; Lidl lehnt VPN-Verbindungen in diesem Ablauf häufig ab."
                    : "Ihre Anmeldung ist gespeichert. Starten Sie jetzt den normalen Import oder laden Sie einmalig die gesamte Historie, solange alles noch frisch verbunden ist."
                )}
              </AlertDescription>
            </Alert>
          ) : null}

          {blockedByOtherBootstrap ? (
            <Alert>
              <AlertTitle>{byLocale(locale, "Another sign-in is active", "Eine andere Anmeldung läuft")}</AlertTitle>
              <AlertDescription>
                {byLocale(
                  locale,
                  `Finish or stop ${blockingDisplayName} sign-in before starting ${displayName}.`,
                  `Schließen Sie die Anmeldung für ${blockingDisplayName} ab oder stoppen Sie sie, bevor Sie ${displayName} starten.`
                )}
              </AlertDescription>
            </Alert>
          ) : null}

          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => void handlePrimaryAction(connector, effectivePrimaryKind, effectivePrimaryEnabled)}
              disabled={
                bootstrapMutation.isPending ||
                syncMutation.isPending ||
                optimisticSyncStarting ||
                !effectivePrimaryEnabled ||
                effectivePrimaryKind === null
              }
            >
              {primaryButtonBusy ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              {primaryButtonLabel}
            </Button>
            {showFirstRunActions ? (
              <Button
                variant="outline"
                onClick={() => void syncMutation.mutateAsync({ sourceId: connector.source_id, full: true })}
                disabled={syncMutation.isPending}
              >
                {syncMutation.isPending && syncMutation.variables?.sourceId === connector.source_id && syncMutation.variables.full ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                {byLocale(locale, "Import full history", "Gesamte Historie laden")}
              </Button>
            ) : null}
          </div>

          {showBootstrapStatus ? (
            <Alert variant={bootstrapStatus?.status === "failed" ? "destructive" : "default"}>
              <AlertTitle>{bootstrapTitle}</AlertTitle>
              <AlertDescription className="space-y-2">
                {bootstrapSummary ? <p>{bootstrapSummary}</p> : null}
                {bootstrapStatus?.status === "running" ? (
                  <div className="space-y-3 pt-1">
                    <div className="flex flex-wrap gap-2">
                      {manualAuthStartUrl ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            void openExternalUrl(manualAuthStartUrl);
                          }}
                        >
                          <ExternalLink className="mr-2 h-4 w-4" />
                          {preferredBrowserCallToAction(
                            connector.source_id,
                            browserPreference?.preferredBrowser,
                            locale
                          )}
                        </Button>
                      ) : null}
                      {!manualAuthStartUrl && bootstrapStatus.remote_login_url ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            void openExternalUrl(bootstrapStatus.remote_login_url);
                          }}
                        >
                          <ExternalLink className="mr-2 h-4 w-4" />
                          {preferredBrowserCallToAction(
                            connector.source_id,
                            browserPreference?.preferredBrowser,
                            locale
                          )}
                        </Button>
                      ) : null}
                    </div>
                    {manualCallbackSupported ? (
                      <div className="space-y-2 rounded-md border border-border/50 bg-background/50 p-3">
                        <div className="space-y-1">
                          <p className="text-sm font-medium text-foreground">{manualCallbackTitle(connector.source_id, locale)}</p>
                          <p className="text-xs text-muted-foreground">{manualCallbackDescription(connector.source_id, locale)}</p>
                        </div>
                        <Label htmlFor={`callback-url-${connector.source_id}`} className="sr-only">
                          {byLocale(locale, "Callback URL", "Callback-URL")}
                        </Label>
                        <Textarea
                          id={`callback-url-${connector.source_id}`}
                          rows={3}
                          value={manualCallbackValue}
                          onChange={(event) => updateManualCallbackValue(connector.source_id, event.target.value)}
                          placeholder={manualCallbackPlaceholder(connector.source_id, locale)}
                        />
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            onClick={() =>
                              void confirmBootstrapMutation.mutateAsync({
                                sourceId: connector.source_id,
                                callbackUrl: manualCallbackValue.trim()
                              })
                            }
                            disabled={!canSubmitManualCallback}
                          >
                            {confirmBootstrapMutation.isPending &&
                            confirmBootstrapMutation.variables?.sourceId === connector.source_id ? (
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : null}
                            {byLocale(locale, "Continue with pasted URL", "Mit eingefügter URL fortfahren")}
                          </Button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {viewerIsAdmin && bootstrapLines.length > 0 ? (
                  <details className="rounded-md border border-border/50 bg-background/60 p-3">
                    <summary className="cursor-pointer text-xs font-medium text-foreground">
                      {byLocale(locale, "Technical details", "Technische Details")}
                    </summary>
                    <pre className="mt-3 max-h-48 overflow-auto text-xs text-foreground">
                      {bootstrapLines.join("\n")}
                    </pre>
                  </details>
                ) : null}
              </AlertDescription>
            </Alert>
          ) : null}

          {showSyncStatus ? (
            <Alert variant={latestSyncFailed ? "destructive" : "default"}>
              <AlertTitle>
                {latestSyncFailed
                  ? byLocale(locale, "Import failed", "Import fehlgeschlagen")
                  : optimisticSyncStarting
                  ? byLocale(locale, "Import starting", "Import wird gestartet")
                  : byLocale(locale, "Import running", "Import läuft")}
              </AlertTitle>
              <AlertDescription className="space-y-2">
                <p>{syncSummary}</p>
                {viewerIsAdmin && syncLines.length > 0 ? (
                  <details className="rounded-md border border-border/50 bg-background/60 p-3">
                    <summary className="cursor-pointer text-xs font-medium text-foreground">
                      {byLocale(locale, "Technical details", "Technische Details")}
                    </summary>
                    <pre className="mt-3 max-h-48 overflow-auto text-xs text-foreground">
                      {syncLines.join("\n")}
                    </pre>
                  </details>
                ) : null}
              </AlertDescription>
            </Alert>
          ) : null}

          <details className="rounded-lg border border-border/60 bg-background/40 px-4 py-3">
            <summary className="cursor-pointer text-sm font-medium text-foreground">
              {byLocale(locale, "More options", "Weitere Optionen")}
            </summary>
            <div className="mt-3 space-y-3">
              {updateAvailable ? (
                <p className="text-sm text-muted-foreground">
                  {byLocale(
                    locale,
                    `${displayName} has a newer trusted version available.`,
                    `Für ${displayName} ist eine neuere vertrauenswürdige Version verfügbar.`
                  )}
                </p>
              ) : null}
              {pack ? (
                <p className="text-sm text-muted-foreground">
                  {byLocale(locale, "Installed on this computer:", "Auf diesem Gerät installiert:")}{" "}
                  {packStateLabel(pack, locale)}.
                </p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                {showBootstrapStatus && bootstrapStatus?.can_cancel ? (
                  <Button
                    variant="outline"
                    onClick={() => void cancelBootstrapMutation.mutateAsync(connector.source_id)}
                    disabled={cancelBootstrapMutation.isPending}
                  >
                    {cancelBootstrapMutation.isPending &&
                    cancelBootstrapMutation.variables === connector.source_id ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    {byLocale(locale, "Cancel sign-in", "Anmeldung abbrechen")}
                  </Button>
                ) : null}

                {connector.supports_sync && !showFirstRunActions ? (
                  <Button
                    variant="outline"
                    onClick={() => void syncMutation.mutateAsync({ sourceId: connector.source_id, full: true })}
                    disabled={syncMutation.isPending || connector.enable_state !== "enabled"}
                  >
                    {syncMutation.isPending && syncMutation.variables?.sourceId === connector.source_id && syncMutation.variables.full ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    {byLocale(locale, "Import full history", "Gesamte Historie laden")}
                  </Button>
                ) : null}

                {viewerIsAdmin &&
                (connector.actions.operator.configure || connector.config_state !== "not_required") ? (
                  <Button
                    variant="outline"
                    onClick={() => void openSetup(connector, "configure")}
                  >
                    {byLocale(locale, "Settings", "Einstellungen")}
                  </Button>
                ) : null}

                {pack ? (
                  <Button
                    variant="outline"
                    onClick={() => openPackGuide(pack, false)}
                  >
                    {byLocale(locale, "How this works", "So funktioniert es")}
                  </Button>
                ) : null}

                {connector.actions.secondary.href ? (
                  <Button asChild variant="outline">
                    <Link to={connector.actions.secondary.href}>
                      <ExternalLink className="mr-2 h-4 w-4" />
                      {connector.actions.secondary.kind === "view_receipts"
                        ? byLocale(locale, "View receipts", "Belege ansehen")
                        : byLocale(locale, "Open source", "Quelle öffnen")}
                    </Link>
                  </Button>
                ) : null}

                {updateAvailable && catalogEntry?.entry_type === "desktop_pack" ? (
                  <Button
                    variant="outline"
                    onClick={() => void installCatalogPackMutation.mutateAsync(catalogEntry.entry_id)}
                    disabled={installCatalogPackMutation.isPending || !desktopBridgeAvailable}
                  >
                    {installCatalogPackMutation.isPending &&
                    installCatalogPackMutation.variables === catalogEntry.entry_id ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    {byLocale(locale, "Install trusted update", "Vertrauenswürdiges Update installieren")}
                  </Button>
                ) : null}
              </div>

              {viewerIsAdmin && connector.advanced.manual_commands.sync ? (
                <details className="rounded-lg border border-border/60 bg-background/60 p-3 text-xs text-muted-foreground">
                  <summary className="cursor-pointer font-medium text-foreground">
                    {byLocale(locale, "Admin fallback", "Admin-Fallback")}
                  </summary>
                  <p className="mt-2">
                    {byLocale(
                      locale,
                      "Only needed if the app cannot start the import for you.",
                      "Nur nötig, wenn die App den Import nicht selbst starten kann."
                    )}
                  </p>
                  <code className="mt-2 block overflow-auto whitespace-pre-wrap">
                    {connector.advanced.manual_commands.sync}
                  </code>
                </details>
              ) : null}
            </div>
          </details>

        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={byLocale(locale, "Connectors", "Anbindungen")}
        description={byLocale(
          locale,
          "Choose a store, finish setup once, then import receipts with a single button.",
          "Wählen Sie einen Händler, richten Sie ihn einmal ein und importieren Sie Belege dann mit nur einem Button."
        )}
      >
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => void installLocalPackMutation.mutateAsync()}
            disabled={installLocalPackMutation.isPending || !desktopBridgeAvailable}
          >
            {installLocalPackMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {byLocale(locale, "Add connector file", "Anbindungsdatei hinzufügen")}
          </Button>
          <Button
            variant="outline"
            onClick={() => void reloadMutation.mutateAsync()}
            disabled={reloadMutation.isPending}
          >
            {reloadMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            {byLocale(locale, "Refresh list", "Liste aktualisieren")}
          </Button>
        </div>
      </PageHeader>

      <p className="text-sm text-muted-foreground">
        {byLocale(
          locale,
          "Most stores only need one quick sign-in. After that, you can come back here whenever you want to import new receipts.",
          "Die meisten Händler brauchen nur eine kurze Anmeldung. Danach können Sie jederzeit hierher zurückkommen und neue Belege importieren."
        )}
      </p>

      {feedback ? (
        <Alert variant={feedback.variant}>
          <AlertTitle>{feedback.title}</AlertTitle>
          <AlertDescription>{feedback.message}</AlertDescription>
        </Alert>
      ) : null}

      {connectorsError ? (
        <Alert variant="destructive">
          <AlertTitle>{byLocale(locale, "Failed to load connectors", "Anbindungen konnten nicht geladen werden")}</AlertTitle>
          <AlertDescription>{connectorsError}</AlertDescription>
        </Alert>
      ) : null}

      {pendingActivationPacks.length > 0 ? (
        <div className="app-section-divider space-y-4">
          <div className="space-y-1.5">
            <h2 className="font-semibold leading-none tracking-tight">
              {byLocale(locale, "Finish adding connectors", "Anbindungen fertig hinzufügen")}
            </h2>
            <p className="text-sm text-muted-foreground">
              {byLocale(
                locale,
                "These are already on your computer. Review them once, then turn them on when you're ready to use them.",
                "Diese Anbindungen sind bereits auf Ihrem Gerät. Prüfen Sie sie kurz und aktivieren Sie sie, sobald Sie sie verwenden möchten."
              )}
            </p>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {pendingActivationPacks.map((pack) => {
              const catalogEntry = findCatalogEntryForPack(catalogEntries, pack);
              const guide = connectorGuideForPack(pack, pack.displayName, locale);
              return (
                <Card
                  key={pack.pluginId}
                  className={cn(
                    "border-border/60 bg-card/85 shadow-sm",
                    highlightedPackId === pack.pluginId ? "ring-2 ring-primary/20" : ""
                  )}
                >
                  <CardHeader className="space-y-3 border-b border-border/50 bg-background/40">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-1">
                        <CardTitle className="text-lg">{pack.displayName}</CardTitle>
                        <CardDescription>
                          {byLocale(locale, "Imported and ready to be turned on.", "Importiert und bereit zum Aktivieren.")}
                        </CardDescription>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Badge>{byLocale(locale, "Needs one more step", "Noch ein Schritt")}</Badge>
                        <Badge variant="secondary">{trustLabel(pack.trustClass, locale)}</Badge>
                        <Badge variant="outline">{pack.version}</Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 pt-6">
                    <p className="text-sm text-muted-foreground">
                      {guide.summary}
                    </p>
                    <p className="text-sm text-muted-foreground">{guide.caution}</p>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        onClick={() => void togglePackMutation.mutateAsync({ pluginId: pack.pluginId, enabled: true })}
                        disabled={togglePackMutation.isPending}
                      >
                        {togglePackMutation.isPending && togglePackMutation.variables?.pluginId === pack.pluginId ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : null}
                        {byLocale(locale, "Enable connector", "Anbindung aktivieren")}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => openPackGuide(pack, true)}
                        disabled={togglePackMutation.isPending}
                      >
                        {byLocale(locale, "Review first", "Zuerst prüfen")}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => void uninstallPackMutation.mutateAsync(pack.pluginId)}
                        disabled={uninstallPackMutation.isPending}
                      >
                        {uninstallPackMutation.isPending && uninstallPackMutation.variables === pack.pluginId ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : null}
                        {byLocale(locale, "Remove connector", "Anbindung entfernen")}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="space-y-1.5">
        <h2 className="font-semibold leading-none tracking-tight">
          {byLocale(locale, "Your stores", "Ihre Händler")}
        </h2>
        <p className="text-sm text-muted-foreground">
          {byLocale(
            locale,
            "Each store shows the next step clearly, so you can set it up once and come back for easy imports later.",
            "Jeder Händler zeigt klar den nächsten Schritt, damit Sie ihn einmal einrichten und später einfach wieder importieren können."
          )}
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {selectedLidlCard
          ? renderConnectorCard(selectedLidlCard, {
              key: "lidl-group",
              title: "Lidl Plus",
              headerExtra: (
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="lidl-market-select" className="text-xs uppercase text-muted-foreground">
                      {byLocale(locale, "Country", "Land")}
                    </Label>
                    <Select value={selectedLidlSourceId} onValueChange={setSelectedLidlSourceId}>
                      <SelectTrigger id="lidl-market-select" className="w-full max-w-xs bg-background/80">
                        <SelectValue placeholder={byLocale(locale, "Choose a country", "Land auswählen")} />
                      </SelectTrigger>
                      <SelectContent>
                        {lidlConnectorCards.map(({ connector }) => (
                          <SelectItem key={connector.source_id} value={connector.source_id}>
                            {connectorMarketLabel(connector, locale)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="lidl-browser-select" className="text-xs uppercase text-muted-foreground">
                      {byLocale(locale, "Browser", "Browser")}
                    </Label>
                    <Select
                      value={browserPreference?.preferredBrowser ?? "system_default"}
                      onValueChange={(value) =>
                        void browserPreferenceMutation.mutateAsync(value as DesktopExternalBrowserId)
                      }
                    >
                      <SelectTrigger id="lidl-browser-select" className="w-full max-w-xs bg-background/80">
                        <SelectValue placeholder={byLocale(locale, "Choose a browser", "Browser auswählen")} />
                      </SelectTrigger>
                      <SelectContent>
                        {(browserPreference?.options ?? [{ id: "system_default", available: true }]).map((option) => (
                          <SelectItem
                            key={option.id}
                            value={option.id}
                            disabled={!option.available && option.id !== "system_default"}
                          >
                            {externalBrowserLabel(option.id, locale)}
                            {!option.available && option.id !== "system_default"
                              ? byLocale(locale, " (not installed)", " (nicht installiert)")
                              : ""}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="max-w-xl text-xs text-muted-foreground">
                      {byLocale(
                        locale,
                        "Lidl always uses a real browser instead of the old embedded sign-in window. By default it opens your system browser, or you can pick another installed browser here.",
                        "Lidl verwendet immer einen echten Browser statt des alten eingebetteten Anmeldefensters. Standardmäßig wird Ihr Systembrowser geöffnet, oder Sie wählen hier einen anderen installierten Browser."
                      )}
                    </p>
                  </div>
                </div>
              )
            })
          : null}
        {selectedAmazonCard
          ? renderConnectorCard(selectedAmazonCard, {
              key: "amazon-group",
              title: "Amazon",
              headerExtra: (
                <div className="space-y-1.5">
                  <Label htmlFor="amazon-market-select" className="text-xs uppercase text-muted-foreground">
                    {byLocale(locale, "Country", "Land")}
                  </Label>
                  <Select value={selectedAmazonSourceId} onValueChange={setSelectedAmazonSourceId}>
                    <SelectTrigger id="amazon-market-select" className="w-full max-w-xs bg-background/80">
                      <SelectValue placeholder={byLocale(locale, "Choose a marketplace", "Marktplatz auswählen")} />
                    </SelectTrigger>
                    <SelectContent>
                      {amazonConnectorCards.map(({ connector }) => (
                        <SelectItem key={connector.source_id} value={connector.source_id}>
                          {connectorMarketLabel(connector, locale)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )
            })
          : null}
        {nonAmazonConnectorCards.map((card) => renderConnectorCard(card))}
      </div>

      {attentionPacks.length > 0 ? (
        <div className="app-section-divider space-y-4">
          <div className="space-y-1.5">
            <h2 className="font-semibold leading-none tracking-tight">
              {byLocale(locale, "Stored connectors needing attention", "Gespeicherte Anbindungen mit offenem Problem")}
            </h2>
            <p className="text-sm text-muted-foreground">
              {byLocale(
                locale,
                "These connectors are stored locally, but they cannot be turned on until the reported issue is resolved.",
                "Diese Anbindungen sind lokal gespeichert, können aber erst aktiviert werden, wenn das gemeldete Problem behoben ist."
              )}
            </p>
          </div>
          <div className="divide-y divide-border/60">
            {attentionPacks.map((pack) => {
              const catalogEntry = findCatalogEntryForPack(catalogEntries, pack);
              return (
                <div key={pack.pluginId} className="space-y-3 py-4 first:pt-0">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="font-medium">{pack.displayName}</p>
                      <p className="text-sm text-muted-foreground">
                        {packStateLabel(pack, locale)}.{" "}
                        {pack.trustReason ??
                          pack.compatibilityReason ??
                          byLocale(
                            locale,
                            "Review the connector details before trying again.",
                            "Bitte prüfen Sie die Details der Anbindung, bevor Sie es erneut versuchen."
                          )}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">{trustLabel(pack.trustClass, locale)}</Badge>
                      <Badge variant="outline">{pack.version}</Badge>
                    </div>
                  </div>
                  {catalogEntry?.support_policy ? (
                    <p className="text-sm text-muted-foreground">
                      {catalogEntry.support_policy.maintainer_support} {catalogEntry.support_policy.update_expectations}
                    </p>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={() => openPackGuide(pack, false)}
                    >
                      {byLocale(locale, "Review connector", "Anbindung prüfen")}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => void togglePackMutation.mutateAsync({ pluginId: pack.pluginId, enabled: true })}
                      disabled={
                        togglePackMutation.isPending ||
                        pack.status === "revoked" ||
                        pack.status === "invalid" ||
                        pack.status === "incompatible"
                      }
                    >
                      {togglePackMutation.isPending &&
                      togglePackMutation.variables?.pluginId === pack.pluginId &&
                      togglePackMutation.variables.enabled ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      {byLocale(locale, "Enable pack", "Paket aktivieren")}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => void uninstallPackMutation.mutateAsync(pack.pluginId)}
                      disabled={uninstallPackMutation.isPending}
                    >
                      {uninstallPackMutation.isPending && uninstallPackMutation.variables === pack.pluginId ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      {byLocale(locale, "Remove pack", "Paket entfernen")}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {curatedDesktopPackEntries.length > 0 ? (
        <div className="app-section-divider space-y-4">
          <div className="space-y-1.5">
            <h2 className="font-semibold leading-none tracking-tight">
              {byLocale(locale, "Trusted connectors you can add", "Vertrauenswürdige Anbindungen zum Hinzufügen")}
            </h2>
            <p className="text-sm text-muted-foreground">
              {byLocale(
                locale,
                "Add more supported stores here when you need them.",
                "Fügen Sie hier weitere unterstützte Händler hinzu, wenn Sie sie brauchen."
              )}
            </p>
          </div>
          <div className="divide-y divide-border/60">
            {curatedDesktopPackEntries.map((entry) => {
              const installedPack = entry.plugin_id
                ? receiptPlugins.find((pack) => pack.pluginId === entry.plugin_id) ?? null
                : null;
              const updateAvailable =
                installedPack !== null &&
                entry.current_version !== null &&
                compareVersions(installedPack.version, entry.current_version) < 0;
              const installLabel = installedPack
                ? updateAvailable
                  ? byLocale(locale, "Install trusted update", "Vertrauenswürdiges Update installieren")
                  : byLocale(locale, "Reinstall trusted pack", "Vertrauenswürdiges Paket neu installieren")
                : byLocale(locale, "Install trusted pack", "Vertrauenswürdiges Paket installieren");
              return (
                <div key={entry.entry_id} className="space-y-3 py-4 first:pt-0">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="font-medium">{entry.display_name}</p>
                      <p className="text-sm text-muted-foreground">{entry.summary}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">{trustLabel(entry.trust_class, locale)}</Badge>
                      {entry.current_version ? <Badge variant="outline">{entry.current_version}</Badge> : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={() => void installCatalogPackMutation.mutateAsync(entry.entry_id)}
                      disabled={installCatalogPackMutation.isPending || !desktopBridgeAvailable}
                    >
                      {installCatalogPackMutation.isPending && installCatalogPackMutation.variables === entry.entry_id ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      {installLabel}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      <Dialog open={packGuideState !== null} onOpenChange={(open) => (!open ? setPackGuideState(null) : undefined)}>
        <DialogContent className="max-w-xl">
          {packGuideState ? (
            <>
              <DialogHeader>
                <DialogTitle>
                  {packGuideState.showEnableAction
                    ? byLocale(
                        locale,
                        `Before you turn on ${packGuideState.pack.displayName}`,
                        `Bevor Sie ${packGuideState.pack.displayName} aktivieren`
                      )
                    : byLocale(
                        locale,
                        `${packGuideState.pack.displayName}: what to expect`,
                        `${packGuideState.pack.displayName}: kurz erklärt`
                      )}
                </DialogTitle>
                <DialogDescription>
                  {packGuideState.showEnableAction
                    ? byLocale(
                        locale,
                        "This quick note explains how the connector behaves before you enable it.",
                        "Diese kurze Erklärung zeigt, wie sich die Anbindung verhält, bevor Sie sie aktivieren."
                      )
                    : byLocale(
                        locale,
                        "Use this as a quick reminder for the first import and future reconnects.",
                        "Nutzen Sie dies als kurze Erinnerung für den ersten Import und spätere erneute Anmeldungen."
                      )}
                </DialogDescription>
              </DialogHeader>

              {(() => {
                const guide = connectorGuideForPack(packGuideState.pack, packGuideState.pack.displayName, locale);
                return (
                  <div className="space-y-4">
                    <Alert>
                      <AlertTitle>{guide.headline}</AlertTitle>
                      <AlertDescription>{guide.summary}</AlertDescription>
                    </Alert>

                    <div className="grid gap-3">
                      <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                        <p className="text-sm font-medium text-foreground">
                          {byLocale(locale, "Expected speed", "Erwartete Dauer")}
                        </p>
                        <p className="mt-1 text-sm text-muted-foreground">{guide.speedDescription}</p>
                      </div>
                      {guide.steps.map((step, index) => (
                        <div
                          key={`${step.title}-${index}`}
                          className="rounded-lg border border-border/60 bg-background/60 p-4"
                        >
                          <p className="text-sm font-medium text-foreground">{step.title}</p>
                          <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
                        </div>
                      ))}
                      <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                        <p className="text-sm font-medium text-foreground">
                          {byLocale(locale, "Good to know", "Gut zu wissen")}
                        </p>
                        <p className="mt-1 text-sm text-muted-foreground">{guide.caution}</p>
                      </div>
                    </div>

                    {packGuideState.catalogEntry?.support_policy ? (
                      <p className="text-sm text-muted-foreground">
                        {packGuideState.catalogEntry.support_policy.maintainer_support}{" "}
                        {packGuideState.catalogEntry.support_policy.update_expectations}
                      </p>
                    ) : null}
                  </div>
                );
              })()}

              <DialogFooter>
                <Button variant="outline" onClick={() => setPackGuideState(null)}>
                  {packGuideState.showEnableAction
                    ? byLocale(locale, "Not now", "Jetzt nicht")
                    : byLocale(locale, "Close", "Schließen")}
                </Button>
                {packGuideState.showEnableAction ? (
                  <Button
                    onClick={() => void handleGuidePrimaryAction()}
                    disabled={togglePackMutation.isPending}
                  >
                    {togglePackMutation.isPending &&
                    togglePackMutation.variables?.pluginId === packGuideState.pack.pluginId &&
                    togglePackMutation.variables.enabled ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    {byLocale(locale, "Enable connector", "Anbindung aktivieren")}
                  </Button>
                ) : null}
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={setupState !== null} onOpenChange={(open) => (!open ? closeSetup() : undefined)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {setupState?.mode === "configure"
                ? t("pages.connectors.dialog.settingsTitle", { name: setupState.connector.display_name })
                : t("pages.connectors.dialog.setupTitle", { name: setupState?.connector.display_name ?? "connector" })}
            </DialogTitle>
            <DialogDescription>
              {setupState?.mode === "configure"
                ? t("pages.connectors.dialog.settingsDescription")
                : t("pages.connectors.dialog.setupDescription")}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {setupConfigQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("pages.connectors.loadingSettings")}
              </div>
            ) : null}

            {!setupConfigQuery.isLoading && setupDialogFields.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("pages.connectors.noExtraSettings")}</p>
            ) : null}

            {setupState && setupState.mode !== "configure" && isAmazonConnector(setupState.connector.source_id) ? (
              (() => {
                const guide = localizedAmazonGuide(locale);
                return (
                  <div className="space-y-3">
                    <Alert>
                      <AlertTitle>{guide.headline}</AlertTitle>
                      <AlertDescription>{guide.summary}</AlertDescription>
                    </Alert>
                    <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                      <p className="text-sm font-medium text-foreground">
                        {byLocale(locale, "Expected duration", "Erwartete Dauer")}
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">{guide.speedDescription}</p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {guide.steps.map((step, index) => (
                        <div
                          key={`${step.title}-${index}`}
                          className="rounded-lg border border-border/60 bg-background/60 p-4"
                        >
                          <p className="text-sm font-medium text-foreground">{step.title}</p>
                          <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
                        </div>
                      ))}
                    </div>
                    <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                      <p className="text-sm font-medium text-foreground">
                        {byLocale(locale, "Important", "Wichtig")}
                      </p>
                      <p className="mt-1 text-sm text-muted-foreground">{guide.caution}</p>
                    </div>
                  </div>
                );
              })()
            ) : null}

            {setupDialogFields.map((field) => (
              <div key={field.key} className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor={`connector-field-${field.key}`}>{field.label}</Label>
                  {field.sensitive && field.has_value ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setClearSecretKeys((current) =>
                          current.includes(field.key)
                            ? current.filter((item) => item !== field.key)
                            : [...current, field.key]
                        )
                      }
                      >
                      {clearSecretKeys.includes(field.key)
                        ? t("pages.connectors.keepSavedValue")
                        : t("pages.connectors.clearSavedValue")}
                    </Button>
                  ) : null}
                </div>

                {field.input_kind === "boolean" ? (
                  <div className="flex items-center gap-3 rounded-md border px-3 py-2">
                    <Switch
                      id={`connector-field-${field.key}`}
                      checked={Boolean(setupValues[field.key])}
                      onCheckedChange={(checked) =>
                        setSetupValues((current) => ({ ...current, [field.key]: checked }))
                      }
                    />
                    <span className="text-sm text-muted-foreground">
                      {field.description ?? t("pages.connectors.toggleRuntimeSetting")}
                    </span>
                  </div>
                ) : (
                  <Input
                    id={`connector-field-${field.key}`}
                    type={field.input_kind === "password" ? "password" : field.input_kind}
                    value={typeof setupValues[field.key] === "string" ? String(setupValues[field.key]) : ""}
                    placeholder={field.placeholder ?? ""}
                    onChange={(event) =>
                      setSetupValues((current) => ({ ...current, [field.key]: event.target.value }))
                    }
                  />
                )}

                {field.description ? <p className="text-xs text-muted-foreground">{field.description}</p> : null}
              </div>
            ))}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeSetup}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() => void handleSaveSetup()}
              disabled={configMutation.isPending || bootstrapMutation.isPending}
            >
              {configMutation.isPending || bootstrapMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              {setupState?.mode === "configure" ? t("pages.connectors.saveSettings") : t("pages.connectors.saveAndContinue")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={authCompletionPrompt !== null} onOpenChange={(open) => (!open ? setAuthCompletionPrompt(null) : undefined)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>
              {authCompletionPrompt && isLidlConnector(authCompletionPrompt.sourceId)
                ? byLocale(locale, "Lidl sign-in saved", "Lidl-Anmeldung gespeichert")
                : authCompletionPrompt && isAmazonConnector(authCompletionPrompt.sourceId)
                  ? byLocale(locale, "Amazon sign-in saved", "Amazon-Anmeldung gespeichert")
                : byLocale(locale, "Sign-in saved", "Anmeldung gespeichert")}
            </DialogTitle>
            <DialogDescription>
              {authCompletionPrompt && isLidlConnector(authCompletionPrompt.sourceId)
                ? byLocale(
                    locale,
                    "Lidl handed the login back to the desktop app successfully. The browser may still stay on the SMS code page or show an error page after that. You can ignore the browser and continue here. Before starting the import, turn off VPN; Lidl often rejects VPN traffic in this flow.",
                    "Lidl hat die Anmeldung erfolgreich an die Desktop-App zurückgegeben. Der Browser kann danach weiterhin auf der SMS-Code-Seite bleiben oder eine Fehlerseite anzeigen. Sie können den Browser ignorieren und hier weitermachen. Schalten Sie vor dem Import VPN aus; Lidl lehnt VPN-Verbindungen in diesem Ablauf häufig ab."
                  )
                : authCompletionPrompt && isAmazonConnector(authCompletionPrompt.sourceId)
                  ? byLocale(
                      locale,
                      "Amazon sign-in is saved. A full history import will open Amazon pages in Chrome/Chromium and can take a long time while it walks year by year through orders and item pages.",
                      "Die Amazon-Anmeldung ist gespeichert. Ein Vollimport öffnet Amazon-Seiten in Chrome/Chromium und kann lange dauern, während Bestellungen und Artikelseiten Jahr für Jahr abgearbeitet werden."
                    )
                : authCompletionPrompt?.detail ??
                  byLocale(
                    locale,
                    "The connector sign-in was saved successfully. You can start importing now or come back later.",
                    "Die Anmeldung der Anbindung wurde erfolgreich gespeichert. Sie können jetzt den Import starten oder später zurückkommen."
                  )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-sm text-muted-foreground">
            <p>
              {byLocale(
                locale,
                authCompletionPrompt && isAmazonConnector(authCompletionPrompt.sourceId)
                  ? "For Amazon, the one-time full history import scans the configured number of years. Leave the browser open; a large history can take around half an hour or longer."
                  : authCompletionPrompt && isLidlConnector(authCompletionPrompt.sourceId)
                    ? "For Lidl Plus, use a direct non-VPN connection before importing. If VPN is active, sign-in or receipt loading can look successful at first and still be rejected by Lidl."
                  : "Next, either import only new receipts or run a one-time full history import while the login is still fresh.",
                authCompletionPrompt && isAmazonConnector(authCompletionPrompt.sourceId)
                  ? "Bei Amazon durchsucht der einmalige Vollimport die konfigurierte Anzahl von Jahren. Lassen Sie den Browser geöffnet; eine große Historie kann ungefähr eine halbe Stunde oder länger dauern."
                  : authCompletionPrompt && isLidlConnector(authCompletionPrompt.sourceId)
                    ? "Nutzen Sie für Lidl Plus vor dem Import eine direkte Verbindung ohne VPN. Wenn VPN aktiv ist, kann die Anmeldung oder das Laden der Belege zunächst erfolgreich wirken und trotzdem von Lidl abgelehnt werden."
                  : "Als Nächstes können Sie entweder nur neue Belege importieren oder einmalig die gesamte Historie laden, solange die Anmeldung noch frisch ist."
              )}
            </p>
          </div>
          <DialogFooter className="gap-2 sm:justify-end">
            <Button variant="outline" onClick={() => setAuthCompletionPrompt(null)}>
              {byLocale(locale, "Later", "Später")}
            </Button>
            {authCompletionPrompt ? (
              <Button
                variant="outline"
                onClick={() => {
                  void syncMutation.mutateAsync({ sourceId: authCompletionPrompt.sourceId, full: false });
                  setAuthCompletionPrompt(null);
                }}
                disabled={syncMutation.isPending}
              >
                {syncMutation.isPending &&
                syncMutation.variables?.sourceId === authCompletionPrompt.sourceId &&
                !syncMutation.variables.full ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                {byLocale(locale, "Import receipts", "Belege importieren")}
              </Button>
            ) : null}
            {authCompletionPrompt ? (
              <Button
                onClick={() => {
                  void syncMutation.mutateAsync({ sourceId: authCompletionPrompt.sourceId, full: true });
                  setAuthCompletionPrompt(null);
                }}
                disabled={syncMutation.isPending}
              >
                {syncMutation.isPending &&
                syncMutation.variables?.sourceId === authCompletionPrompt.sourceId &&
                syncMutation.variables.full ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : null}
                {byLocale(locale, "Import full history", "Gesamte Historie laden")}
              </Button>
            ) : null}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
