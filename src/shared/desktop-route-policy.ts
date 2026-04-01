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
  { route: "/login", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/setup", availability: "adapted", navVisible: false, redirectTo: null, reason: "desktop_override" },
  { route: "/explore", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/products", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/offers", availability: "unsupported", navVisible: false, redirectTo: "/", reason: "desktop_out_of_scope" },
  { route: "/compare", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/quality", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/connectors", availability: "adapted", navVisible: true, redirectTo: null, reason: "desktop_override" },
  { route: "/sources", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/add", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/imports/manual", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/imports/ocr", availability: "preview", navVisible: true, redirectTo: null, reason: "desktop_preview" },
  { route: "/budget", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/bills", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/patterns", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/receipts", availability: "enabled", navVisible: true, redirectTo: null, reason: null },
  { route: "/transactions", availability: "enabled", navVisible: false, redirectTo: null, reason: null },
  { route: "/documents/upload", availability: "preview", navVisible: false, redirectTo: null, reason: "desktop_preview" },
  { route: "/review-queue", availability: "preview", navVisible: false, redirectTo: null, reason: "desktop_preview" },
  { route: "/automations", availability: "unsupported", navVisible: false, redirectTo: "/", reason: "scheduler_host_required" },
  { route: "/automation-inbox", availability: "unsupported", navVisible: false, redirectTo: "/", reason: "scheduler_host_required" },
  { route: "/chat", availability: "adapted", navVisible: true, redirectTo: null, reason: "desktop_override" },
  { route: "/reliability", availability: "unsupported", navVisible: false, redirectTo: "/", reason: "operator_surface" },
  { route: "/settings/ai", availability: "adapted", navVisible: true, redirectTo: null, reason: "desktop_override" },
  { route: "/settings/users", availability: "adapted", navVisible: true, redirectTo: null, reason: "desktop_override" }
];

export const DESKTOP_CAPABILITIES: DesktopCapabilities = {
  routes: DESKTOP_ROUTE_CAPABILITIES
};
