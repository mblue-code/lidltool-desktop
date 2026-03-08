import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import {
  Activity,
  CalendarCheck,
  Database,
  GitCompare,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageCircle,
  Package,
  Percent,
  ReceiptText,
  Search,
  ShieldCheck,
  TrendingUp,
  Users,
  Wallet,
  Zap,
  type LucideIcon
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";

import { fetchAISettings } from "@/api/aiSettings";
import { getSidePanelPageContext } from "@/agent/page-context";
import { logout } from "@/api/auth";
import type { CurrentUser } from "@/api/users";
import { preloadRouteModule } from "@/app/page-loaders";
import { ChatPanel } from "@/components/ChatPanel";
import { useAccessScope } from "@/app/scope-provider";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { type TranslationKey, isSupportedLocale, useI18n } from "@/i18n";
import { cn } from "@/lib/utils";

type NavItem = {
  to: string;
  labelKey: TranslationKey;
  icon: LucideIcon;
};

type NavGroup = {
  labelKey: TranslationKey;
  items: NavItem[];
};

const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: "nav.group.analytics",
    items: [
      { to: "/", labelKey: "nav.item.overview", icon: LayoutDashboard },
      { to: "/explore", labelKey: "nav.item.explore", icon: Search },
      { to: "/products", labelKey: "nav.item.products", icon: Package },
      { to: "/compare", labelKey: "nav.item.comparisons", icon: GitCompare },
      { to: "/receipts", labelKey: "nav.item.receipts", icon: ReceiptText },
      { to: "/budget", labelKey: "nav.item.budget", icon: Wallet },
      { to: "/bills", labelKey: "nav.item.bills", icon: CalendarCheck },
      { to: "/patterns", labelKey: "nav.item.patterns", icon: TrendingUp }
    ]
  },
  {
    labelKey: "nav.group.data",
    items: [
      { to: "/quality", labelKey: "nav.item.dataQuality", icon: ShieldCheck },
      { to: "/connectors", labelKey: "nav.item.connectors", icon: Database },
      { to: "/sources", labelKey: "nav.item.sources", icon: Database },
      { to: "/imports/manual", labelKey: "nav.item.manualImport", icon: ReceiptText },
      { to: "/imports/ocr", labelKey: "nav.item.ocrImport", icon: Search },
      { to: "/automations", labelKey: "nav.item.automations", icon: Zap }
    ]
  },
  {
    labelKey: "nav.group.system",
    items: [
      { to: "/chat", labelKey: "nav.item.chat", icon: MessageCircle },
      { to: "/reliability", labelKey: "nav.item.reliability", icon: Activity },
      { to: "/settings/ai", labelKey: "nav.item.aiAssistant", icon: Zap },
      { to: "/settings/users", labelKey: "nav.item.users", icon: Users }
    ]
  }
];

const NAV_ITEMS_FLAT = NAV_GROUPS.flatMap((g) => g.items);
const CHAT_PANEL_WIDTH_STORAGE_KEY = "layout.chat_panel_width";
const CHAT_PANEL_WIDTH_DEFAULT = 420;
const CHAT_PANEL_WIDTH_MIN = 320;
const CHAT_PANEL_WIDTH_MAX = 860;

function clampChatPanelWidth(width: number): number {
  if (!Number.isFinite(width)) {
    return CHAT_PANEL_WIDTH_DEFAULT;
  }
  const viewportWidth = typeof window !== "undefined" ? window.innerWidth : 1440;
  const maxByViewport = Math.max(CHAT_PANEL_WIDTH_MIN, Math.min(CHAT_PANEL_WIDTH_MAX, viewportWidth - 280));
  return Math.min(maxByViewport, Math.max(CHAT_PANEL_WIDTH_MIN, Math.round(width)));
}

function NavItems(): JSX.Element {
  const { t } = useI18n();
  return (
    <nav className="flex flex-col gap-5" aria-label={t("nav.primary")}>
      {NAV_GROUPS.map((group) => (
        <div key={group.labelKey}>
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
                    "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-sidebar-primary text-sidebar-primary-foreground shadow-sm"
                      : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  )
                }
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {t(item.labelKey)}
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
  aiReady
}: {
  user: CurrentUser;
  onLogout: () => void;
  onOpenChat: () => void;
  chatOpen: boolean;
  aiReady: boolean;
}): JSX.Element {
  const { t } = useI18n();
  return (
    <div className="flex h-full flex-col bg-sidebar">
      {/* Brand */}
      <div className="flex items-center gap-3 border-b border-sidebar-border px-4 py-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Percent className="h-4 w-4" />
        </div>
        <div>
          <p className="text-sm font-semibold text-sidebar-foreground">{t("app.brand.title")}</p>
          <p className="text-xs text-sidebar-foreground/50">{t("app.brand.subtitle")}</p>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto px-3 py-4">
        <NavItems />
      </div>

      <div className="px-3 pb-2">
        <Button
          variant="outline"
          className="relative w-full justify-start gap-2"
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

      {/* User + logout */}
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

      {/* Dev-mode environment indicator */}
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

export function AppShell({ user }: AppShellProps): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const { scope, setScope } = useAccessScope();
  const { locale, setLocale, t } = useI18n();
  const [chatOpen, setChatOpen] = useState(false);
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
  const activeNavItem = NAV_ITEMS_FLAT.find((item) =>
    item.to === "/"
      ? location.pathname === "/"
      : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)
  );
  const sidePanelPageContext = getSidePanelPageContext(location.pathname);
  const aiReady =
    aiSettingsQuery.data?.enabled === true &&
    (aiSettingsQuery.data.api_key_set || aiSettingsQuery.data.oauth_connected);

  async function handleLogout() {
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  }

  function handleOpenChat(): void {
    setChatOpen((current) => !current);
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
    const handleResize = () => {
      setChatPanelWidth((current) => clampChatPanelWidth(current));
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div className="min-h-screen bg-muted/30">
      <a
        href="#main-content"
        className="sr-only rounded-md bg-background px-3 py-2 text-sm font-medium focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50"
      >
        {t("app.skipToMain")}
      </a>

      <div className="flex min-h-screen">
        {/* Desktop sidebar */}
        <aside className="hidden w-64 md:flex md:flex-col" aria-label={t("nav.primary")}>
          <SidebarContent
            user={user}
            onLogout={handleLogout}
            onOpenChat={handleOpenChat}
            chatOpen={chatOpen}
            aiReady={Boolean(aiReady)}
          />
        </aside>

        {/* Content area */}
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
          <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur-sm">
            <div className="mx-auto flex w-full max-w-7xl items-center gap-3 px-4 py-3 md:px-6">
              {/* Mobile menu trigger */}
              <div className="md:hidden">
                <Sheet>
                  <SheetTrigger asChild>
                    <Button variant="outline" size="icon" aria-label={t("app.aria.openNavigationMenu")}>
                      <Menu className="h-4 w-4" />
                    </Button>
                  </SheetTrigger>
                  <SheetContent side="left" className="w-64 p-0">
                    <SidebarContent
                      user={user}
                      onLogout={handleLogout}
                      onOpenChat={() => {
                        setChatOpen(true);
                      }}
                      chatOpen={chatOpen}
                      aiReady={Boolean(aiReady)}
                    />
                  </SheetContent>
                </Sheet>
              </div>

              {/* Page title with icon */}
              <div className="flex items-center gap-2">
                {activeNavItem ? (
                  <activeNavItem.icon className="h-4 w-4 text-muted-foreground" />
                ) : null}
                <h1 className="text-sm font-semibold">{t(activeNavItem?.labelKey ?? "app.defaultPageTitle")}</h1>
              </div>

              <div className="ml-auto flex items-center gap-2">
                <span className="text-xs font-medium text-muted-foreground">{t("app.header.language")}</span>
                <Select
                  value={locale}
                  onValueChange={(nextLocale) => {
                    if (isSupportedLocale(nextLocale)) {
                      setLocale(nextLocale);
                    }
                  }}
                >
                  <SelectTrigger aria-label={t("app.header.language")} className="h-8 w-[120px] text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">{t("app.language.english")}</SelectItem>
                    <SelectItem value="de">{t("app.language.german")}</SelectItem>
                  </SelectContent>
                </Select>

                <span className="text-xs font-medium text-muted-foreground">{t("app.header.scope")}</span>
                <Select
                  value={scope}
                  onValueChange={(nextScope) => {
                    if (nextScope === "personal" || nextScope === "family") {
                      setScope(nextScope);
                    }
                  }}
                >
                  <SelectTrigger aria-label={t("app.header.scope")} className="h-8 w-[130px] text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="personal">{t("app.scope.personal")}</SelectItem>
                    <SelectItem value="family">{t("app.scope.family")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </header>

          <main
            id="main-content"
            tabIndex={-1}
            className="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-6 md:px-6"
          >
            <Outlet />
          </main>
        </div>
      </div>
      <ChatPanel
        open={chatOpen}
        onOpenChange={setChatOpen}
        enabled={Boolean(aiReady)}
        panelWidth={chatPanelWidth}
        onPanelWidthChange={(next) => setChatPanelWidth(clampChatPanelWidth(next))}
        pageContext={sidePanelPageContext}
      />
    </div>
  );
}
