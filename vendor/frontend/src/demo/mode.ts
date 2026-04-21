export const DEMO_APP_MODE = "demo_snapshot";

export function isDemoSnapshotMode(): boolean {
  return import.meta.env.VITE_APP_MODE === DEMO_APP_MODE;
}

export const demoUser = {
  user_id: "demo-user",
  username: "demo",
  display_name: "Demo Snapshot",
  is_admin: false,
  preferred_locale: "en" as const
};

export const demoSupportedNavRoutes = new Set([
  "/",
  "/receipts",
  "/connectors",
  "/products",
  "/chat"
]);
