import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  BellRing,
  CalendarCheck,
  CheckCircle2,
  Database,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Menu,
  MessageCircle,
  Plus,
  ReceiptText,
  SlidersHorizontal,
  TrendingUp,
  X,
  Wallet,
  type LucideIcon
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "next-themes";

import { fetchAISettings } from "@/api/aiSettings";
import {
  fetchConnectors,
  fetchConnectorSyncStatus,
  type ConnectorSyncStatus
} from "@/api/connectors";
import { logout } from "@/api/auth";
import {
  fetchNotifications,
  markAllNotificationsRead,
  updateNotificationReadState
} from "@/api/notifications";
import type { CurrentUser } from "@/api/users";
import { getSidePanelPageContext } from "@/agent/page-context";
import { useDateRangeContext, type DateRangePreset } from "@/app/date-range-context";
import { preloadRouteModule } from "@/app/page-loaders";
import { useAccessScope } from "@/app/scope-provider";
import { ChatPanel } from "@/components/ChatPanel";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import {
  getDesktopRedirectMessage,
  isDesktopNavRouteVisible,
  useDesktopCapabilities,
  type DesktopLocationState
} from "@/lib/desktop-capabilities";
import { hasDesktopControlCenterBridge, openDesktopControlCenter } from "@/lib/desktop-shell";
import { type TranslationKey, isSupportedLocale, useI18n } from "@/i18n";
import { cn } from "@/lib/utils";
import logoMark from "@/assets/logo-mark.svg";

type NavItem = {
  to: string;
  labelKey: TranslationKey;
  icon: LucideIcon;
  adminOnly?: boolean;
};

type NavGroup = {
  labelKey: TranslationKey;
  items: NavItem[];
};

function isDocumentVisible(): boolean {
  if (typeof document === "undefined") {
    return true;
  }
  return document.visibilityState === "visible";
}

const PRIMARY_NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.group.workspace",
    items: [
      { to: "/", labelKey: "nav.item.dashboard", icon: LayoutDashboard },
      { to: "/transactions", labelKey: "nav.item.transactions", icon: ReceiptText },
      { to: "/groceries", labelKey: "nav.item.groceries", icon: Database },
      { to: "/budget", labelKey: "nav.item.budget", icon: Wallet },
      { to: "/bills", labelKey: "nav.item.bills", icon: CalendarCheck },
      { to: "/cash-flow", labelKey: "nav.item.cashFlow", icon: TrendingUp },
      { to: "/reports", labelKey: "nav.item.reports", icon: Activity },
      { to: "/goals", labelKey: "nav.item.goals", icon: CheckCircle2 },
      { to: "/merchants", labelKey: "nav.item.merchants", icon: Database },
      { to: "/settings", labelKey: "nav.item.settings", icon: SlidersHorizontal }
    ]
  }
];

const QUICK_ACTIONS: NavItem[] = [
  { to: "/add", labelKey: "nav.item.manualImport", icon: Plus },
  { to: "/connectors", labelKey: "nav.item.connectors", icon: Database },
  { to: "/chat", labelKey: "nav.item.chat", icon: MessageCircle }
];

const CHAT_PANEL_WIDTH_STORAGE_KEY = "layout.chat_panel_width";
const GLOBAL_SYNC_DISMISS_STORAGE_KEY = "app.global_sync_banner.dismissed";
const CHAT_PANEL_WIDTH_DEFAULT = 420;
const CHAT_PANEL_WIDTH_MIN = 320;
const CHAT_PANEL_WIDTH_MAX = 860;

type ParsedSyncProgress = {
  seen: number | null;
  total: number | null;
  latestLine: string | null;
};

function preferencesLabel(locale: "en" | "de"): string {
  return locale === "de" ? "Einstellungen" : "Preferences";
}

function controlCenterMenuLabel(locale: "en" | "de"): string {
  return locale === "de" ? "Kontrollzentrum öffnen" : "Open control center";
}

function notificationEmptyLabel(locale: "en" | "de"): string {
  return locale === "de" ? "Noch keine Benachrichtigungen." : "No notifications yet.";
}

function notificationMarkAllReadLabel(locale: "en" | "de"): string {
  return locale === "de" ? "Alle als gelesen markieren" : "Mark all as read";
}

function syncBannerStatusLabel(
  locale: "en" | "de",
  status: ConnectorSyncStatus["status"],
  partialSuccess = false
): string {
  if (partialSuccess) {
    return locale === "de" ? "Mit Hinweisen" : "With issues";
  }
  if (locale === "de") {
    if (status === "running") {
      return "Läuft";
    }
    if (status === "succeeded") {
      return "Fertig";
    }
    return "Fehlgeschlagen";
  }
  if (status === "running") {
    return "Running";
  }
  if (status === "succeeded") {
    return "Finished";
  }
  return "Failed";
}

function syncBannerTitle(locale: "en" | "de", source: string): string {
  return locale === "de" ? `${source}-Synchronisierung` : `${source} sync`;
}

function syncBannerProgressLabel(locale: "en" | "de", seen: number, total: number | null): string {
  if (locale === "de") {
    return total === null ? `${seen} verarbeitet` : `${seen} von ${total}`;
  }
  return total === null ? `${seen} processed` : `${seen} of ${total}`;
}

function syncBannerWaitingLabel(locale: "en" | "de"): string {
  return locale === "de" ? "Synchronisierungsstatus wird vorbereitet..." : "Preparing sync status...";
}

function syncBannerStageLabel(
  locale: "en" | "de",
  stage: string,
  detail: string | null
): string | null {
  if (stage === "authenticating") {
    return locale === "de" ? "Gespeicherte Anmeldung wird geprüft..." : "Checking saved sign-in...";
  }
  if (stage === "refreshing_auth") {
    return locale === "de" ? "Belegsitzung wird aktualisiert..." : "Refreshing receipt session...";
  }
  if (stage === "healthcheck") {
    return locale === "de" ? "Zugriff auf den Händler wird geprüft..." : "Validating retailer access...";
  }
  if (stage === "discovering") {
    return locale === "de" ? "Bestellverlauf wird durchsucht..." : "Scanning order history...";
  }
  if (stage === "processing" && detail === "preparing_import") {
    return locale === "de" ? "Import wird vorbereitet..." : "Preparing import...";
  }
  if (stage === "processing") {
    return locale === "de" ? "Belege werden importiert..." : "Importing receipts...";
  }
  if (stage === "finalizing") {
    return locale === "de" ? "Belege werden gespeichert..." : "Saving receipts...";
  }
  return null;
}

function syncBannerOpenConnectorsLabel(locale: "en" | "de"): string {
  return locale === "de" ? "Anbindungen öffnen" : "Open connectors";
}

function partialSyncDescription(locale: "en" | "de"): string {
  return locale === "de"
    ? "Der Import hat bereits Belege gespeichert, aber ein späterer Schritt braucht noch Aufmerksamkeit."
    : "The import already saved receipts, but a later follow-up step still needs attention.";
}

function parseSyncProgress(status: ConnectorSyncStatus): ParsedSyncProgress {
  let seen: number | null = null;
  let total: number | null = null;
  let latestLine: string | null = null;

  for (const line of status.output_tail) {
    if (line.startsWith("stage=")) {
      latestLine = line;
    }
    const match = /seen=(\d+)\/(\d+|\?)/.exec(line);
    if (!match) {
      continue;
    }
    seen = Number(match[1]);
    total = match[2] === "?" ? null : Number(match[2]);
  }

  if (latestLine === null && status.output_tail.length > 0) {
    latestLine = status.output_tail[status.output_tail.length - 1] ?? null;
  }

  return { seen, total, latestLine };
}

function parseSyncFields(line: string | null): Record<string, string> | null {
  if (!line) {
    return null;
  }
  const fields: Record<string, string> = {};
  for (const segment of line.trim().split(/\s+/)) {
    const separatorIndex = segment.indexOf("=");
    if (separatorIndex <= 0) {
      continue;
    }
    const key = segment.slice(0, separatorIndex);
    const value = segment.slice(separatorIndex + 1);
    if (!key || !value) {
      continue;
    }
    fields[key] = value;
  }
  return Object.keys(fields).length > 0 ? fields : null;
}

function formatSyncLine(locale: "en" | "de", line: string | null): string | null {
  if (!line) {
    return null;
  }
  const fields = parseSyncFields(line);
  if (!fields?.stage) {
    return line;
  }

  const stageLabel = syncBannerStageLabel(locale, fields.stage, fields.detail ?? null);
  if (stageLabel) {
    const extras: string[] = [];
    if (fields.year) {
      extras.push(locale === "de" ? `Jahr ${fields.year}` : `Year ${fields.year}`);
    }
    if (fields.page) {
      extras.push(locale === "de" ? `Seite ${fields.page}` : `Page ${fields.page}`);
    }
    if (fields.total && Number(fields.total) > 0) {
      extras.push(locale === "de" ? `${fields.total} Belege erkannt` : `${fields.total} receipts found`);
    }
    if (fields.queued && Number(fields.queued) > 0) {
      extras.push(locale === "de" ? `${fields.queued} entdeckt` : `${fields.queued} discovered`);
    }
    if (fields.seen && Number(fields.seen) > 0) {
      extras.push(locale === "de" ? `${fields.seen} verarbeitet` : `${fields.seen} processed`);
    }
    if (fields.new && Number(fields.new) > 0) {
      extras.push(locale === "de" ? `${fields.new} neu` : `${fields.new} new`);
    }
    if (fields.skipped && Number(fields.skipped) > 0) {
      extras.push(locale === "de" ? `${fields.skipped} bereits vorhanden` : `${fields.skipped} already present`);
    }
    return extras.length > 0 ? `${stageLabel} ${extras.join(" • ")}` : stageLabel;
  }

  const formattedSegments: string[] = [];
  if (fields.stage) {
    formattedSegments.push(fields.stage);
  }
  if (fields.pages && Number(fields.pages) > 0) {
    formattedSegments.push(`pages=${fields.pages}`);
  }
  if (fields.queued && Number(fields.queued) > 0) {
    formattedSegments.push(`queued=${fields.queued}`);
  }
  if (fields.seen && Number(fields.seen) > 0) {
    formattedSegments.push(`seen=${fields.seen}`);
  }
  if (fields.new && Number(fields.new) > 0) {
    formattedSegments.push(`new=${fields.new}`);
  }
  if (fields.items && Number(fields.items) > 0) {
    formattedSegments.push(`items=${fields.items}`);
  }
  if (fields.skipped && Number(fields.skipped) > 0) {
    formattedSegments.push(`skipped=${fields.skipped}`);
  }
  if (fields.current) {
    formattedSegments.push(`current=${fields.current}`);
  }
  return formattedSegments.join(" • ");
}

function syncRunKey(sourceId: string, status: ConnectorSyncStatus): string {
  return `${sourceId}:${status.status}:${status.started_at ?? ""}:${status.finished_at ?? ""}`;
}

function SyncStatusBanner({
  sourceLabel,
  status,
  onDismiss
}: {
  sourceLabel: string;
  status: ConnectorSyncStatus;
  onDismiss?: (() => void) | undefined;
}) {
  const { locale, t } = useI18n();
  const progress = parseSyncProgress(status);
  const partialSuccess =
    status.status === "failed" &&
    ((progress.seen ?? 0) > 0 || Number(parseSyncFields(progress.latestLine)?.new ?? "0") > 0);
  const Icon =
    status.status === "running"
      ? LoaderCircle
      : status.status === "succeeded"
        ? CheckCircle2
        : partialSuccess
          ? CheckCircle2
          : AlertCircle;
  const iconClassName =
    status.status === "running"
      ? "text-sky-700 animate-spin"
      : status.status === "succeeded"
        ? "text-emerald-700"
        : partialSuccess
          ? "text-amber-700"
          : "text-destructive";
  const alertClassName =
    status.status === "running"
      ? "border-sky-200 bg-sky-50/80 text-sky-950"
      : status.status === "succeeded"
        ? "border-emerald-200 bg-emerald-50/80 text-emerald-950"
        : partialSuccess
          ? "border-amber-200 bg-amber-50/80 text-amber-950"
          : "border-destructive/30 bg-destructive/5";
  const progressLabel =
    progress.seen !== null && progress.seen > 0 && progress.total !== null
      ? syncBannerProgressLabel(locale, progress.seen, progress.total)
      : progress.seen !== null && progress.seen > 0
        ? syncBannerProgressLabel(locale, progress.seen, null)
        : null;
  const latestLine = partialSuccess ? partialSyncDescription(locale) : formatSyncLine(locale, progress.latestLine);

  return (
    <Alert className={cn("rounded-xl", alertClassName)}>
      <Icon className={cn("h-4 w-4", iconClassName)} />
      <AlertTitle className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span>{syncBannerTitle(locale, sourceLabel)}</span>
          <Badge variant={status.status === "failed" && !partialSuccess ? "destructive" : "secondary"}>
            {syncBannerStatusLabel(locale, status.status, partialSuccess)}
          </Badge>
          {progressLabel ? <Badge variant="outline">{progressLabel}</Badge> : null}
        </div>
        {onDismiss ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            aria-label={t("common.close")}
            onClick={onDismiss}
          >
            <X className="h-4 w-4" />
          </Button>
        ) : null}
      </AlertTitle>
      <AlertDescription className="flex flex-wrap items-center gap-3 text-xs sm:text-sm">
        <span>{latestLine ?? syncBannerWaitingLabel(locale)}</span>
        <Link className="font-medium underline underline-offset-4" to="/connectors">
          {syncBannerOpenConnectorsLabel(locale)}
        </Link>
      </AlertDescription>
    </Alert>
  );
}

function DesktopRedirectBanner({
  onDismiss
}: {
  onDismiss: () => void;
}) {
  const location = useLocation();
  const { locale } = useI18n();
  const notice = (location.state as DesktopLocationState | null)?.desktopRedirectNotice ?? null;

  if (!notice) {
    return null;
  }

  const message = getDesktopRedirectMessage(locale, notice);

  return (
    <Alert className="rounded-xl border-amber-300 bg-amber-50/80 text-amber-950">
      <AlertCircle className="h-4 w-4 text-amber-700" />
      <AlertTitle className="flex items-start justify-between gap-3">
        <span>{message.title}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          aria-label={locale === "de" ? "Hinweis schließen" : "Dismiss notice"}
          onClick={onDismiss}
        >
          <X className="h-4 w-4" />
        </Button>
      </AlertTitle>
      <AlertDescription className="text-sm">
        {message.description}
        <span className="ml-1 font-medium">
          {locale === "de" ? `Angeforderte Route: ${notice.requestedPath}.` : `Requested route: ${notice.requestedPath}.`}
        </span>
      </AlertDescription>
    </Alert>
  );
}

function clampChatPanelWidth(width: number): number {
  if (!Number.isFinite(width)) {
    return CHAT_PANEL_WIDTH_DEFAULT;
  }
  const viewportWidth = typeof window !== "undefined" ? window.innerWidth : 1440;
  const maxByViewport = Math.max(CHAT_PANEL_WIDTH_MIN, Math.min(CHAT_PANEL_WIDTH_MAX, viewportWidth - 280));
  return Math.min(maxByViewport, Math.max(CHAT_PANEL_WIDTH_MIN, Math.round(width)));
}

function filterNavGroups(groups: NavGroup[], isAdmin: boolean, visibleRoutes: Set<string>): NavGroup[] {
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => (!item.adminOnly || isAdmin) && visibleRoutes.has(item.to))
    }))
    .filter((group) => group.items.length > 0);
}

function filterNavItems(items: NavItem[], isAdmin: boolean, visibleRoutes: Set<string>): NavItem[] {
  return items.filter((item) => (!item.adminOnly || isAdmin) && visibleRoutes.has(item.to));
}

function formatShellTimestamp(locale: "en" | "de", value: string | null | undefined): string {
  if (!value) {
    return locale === "de" ? "Lokale Daten" : "Local data";
  }
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return locale === "de" ? "Lokale Daten" : "Local data";
  }
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(date);
}

function formatTopBarRange(locale: "en" | "de", fromDate: string, toDate: string): string {
  const start = new Date(fromDate);
  const end = new Date(toDate);
  const formatter = new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-US", {
    month: "short",
    day: "numeric"
  });
  return `${formatter.format(start)} - ${formatter.format(end)}`;
}

function datePresetLabel(locale: "en" | "de", preset: DateRangePreset): string {
  const labels: Record<DateRangePreset, { en: string; de: string }> = {
    this_week: { en: "This week", de: "Diese Woche" },
    last_7_days: { en: "Last 7 days", de: "Letzte 7 Tage" },
    this_month: { en: "This month", de: "Dieser Monat" },
    last_month: { en: "Last month", de: "Letzter Monat" },
    custom: { en: "Custom", de: "Benutzerdefiniert" }
  };
  return locale === "de" ? labels[preset].de : labels[preset].en;
}

function NavItems({ groups }: { groups: NavGroup[] }) {
  const { t } = useI18n();

  return (
    <nav className="flex flex-col gap-7" aria-label={t("nav.primary")}>
      {groups.map((group, index) => (
        <div key={`${group.labelKey}-${index}`}>
          <p className="mb-3 px-4 text-[11px] font-semibold uppercase tracking-[0.22em] text-sidebar-foreground/35">
            {t(group.labelKey)}
          </p>
          <div className="flex flex-col gap-1.5">
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                onMouseEnter={() => preloadRouteModule(item.to)}
                onFocus={() => preloadRouteModule(item.to)}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-[24px] px-4 py-3.5 text-left text-base font-medium tracking-[-0.02em] transition-colors",
                    isActive
                      ? "bg-emerald-500/78 text-white shadow-[0_16px_30px_rgba(16,185,129,0.22)]"
                      : "text-sidebar-foreground/72 hover:bg-white/7 hover:text-white"
                  )
                }
              >
                <item.icon className="h-5 w-5 shrink-0" />
                <span className="min-w-0 flex-1 whitespace-normal">{t(item.labelKey)}</span>
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </nav>
  );
}

function SidebarContent({
  user,
  onLogout,
  onOpenChat,
  chatOpen,
  aiReady,
  quickActions,
  connectedMerchantCount,
  topMerchantLabels,
  lastUpdatedLabel
}: {
  user: CurrentUser;
  onLogout: () => void;
  onOpenChat: () => void;
  chatOpen: boolean;
  aiReady: boolean;
  quickActions: NavItem[];
  connectedMerchantCount: number;
  topMerchantLabels: string[];
  lastUpdatedLabel: string;
}) {
  const { t } = useI18n();
  const desktopCapabilities = useDesktopCapabilities();
  const visibleRoutes = useMemo(
    () =>
      new Set([
        ...PRIMARY_NAV_GROUPS.flatMap((group) => group.items),
        ...QUICK_ACTIONS
      ]
        .filter((item) => isDesktopNavRouteVisible(desktopCapabilities, item.to))
        .map((item) => item.to)),
    [desktopCapabilities]
  );
  const primaryGroups = filterNavGroups(PRIMARY_NAV_GROUPS, user.is_admin, visibleRoutes);

  return (
    <div className="flex h-full flex-col bg-[linear-gradient(180deg,rgba(7,20,35,0.98),rgba(5,16,30,0.98))] text-sidebar-foreground">
      <div className="px-6 pb-4 pt-6">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/10 bg-white/6 p-2 shadow-[0_16px_34px_rgba(2,12,24,0.42)]">
          <img src={logoMark} alt="" aria-hidden="true" className="h-full w-full" />
        </div>
          <div>
            <p className="text-lg font-semibold tracking-tight text-white">{t("app.brand.title")}</p>
            <p className="text-sm text-sidebar-foreground/60">{t("app.brand.subtitle")}</p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-6">
        <NavItems groups={primaryGroups} />

        {quickActions.length > 0 ? (
          <div className="mt-8 rounded-[28px] border border-white/8 bg-white/4 p-4 shadow-[0_20px_44px_rgba(2,12,24,0.26)]">
            <p className="px-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-sidebar-foreground/40">
              {t("nav.group.shortcuts")}
            </p>
            <div className="mt-3 grid gap-2">
              {quickActions.map((item) => (
                <Button
                  key={item.to}
                  asChild
                  variant="ghost"
                  className="h-11 justify-start gap-3 rounded-2xl border border-transparent bg-white/4 px-3 text-sidebar-foreground/78 hover:border-white/8 hover:bg-white/8 hover:text-white"
                >
                  <Link
                    to={item.to}
                    onMouseEnter={() => preloadRouteModule(item.to)}
                    onFocus={() => preloadRouteModule(item.to)}
                  >
                    <item.icon className="h-4 w-4 shrink-0" />
                    {t(item.labelKey)}
                  </Link>
                </Button>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-8 rounded-[28px] border border-white/8 bg-white/4 p-4 shadow-[0_20px_44px_rgba(2,12,24,0.26)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-white">{t("app.sidebar.connectedMerchants")}</p>
              <p className="text-xs text-sidebar-foreground/55">{t("app.sidebar.connectedMerchantsHint")}</p>
            </div>
            <div className="rounded-full bg-white/10 px-3 py-1 text-sm font-semibold text-white">
              {connectedMerchantCount}
            </div>
          </div>
          {topMerchantLabels.length > 0 ? (
            <div className="mt-4 grid grid-cols-2 gap-2">
              {topMerchantLabels.slice(0, 6).map((label) => (
                <div
                  key={label}
                  className="rounded-2xl border border-white/8 bg-white/6 px-3 py-3 text-sm font-medium text-sidebar-foreground/82"
                >
                  {label}
                </div>
              ))}
            </div>
          ) : (
            <p className="mt-4 text-sm text-sidebar-foreground/55">{t("app.sidebar.connectedMerchantsEmpty")}</p>
          )}
        </div>

        <div className="mt-4 rounded-[28px] border border-emerald-400/18 bg-emerald-400/8 p-4 shadow-[0_20px_44px_rgba(2,12,24,0.22)]">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-200/70">
            {t("app.sidebar.localData")}
          </p>
          <p className="mt-3 text-sm font-medium text-white">{lastUpdatedLabel}</p>
          <p className="mt-1 text-xs text-sidebar-foreground/55">{t("app.sidebar.localDataHint")}</p>
        </div>
      </div>

      <div className="px-4 pb-3">
        <Button
          variant="outline"
          className="relative h-11 w-full justify-start gap-2 rounded-2xl border-white/10 bg-white/4 text-sidebar-foreground/78 hover:bg-white/8 hover:text-white"
          onClick={onOpenChat}
        >
          <MessageCircle className="h-4 w-4" />
          {chatOpen ? t("app.chat.close") : t("app.chat.open")}
          {aiReady ? (
            <span className="absolute right-3 inline-flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500/70" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
            </span>
          ) : null}
        </Button>
      </div>

      <div className="border-t border-white/8 px-4 py-4">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-white">
              {user.display_name ?? user.username}
            </p>
            {user.is_admin ? (
              <p className="text-[10px] text-sidebar-foreground/40">{t("app.role.admin")}</p>
            ) : null}
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("action.signOut")}
            className="h-8 w-8 shrink-0 rounded-full text-sidebar-foreground/60 hover:bg-white/8 hover:text-white"
            onClick={onLogout}
          >
            <LogOut className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {import.meta.env.DEV ? (
        <div className="border-t border-sidebar-border px-4 py-2 font-mono text-[10px] text-sidebar-foreground/30">
          {import.meta.env.MODE}
        </div>
      ) : null}
    </div>
  );
}

type AppShellProps = {
  user: CurrentUser;
};

export function AppShell({ user }: AppShellProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const desktopCapabilities = useDesktopCapabilities();
  const { theme, setTheme } = useTheme();
  const navItems = useMemo(
    () =>
      [...PRIMARY_NAV_GROUPS.flatMap((group) => group.items), ...QUICK_ACTIONS]
        .filter((item) => isDesktopNavRouteVisible(desktopCapabilities, item.to)),
    [desktopCapabilities]
  );
  const { scope, setScope } = useAccessScope();
  const { locale, setLocale, t } = useI18n();
  const { preset, fromDate, toDate, setPreset } = useDateRangeContext();
  const canOpenControlCenter = hasDesktopControlCenterBridge();
  const [chatOpen, setChatOpen] = useState(false);
  const [dismissedSyncRun, setDismissedSyncRun] = useState<string | null>(() => {
    if (typeof window === "undefined") {
      return null;
    }
    const storage = window.localStorage;
    if (!storage || typeof storage.getItem !== "function") {
      return null;
    }
    return storage.getItem(GLOBAL_SYNC_DISMISS_STORAGE_KEY);
  });
  const [chatPanelWidth, setChatPanelWidth] = useState<number>(() => {
    if (typeof window === "undefined") {
      return CHAT_PANEL_WIDTH_DEFAULT;
    }
    const storage = window.localStorage;
    if (!storage || typeof storage.getItem !== "function") {
      return CHAT_PANEL_WIDTH_DEFAULT;
    }
    const raw = storage.getItem(CHAT_PANEL_WIDTH_STORAGE_KEY);
    if (raw === null) {
      return CHAT_PANEL_WIDTH_DEFAULT;
    }
    const parsed = Number(raw);
    return clampChatPanelWidth(parsed);
  });
  const aiSettingsQuery = useQuery({
    queryKey: ["ai-settings"],
    queryFn: fetchAISettings
  });
  const connectorsQuery = useQuery({
    queryKey: ["connectors"],
    queryFn: fetchConnectors
  });
  const notificationsQuery = useQuery({
    queryKey: ["notifications", "header"],
    queryFn: () => fetchNotifications(8),
    refetchInterval: 30_000
  });
  const markAllNotificationsReadMutation = useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
  });
  const markNotificationReadMutation = useMutation({
    mutationFn: ({ notificationId }: { notificationId: string }) =>
      updateNotificationReadState(notificationId, false),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["notifications"] });
    }
  });
  const globalSyncConnectors =
    connectorsQuery.data?.connectors.filter(
      (connector) => connector.supports_sync && connector.install_state === "installed"
    ) ?? [];
  const quickActions = useMemo(
    () =>
      filterNavItems(
        QUICK_ACTIONS,
        user.is_admin,
        new Set(navItems.map((item) => item.to))
      ),
    [navItems, user.is_admin]
  );
  const connectorSyncQueries = useQueries({
    queries: globalSyncConnectors.map((connector) => ({
      queryKey: ["global-connector-sync-status", connector.source_id],
      queryFn: () => fetchConnectorSyncStatus(connector.source_id),
      refetchInterval: (query: { state: { data?: ConnectorSyncStatus } }) =>
        !isDocumentVisible() ? false : query.state.data?.status === "running" ? 1500 : 30_000,
      retry: false
    }))
  });
  const syncStatusEntries = connectorSyncQueries.flatMap((query, index) =>
    query.status === "success" && query.data
      ? [
          {
            sourceId: globalSyncConnectors[index]?.source_id ?? query.data.source_id,
            sourceLabel: globalSyncConnectors[index]?.display_name ?? query.data.source_id,
            status: query.data
          }
        ]
      : []
  );
  const activeNavItem = navItems.find((item) =>
    item.to === "/"
      ? location.pathname === "/"
      : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)
  );
  const sidePanelPageContext = getSidePanelPageContext(location.pathname);
  const aiReady =
    aiSettingsQuery.data?.enabled === true &&
    (aiSettingsQuery.data.api_key_set || aiSettingsQuery.data.oauth_connected);
  const globalSyncStatus = syncStatusEntries
    .sort((left, right) => {
      const rank = (value: ConnectorSyncStatus["status"]) =>
        value === "running" ? 0 : value === "failed" ? 1 : value === "succeeded" ? 2 : 3;
      return rank(left.status.status) - rank(right.status.status);
    })
    .find((entry) => entry.status.status !== "idle");
  const globalSyncRunId = globalSyncStatus ? syncRunKey(globalSyncStatus.sourceId, globalSyncStatus.status) : null;
  const globalSyncDismissed =
    globalSyncStatus?.status.status !== "running" && globalSyncRunId !== null && dismissedSyncRun === globalSyncRunId;
  const sidebarMerchantLabels = globalSyncConnectors
    .map((connector) => connector.display_name?.trim() || connector.source_id)
    .filter(Boolean)
    .slice(0, 6);
  const notifications = notificationsQuery.data?.items ?? [];
  const unreadNotifications = notificationsQuery.data?.unread_count ?? 0;
  const lastUpdatedLabel = formatShellTimestamp(
    locale,
    globalSyncStatus?.status.finished_at ??
      globalSyncStatus?.status.started_at ??
      connectorsQuery.data?.generated_at ??
      null
  );
  const topBarRangeLabel = formatTopBarRange(locale, fromDate, toDate);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  }

  function handleOpenControlCenter(): void {
    void openDesktopControlCenter();
  }

  function handleOpenChat(): void {
    setChatOpen((current) => !current);
  }

  function dismissDesktopRedirectNotice(): void {
    const currentState = (location.state as DesktopLocationState | null) ?? {};
    if (!currentState.desktopRedirectNotice) {
      return;
    }
    const { desktopRedirectNotice: _desktopRedirectNotice, ...nextState } = currentState;
    navigate(
      {
        pathname: location.pathname,
        search: location.search,
        hash: location.hash
      },
      {
        replace: true,
        state: Object.keys(nextState).length > 0 ? nextState : null
      }
    );
  }

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const storage = window.localStorage;
    if (!storage || typeof storage.setItem !== "function") {
      return;
    }
    storage.setItem(CHAT_PANEL_WIDTH_STORAGE_KEY, String(chatPanelWidth));
  }, [chatPanelWidth]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const storage = window.localStorage;
    if (!storage || typeof storage.setItem !== "function" || typeof storage.removeItem !== "function") {
      return;
    }
    if (dismissedSyncRun) {
      storage.setItem(GLOBAL_SYNC_DISMISS_STORAGE_KEY, dismissedSyncRun);
      return;
    }
    storage.removeItem(GLOBAL_SYNC_DISMISS_STORAGE_KEY);
  }, [dismissedSyncRun]);

  useEffect(() => {
    if (globalSyncStatus?.status.status === "running" && dismissedSyncRun !== null) {
      setDismissedSyncRun(null);
    }
  }, [dismissedSyncRun, globalSyncStatus?.status.status]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const handleResize = () => {
      setChatPanelWidth((current) => clampChatPanelWidth(current));
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div className="min-h-screen bg-[#f3f6fb] dark:bg-transparent">
      <a
        href="#main-content"
        className="sr-only rounded-md bg-background px-3 py-2 text-sm font-medium focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50"
      >
        {t("app.skipToMain")}
      </a>

      <div className="flex min-h-screen dark:bg-[var(--app-shell-surface)]">
        <aside className="hidden w-[320px] shrink-0 xl:w-[348px] md:flex md:flex-col" aria-label={t("nav.primary")}>
          <SidebarContent
            user={user}
            onLogout={handleLogout}
            onOpenChat={handleOpenChat}
            chatOpen={chatOpen}
            aiReady={Boolean(aiReady)}
            quickActions={quickActions}
            connectedMerchantCount={globalSyncConnectors.length}
            topMerchantLabels={sidebarMerchantLabels}
            lastUpdatedLabel={lastUpdatedLabel}
          />
        </aside>

        <div
          className={cn(
            "flex min-h-screen flex-1 flex-col transition-[padding-right] duration-200",
            chatOpen ? "md:pr-[var(--chat-panel-width)]" : ""
          )}
          style={
            {
              "--chat-panel-width": `${chatPanelWidth}px`
            } as CSSProperties
          }
        >
          <header className="sticky top-0 z-30 border-b border-border/50 bg-background/88 backdrop-blur-xl dark:bg-[var(--app-header-surface)]">
            <div className="mx-auto flex w-full max-w-[1720px] items-center gap-3 px-4 py-4 md:px-6 lg:px-8">
              <div className="md:hidden">
                <Sheet>
                  <SheetTrigger asChild>
                    <Button variant="ghost" size="icon" aria-label={t("app.aria.openNavigationMenu")}>
                      <Menu className="h-5 w-5" />
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="left" className="w-80 max-w-[85vw] p-0">
                    <SidebarContent
                      user={user}
                      onLogout={handleLogout}
                      onOpenChat={() => {
                        setChatOpen(true);
                      }}
                      chatOpen={chatOpen}
                      aiReady={Boolean(aiReady)}
                      quickActions={quickActions}
                      connectedMerchantCount={globalSyncConnectors.length}
                      topMerchantLabels={sidebarMerchantLabels}
                      lastUpdatedLabel={lastUpdatedLabel}
                    />
                  </SheetContent>
                </Sheet>
              </div>

              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-2">
                  {activeNavItem ? <activeNavItem.icon className="h-4 w-4 shrink-0 text-muted-foreground" /> : null}
                  <h1 className="truncate text-base font-semibold tracking-[-0.02em]">
                    {t(activeNavItem?.labelKey ?? "app.defaultPageTitle")}
                  </h1>
                </div>
                <p className="mt-1 hidden text-sm text-muted-foreground lg:block">
                  {t("app.header.desktopSubtitle")}
                </p>
              </div>

              <div className="ml-auto flex items-center gap-2">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="hidden h-12 rounded-2xl px-4 text-sm lg:flex">
                      <CalendarCheck className="mr-2 h-4 w-4" />
                      {topBarRangeLabel}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <DropdownMenuLabel>{datePresetLabel(locale, preset)}</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuRadioGroup value={preset} onValueChange={(value) => setPreset(value as DateRangePreset)}>
                      <DropdownMenuRadioItem value="this_week">{datePresetLabel(locale, "this_week")}</DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="last_7_days">{datePresetLabel(locale, "last_7_days")}</DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="this_month">{datePresetLabel(locale, "this_month")}</DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="last_month">{datePresetLabel(locale, "last_month")}</DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="relative h-12 w-12 rounded-2xl"
                      aria-label={t("app.header.notifications")}
                    >
                      <BellRing className="h-4 w-4" />
                      {unreadNotifications > 0 ? (
                        <span className="absolute right-3 top-3 h-2.5 w-2.5 rounded-full bg-rose-500" />
                      ) : null}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" sideOffset={8} className="w-96 max-w-[calc(100vw-2rem)]">
                    <div className="flex items-center justify-between px-2 py-1.5">
                      <DropdownMenuLabel className="px-0">{t("app.header.notifications")}</DropdownMenuLabel>
                      {unreadNotifications > 0 ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-8 px-2 text-xs"
                          onClick={() => markAllNotificationsReadMutation.mutate()}
                        >
                          {notificationMarkAllReadLabel(locale)}
                        </Button>
                      ) : null}
                    </div>
                    <DropdownMenuSeparator />
                    {notifications.length > 0 ? (
                      notifications.map((notification) => (
                        <DropdownMenuItem
                          key={notification.id}
                          className="items-start gap-3 whitespace-normal py-3"
                          onSelect={() => {
                            if (notification.unread) {
                              markNotificationReadMutation.mutate({ notificationId: notification.id });
                            }
                            if (notification.href) {
                              navigate(notification.href);
                            }
                          }}
                        >
                          <span
                            className={cn(
                              "mt-1 h-2.5 w-2.5 shrink-0 rounded-full",
                              notification.unread ? "bg-rose-500" : "bg-slate-300"
                            )}
                          />
                          <div className="min-w-0 space-y-1">
                            <p className="font-medium leading-5">{notification.title}</p>
                            <p className="text-xs leading-5 text-muted-foreground">{notification.body}</p>
                          </div>
                        </DropdownMenuItem>
                      ))
                    ) : (
                      <div className="px-3 py-4 text-sm text-muted-foreground">
                        {notificationEmptyLabel(locale)}
                      </div>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button asChild size="sm" className="h-12 gap-2 rounded-2xl px-4">
                  <Link to="/add">
                    <Plus className="h-4 w-4" />
                    {t("nav.item.manualImport")}
                  </Link>
                </Button>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="h-12 rounded-2xl px-4" aria-label={t("app.header.preferences")}>
                      <SlidersHorizontal className="h-4 w-4" />
                      <span className="hidden sm:inline">{t("app.header.preferences")}</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" sideOffset={8} className="w-72 sm:w-80">
                    <DropdownMenuLabel>{t("app.header.preferences")}</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>{t("app.header.language")}</DropdownMenuLabel>
                    <DropdownMenuRadioGroup
                      value={locale}
                      onValueChange={(nextLocale) => {
                        if (isSupportedLocale(nextLocale)) {
                          setLocale(nextLocale);
                        }
                      }}
                    >
                      <DropdownMenuRadioItem value="en">{t("app.language.english")}</DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="de">{t("app.language.german")}</DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>{t("app.header.theme")}</DropdownMenuLabel>
                    <DropdownMenuRadioGroup
                      value={theme ?? "system"}
                      onValueChange={(nextTheme) => {
                        if (nextTheme === "light" || nextTheme === "dark" || nextTheme === "system") {
                          setTheme(nextTheme);
                        }
                      }}
                    >
                      <DropdownMenuRadioItem value="system">{t("app.theme.system")}</DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="light">{t("app.theme.light")}</DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="dark">{t("app.theme.dark")}</DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                    <DropdownMenuSeparator />
                    <DropdownMenuLabel>{t("app.header.scope")}</DropdownMenuLabel>
                    <DropdownMenuRadioGroup
                      value={scope}
                      onValueChange={(nextScope) => {
                        if (nextScope === "personal" || nextScope === "family") {
                          setScope(nextScope);
                        }
                      }}
                    >
                      <DropdownMenuRadioItem value="personal">{t("app.scope.personal")}</DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="family">{t("app.scope.family")}</DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                    <DropdownMenuSeparator />
                    {canOpenControlCenter ? (
                      <>
                        <DropdownMenuItem onClick={handleOpenControlCenter}>
                          {controlCenterMenuLabel(locale)}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                      </>
                    ) : null}
                    <DropdownMenuItem onClick={handleLogout}>{t("action.signOut")}</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          </header>

          <main
            id="main-content"
            tabIndex={-1}
            className="mx-auto w-full max-w-[1720px] flex-1 space-y-6 px-4 py-6 md:px-6 lg:px-8 lg:py-8"
          >
            <DesktopRedirectBanner onDismiss={dismissDesktopRedirectNotice} />
            {globalSyncStatus && !globalSyncDismissed ? (
            <SyncStatusBanner
              sourceLabel={globalSyncStatus.sourceLabel}
              status={globalSyncStatus.status}
              onDismiss={
                  globalSyncStatus.status.status === "running" || globalSyncRunId === null
                    ? undefined
                    : () => setDismissedSyncRun(globalSyncRunId)
                }
              />
            ) : null}
            <Outlet />
          </main>
        </div>

        <ChatPanel
          open={chatOpen}
          onOpenChange={setChatOpen}
          enabled={Boolean(aiReady)}
          panelWidth={chatPanelWidth}
          onPanelWidthChange={setChatPanelWidth}
          pageContext={sidePanelPageContext}
        />
      </div>
    </div>
  );
}
