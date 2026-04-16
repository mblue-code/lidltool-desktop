import { useQueries, useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  BellRing,
  CalendarCheck,
  CheckCircle2,
  Database,
  GitCompare,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Menu,
  MessageCircle,
  Package,
  Percent,
  Plus,
  ReceiptText,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  TrendingUp,
  Users,
  X,
  Wallet,
  Zap,
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
import type { CurrentUser } from "@/api/users";
import { getSidePanelPageContext } from "@/agent/page-context";
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
    labelKey: "nav.group.analytics",
    items: [
      { to: "/", labelKey: "nav.item.overview", icon: LayoutDashboard },
      { to: "/receipts", labelKey: "nav.item.receipts", icon: ReceiptText },
      { to: "/add", labelKey: "nav.item.manualImport", icon: Plus },
      { to: "/budget", labelKey: "nav.item.budget", icon: Wallet },
      { to: "/bills", labelKey: "nav.item.bills", icon: CalendarCheck },
      { to: "/connectors", labelKey: "nav.item.connectors", icon: Database }
    ]
  }
];

const ADVANCED_NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.group.data",
    items: [
      { to: "/offers", labelKey: "nav.item.offers", icon: BellRing },
      { to: "/products", labelKey: "nav.item.products", icon: Package },
      { to: "/compare", labelKey: "nav.item.comparisons", icon: GitCompare },
      { to: "/patterns", labelKey: "nav.item.patterns", icon: TrendingUp },
      { to: "/explore", labelKey: "nav.item.explore", icon: Search }
    ]
  },
  {
    labelKey: "nav.group.data",
    items: [
      { to: "/imports/ocr", labelKey: "nav.item.ocrImport", icon: ReceiptText },
      { to: "/quality", labelKey: "nav.item.dataQuality", icon: ShieldCheck },
      { to: "/sources", labelKey: "nav.item.sources", icon: Database },
      { to: "/automations", labelKey: "nav.item.automations", icon: Zap },
      { to: "/chat", labelKey: "nav.item.chat", icon: MessageCircle }
    ]
  },
  {
    labelKey: "nav.group.system",
    items: [
      { to: "/reliability", labelKey: "nav.item.reliability", icon: Activity, adminOnly: true },
      { to: "/settings/ai", labelKey: "nav.item.aiAssistant", icon: Zap, adminOnly: true },
      { to: "/settings/users", labelKey: "nav.item.users", icon: Users, adminOnly: true }
    ]
  }
];

const CHAT_PANEL_WIDTH_STORAGE_KEY = "layout.chat_panel_width";
const ADVANCED_NAV_STORAGE_KEY = "layout.advanced_nav_open";
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

function advancedToggleLabel(locale: "en" | "de", expanded: boolean): string {
  if (locale === "de") {
    return expanded ? "Erweiterte Werkzeuge ausblenden" : "Erweiterte Werkzeuge anzeigen";
  }
  return expanded ? "Hide advanced tools" : "Show advanced tools";
}

function advancedDescription(locale: "en" | "de"): string {
  if (locale === "de") {
    return "Anbindungen, Diagnose und Power-User-Werkzeuge bleiben hier, bis Sie sie brauchen.";
  }
  return "Connectors, diagnostics, and power-user tools stay here until you need them.";
}

function syncBannerStatusLabel(locale: "en" | "de", status: ConnectorSyncStatus["status"]): string {
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
  const Icon =
    status.status === "running"
      ? LoaderCircle
      : status.status === "succeeded"
        ? CheckCircle2
        : AlertCircle;
  const iconClassName =
    status.status === "running"
      ? "text-sky-700 animate-spin"
      : status.status === "succeeded"
        ? "text-emerald-700"
        : "text-destructive";
  const alertClassName =
    status.status === "running"
      ? "border-sky-200 bg-sky-50/80 text-sky-950"
      : status.status === "succeeded"
        ? "border-emerald-200 bg-emerald-50/80 text-emerald-950"
        : "border-destructive/30 bg-destructive/5";
  const progressLabel =
    progress.seen !== null && progress.seen > 0 && progress.total !== null
      ? syncBannerProgressLabel(locale, progress.seen, progress.total)
      : progress.seen !== null && progress.seen > 0
        ? syncBannerProgressLabel(locale, progress.seen, null)
        : null;
  const latestLine = formatSyncLine(locale, progress.latestLine);

  return (
    <Alert className={cn("rounded-xl", alertClassName)}>
      <Icon className={cn("h-4 w-4", iconClassName)} />
      <AlertTitle className="flex items-start justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span>{syncBannerTitle(locale, sourceLabel)}</span>
          <Badge variant={status.status === "failed" ? "destructive" : "secondary"}>
            {syncBannerStatusLabel(locale, status.status)}
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

function NavItems({ groups }: { groups: NavGroup[] }) {
  const { t } = useI18n();

  return (
    <nav className="flex flex-col gap-5" aria-label={t("nav.primary")}>
      {groups.map((group, index) => (
        <div key={`${group.labelKey}-${index}`}>
          <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-sidebar-foreground/40">
            {t(group.labelKey)}
          </p>
          <div className="flex flex-col gap-0.5">
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                onMouseEnter={() => preloadRouteModule(item.to)}
                onFocus={() => preloadRouteModule(item.to)}
                className={({ isActive }) =>
                  cn(
                    "flex items-start gap-2.5 rounded-md px-3 py-2 text-left text-sm font-medium leading-snug transition-colors",
                    isActive
                      ? "bg-sidebar-primary text-sidebar-primary-foreground shadow-sm"
                      : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  )
                }
              >
                <item.icon className="mt-0.5 h-4 w-4 shrink-0" />
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
  showAdvancedNav,
  onToggleAdvancedNav
}: {
  user: CurrentUser;
  onLogout: () => void;
  onOpenChat: () => void;
  chatOpen: boolean;
  aiReady: boolean;
  showAdvancedNav: boolean;
  onToggleAdvancedNav: () => void;
}) {
  const { locale, t } = useI18n();
  const desktopCapabilities = useDesktopCapabilities();
  const visibleRoutes = useMemo(
    () =>
      new Set(
        [...PRIMARY_NAV_GROUPS, ...ADVANCED_NAV_GROUPS]
          .flatMap((group) => group.items)
          .filter((item) => isDesktopNavRouteVisible(desktopCapabilities, item.to))
          .map((item) => item.to)
      ),
    [desktopCapabilities]
  );
  const primaryGroups = filterNavGroups(PRIMARY_NAV_GROUPS, user.is_admin, visibleRoutes);
  const advancedGroups = filterNavGroups(ADVANCED_NAV_GROUPS, user.is_admin, visibleRoutes);

  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className="flex items-center gap-3 border-b border-sidebar-border px-4 py-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Percent className="h-4 w-4" />
        </div>
        <div>
          <p className="text-sm font-semibold text-sidebar-foreground">{t("app.brand.title")}</p>
          <p className="text-xs text-sidebar-foreground/50">{t("app.brand.subtitle")}</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        <NavItems groups={primaryGroups} />

        {advancedGroups.length > 0 ? (
          <div className="mt-6 border-t border-sidebar-border pt-4">
            <Button
              variant="ghost"
            className="h-auto w-full items-start justify-between gap-3 whitespace-normal px-3 py-2.5 text-left leading-snug text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              onClick={onToggleAdvancedNav}
            >
            <span className="min-w-0 flex-1 whitespace-normal">{advancedToggleLabel(locale, showAdvancedNav)}</span>
              <SlidersHorizontal className="h-4 w-4" />
            </Button>
            {showAdvancedNav ? (
              <div className="mt-4">
                <NavItems groups={advancedGroups} />
              </div>
            ) : (
              <p className="px-3 pt-2 text-xs leading-5 text-sidebar-foreground/40">
                {advancedDescription(locale)}
              </p>
            )}
          </div>
        ) : null}
      </div>

      <div className="px-3 pb-2">
        <Button variant="outline" className="relative w-full justify-start gap-2" onClick={onOpenChat}>
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

      <div className="border-t border-sidebar-border px-3 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-sidebar-foreground">
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
            className="h-7 w-7 shrink-0 text-sidebar-foreground/50 hover:text-sidebar-foreground"
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
  const desktopCapabilities = useDesktopCapabilities();
  const { theme, setTheme } = useTheme();
  const navItems = useMemo(
    () =>
      [...PRIMARY_NAV_GROUPS, ...ADVANCED_NAV_GROUPS]
        .flatMap((group) => group.items)
        .filter((item) => isDesktopNavRouteVisible(desktopCapabilities, item.to)),
    [desktopCapabilities]
  );
  const { scope, setScope } = useAccessScope();
  const { locale, setLocale, t } = useI18n();
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
  const [showAdvancedNav, setShowAdvancedNav] = useState<boolean>(() => {
    if (typeof window === "undefined") {
      return false;
    }
    const storage = window.localStorage;
    if (!storage || typeof storage.getItem !== "function") {
      return false;
    }
    return storage.getItem(ADVANCED_NAV_STORAGE_KEY) === "true";
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
  const globalSyncConnectors =
    connectorsQuery.data?.connectors.filter(
      (connector) => connector.supports_sync && connector.install_state === "installed"
    ) ?? [];
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
    if (!storage || typeof storage.setItem !== "function") {
      return;
    }
    storage.setItem(ADVANCED_NAV_STORAGE_KEY, String(showAdvancedNav));
  }, [showAdvancedNav]);

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
    <div className="min-h-screen bg-muted/30 dark:bg-transparent">
      <a
        href="#main-content"
        className="sr-only rounded-md bg-background px-3 py-2 text-sm font-medium focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50"
      >
        {t("app.skipToMain")}
      </a>

      <div className="flex min-h-screen dark:bg-[var(--app-shell-surface)]">
        <aside className="hidden w-72 xl:w-80 md:flex md:flex-col" aria-label={t("nav.primary")}>
          <SidebarContent
            user={user}
            onLogout={handleLogout}
            onOpenChat={handleOpenChat}
            chatOpen={chatOpen}
            aiReady={Boolean(aiReady)}
            showAdvancedNav={showAdvancedNav}
            onToggleAdvancedNav={() => setShowAdvancedNav((current) => !current)}
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
          <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur-sm dark:bg-[var(--app-header-surface)]">
            <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-3 md:px-6">
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
                      showAdvancedNav={showAdvancedNav}
                      onToggleAdvancedNav={() => setShowAdvancedNav((current) => !current)}
                    />
                  </SheetContent>
                </Sheet>
              </div>

              <div className="flex min-w-0 items-center gap-2">
                {activeNavItem ? <activeNavItem.icon className="h-4 w-4 shrink-0 text-muted-foreground" /> : null}
                <h1 className="truncate text-sm font-semibold">{t(activeNavItem?.labelKey ?? "app.defaultPageTitle")}</h1>
              </div>

              <div className="ml-auto flex items-center gap-2">
                    <Button asChild size="sm" className="gap-2">
                  <Link to="/add">
                    <Plus className="h-4 w-4" />
                    {t("nav.item.manualImport")}
                  </Link>
                </Button>

                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" aria-label={t("app.header.preferences")}>
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
            className="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-6 md:px-6"
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
