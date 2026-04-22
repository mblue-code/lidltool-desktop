type DesktopRouteAvailability = "enabled" | "adapted" | "preview" | "unsupported";
type DesktopRouteReason =
  | "desktop_override"
  | "desktop_preview"
  | "desktop_out_of_scope"
  | "scheduler_host_required"
  | "operator_surface";

type DesktopRouteCapability = {
  route: string;
  availability: DesktopRouteAvailability;
  navVisible: boolean;
  redirectTo: string | null;
  reason: DesktopRouteReason | null;
};

type DesktopCapabilities = {
  routes: DesktopRouteCapability[];
};

export const DESKTOP_ROUTE_CAPABILITIES: DesktopRouteCapability[] = [
  { route: "/", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/dashboard", availability: "enabled", navVisible: false, redirectTo: "/", reason: null },
  { route: "/login", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/setup", availability: "adapted", navVisible: false, redirectTo: null, reason: "desktop_override" },
  { route: "/transactions", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/receipts", availability: "adapted", navVisible: false, redirectTo: "/transactions", reason: "desktop_override" },
  { route: "/groceries", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/budget", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/bills", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/cash-flow", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/reports", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/goals", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/merchants", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/settings", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/add", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/connectors", availability: "adapted", navVisible: true, redirectTo: null, reason: "desktop_override" },
  { route: "/chat", availability: "adapted", navVisible: true, redirectTo: null, reason: "desktop_override" },
  { route: "/imports/manual", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/imports/ocr", availability: "preview", navVisible: false, redirectTo: null, reason: "desktop_preview" },
  { route: "/sources", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/explore", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/products", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/offers", availability: "unsupported", navVisible: false, redirectTo: "/", reason: "desktop_out_of_scope" },
  { route: "/compare", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/quality", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/patterns", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/documents/upload", availability: "preview", navVisible: false, redirectTo: null, reason: "desktop_preview" },
  { route: "/review-queue", availability: "preview", navVisible: false, redirectTo: null, reason: "desktop_preview" },
  { route: "/automations", availability: "unsupported", navVisible: false, redirectTo: "/", reason: "scheduler_host_required" },
  { route: "/automation-inbox", availability: "unsupported", navVisible: false, redirectTo: "/", reason: "scheduler_host_required" },
  { route: "/reliability", availability: "unsupported", navVisible: false, redirectTo: "/", reason: "operator_surface" },
  { route: "/settings/ai", availability: "adapted", navVisible: false, redirectTo: null, reason: "desktop_override" },
  { route: "/settings/users", availability: "adapted", navVisible: false, redirectTo: null, reason: "desktop_override" }
];

export const DESKTOP_CAPABILITIES: DesktopCapabilities = {
  routes: DESKTOP_ROUTE_CAPABILITIES
};
