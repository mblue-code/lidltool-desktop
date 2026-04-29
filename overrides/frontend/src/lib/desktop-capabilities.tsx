import type { ReactNode } from "react";
import { createContext, useContext, useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";

import {
  getDesktopCapabilityBridge,
  type DesktopCapabilities,
  type DesktopRouteAvailability,
  type DesktopRouteCapability,
  type DesktopRouteReason
} from "@/lib/desktop-api";
import { DESKTOP_CAPABILITIES as DEFAULT_DESKTOP_CAPABILITIES } from "@/lib/desktop-route-policy";

const DesktopCapabilitiesContext = createContext<DesktopCapabilities>(DEFAULT_DESKTOP_CAPABILITIES);
const DESKTOP_CAPABILITIES_TIMEOUT_MS = 2_000;

export type DesktopRedirectNotice = {
  requestedPath: string;
  redirectTo: string;
  availability: DesktopRouteAvailability;
  reason: DesktopRouteReason | null;
};

export type DesktopLocationState = {
  desktopRedirectNotice?: DesktopRedirectNotice;
  [key: string]: unknown;
};

type DesktopCapabilityMessage = {
  title: string;
  description: string;
};

function matchesRoute(pathname: string, route: string): boolean {
  if (route === "/") {
    return pathname === "/";
  }
  return pathname === route || pathname.startsWith(`${route}/`);
}

export async function loadDesktopCapabilities(timeoutMs = DESKTOP_CAPABILITIES_TIMEOUT_MS): Promise<DesktopCapabilities> {
  const bridge = getDesktopCapabilityBridge();
  if (!bridge) {
    return DEFAULT_DESKTOP_CAPABILITIES;
  }

  try {
    return await Promise.race([
      bridge.getCapabilities(),
      new Promise<DesktopCapabilities>((resolve) => {
        window.setTimeout(() => resolve(DEFAULT_DESKTOP_CAPABILITIES), timeoutMs);
      })
    ]);
  } catch (error) {
    console.warn("Failed to load desktop capabilities. Falling back to built-in defaults.", error);
    return DEFAULT_DESKTOP_CAPABILITIES;
  }
}

export function DesktopCapabilitiesProvider({
  capabilities,
  children
}: {
  capabilities: DesktopCapabilities;
  children: ReactNode;
}) {
  const [resolvedCapabilities, setResolvedCapabilities] = useState(capabilities);

  useEffect(() => {
    setResolvedCapabilities(capabilities);
  }, [capabilities]);

  useEffect(() => {
    let cancelled = false;

    void loadDesktopCapabilities().then((nextCapabilities) => {
      if (!cancelled) {
        setResolvedCapabilities(nextCapabilities);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <DesktopCapabilitiesContext.Provider value={resolvedCapabilities}>{children}</DesktopCapabilitiesContext.Provider>
  );
}

export function useDesktopCapabilities(): DesktopCapabilities {
  return useContext(DesktopCapabilitiesContext);
}

export function getDefaultDesktopCapabilities(): DesktopCapabilities {
  return DEFAULT_DESKTOP_CAPABILITIES;
}

export function findDesktopRouteCapability(
  capabilities: DesktopCapabilities,
  pathname: string
): DesktopRouteCapability | null {
  const sortedRoutes = [...capabilities.routes].sort((left, right) => right.route.length - left.route.length);
  return sortedRoutes.find((entry) => matchesRoute(pathname, entry.route)) ?? null;
}

export function isDesktopNavRouteVisible(capabilities: DesktopCapabilities, pathname: string): boolean {
  const routeCapability = findDesktopRouteCapability(capabilities, pathname);
  return routeCapability?.navVisible ?? true;
}

export function createDesktopRedirectNotice(
  requestedPath: string,
  capability: DesktopRouteCapability | null
): DesktopRedirectNotice {
  return {
    requestedPath,
    redirectTo: capability?.redirectTo ?? "/",
    availability: capability?.availability ?? "unsupported",
    reason: capability?.reason ?? "desktop_out_of_scope"
  };
}

export function DesktopRouteGate({
  children
}: {
  children: ReactNode;
}) {
  const location = useLocation();
  const desktopCapabilities = useDesktopCapabilities();
  const capability = findDesktopRouteCapability(desktopCapabilities, location.pathname);

  if (capability?.availability !== "unsupported") {
    return <>{children}</>;
  }

  return (
    <Navigate
      to={{ pathname: capability.redirectTo ?? "/", search: location.search, hash: location.hash }}
      replace
      state={{
        desktopRedirectNotice: createDesktopRedirectNotice(location.pathname, capability)
      }}
    />
  );
}

export function getDesktopRedirectMessage(
  locale: "en" | "de",
  notice: DesktopRedirectNotice
): DesktopCapabilityMessage {
  if (locale === "de") {
    switch (notice.reason) {
      case "scheduler_host_required":
        return {
          title: "In Desktop nicht verfugbar",
          description:
            "Automatisierungen und der Automation-Posteingang bleiben im selbst gehosteten Produkt, weil sie einen dauerhaften Scheduler-Host voraussetzen."
        };
      case "operator_surface":
        return {
          title: "In Desktop nicht verfugbar",
          description:
            "Zuverlassigkeits- und Operator-Oberflachen bleiben im selbst gehosteten Produkt und werden im Electron-Desktop nicht angezeigt."
        };
      case "desktop_out_of_scope":
      default:
        return {
          title: "In Desktop nicht verfugbar",
          description:
            "Diese Route bleibt im Desktop-Produkt bewusst ausserhalb des Umfangs. Verwenden Sie stattdessen die lokalen Analyse-, Backup- oder Connector-Seiten."
        };
    }
  }

  switch (notice.reason) {
    case "scheduler_host_required":
      return {
        title: "Not available in desktop",
        description:
          "Automations and the automation inbox stay in the self-hosted product because they require a persistent scheduler host."
      };
    case "operator_surface":
      return {
        title: "Not available in desktop",
        description:
          "Reliability and operator-facing routes stay in the self-hosted product and are not exposed inside Electron."
      };
    case "desktop_out_of_scope":
    default:
      return {
        title: "Not available in desktop",
        description:
          "This route remains out of scope for the desktop product. Use the local analysis, backup, or connector pages instead."
      };
  }
}
