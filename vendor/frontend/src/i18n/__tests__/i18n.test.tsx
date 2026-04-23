import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiTransportError } from "@/lib/api-errors";
import { I18nProvider, localizeNode, tForLocale, useI18n } from "@/i18n";

const mocks = vi.hoisted(() => ({
  fetchCurrentUserMock: vi.fn(),
  updateCurrentUserLocaleMock: vi.fn()
}));

vi.mock("@/api/users", () => ({
  fetchCurrentUser: mocks.fetchCurrentUserMock,
  updateCurrentUserLocale: mocks.updateCurrentUserLocaleMock
}));

function LocaleProbe() {
  const { locale, setLocale } = useI18n();
  return (
    <>
      <span data-testid="locale">{locale}</span>
      <button type="button" onClick={() => setLocale("de")}>
        switch
      </button>
    </>
  );
}

describe("i18n plumbing", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    const storage = new Map<string, string>();
    const localeListeners = new Set<(locale: string) => void>();
    let desktopLocale = "en";
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => {
          storage.set(key, value);
        },
        removeItem: (key: string) => {
          storage.delete(key);
        }
      }
    });
    Object.defineProperty(window, "desktopApi", {
      configurable: true,
      value: {
        getLocale: vi.fn(async () => desktopLocale),
        setLocale: vi.fn(async (nextLocale: string) => {
          desktopLocale = nextLocale;
          localeListeners.forEach((listener) => listener(nextLocale));
        }),
        onLocaleChanged: vi.fn((listener: (locale: string) => void) => {
          localeListeners.add(listener);
          return () => {
            localeListeners.delete(listener);
          };
        })
      }
    });
  });

  it("returns german catalog values for known keys", () => {
    expect(tForLocale("de", "nav.item.overview")).toBe("Übersicht");
    expect(tForLocale("de", "common.changes")).toBe("Änderungen");
  });

  it("returns explicit launch-critical keys in both locales", () => {
    expect(tForLocale("en", "pages.connectors.title")).toBe("Connector Setup");
    expect(tForLocale("de", "pages.connectors.title")).toBe("Anbindungen einrichten");
    expect(tForLocale("en", "pages.chatWorkspace.send")).toBe("Send");
    expect(tForLocale("de", "pages.chatWorkspace.send")).toBe("Senden");
  });

  it("keeps unknown literal text unchanged and translates known literals", () => {
    expect(localizeNode(" Close ", "de")).toBe(" Schließen ");
    expect(localizeNode("Custom merchant", "de")).toBe("Custom merchant");
  });

  it("localizes child text within react elements", () => {
    const element = localizeNode(<span>Open</span>, "de") as React.ReactElement<{ children: string }>;
    expect(element.props.children).toEqual(["Öffnen"]);
  });

  it("prefers the signed-in locale over local storage", async () => {
    window.localStorage.setItem("app.locale", "de");
    mocks.fetchCurrentUserMock.mockResolvedValue({
      user_id: "u1",
      username: "alice",
      display_name: "Alice",
      is_admin: false,
      preferred_locale: "en"
    });

    render(
      <I18nProvider>
        <LocaleProbe />
      </I18nProvider>
    );

    await waitFor(() => {
      expect(document.documentElement.lang).toBe("en");
    });
  });

  it("keeps the local preference when the signed-in user has no stored locale", async () => {
    window.localStorage.setItem("app.locale", "de");
    mocks.fetchCurrentUserMock.mockResolvedValue({
      user_id: "u1",
      username: "alice",
      display_name: "Alice",
      is_admin: false,
      preferred_locale: null
    });

    render(
      <I18nProvider>
        <LocaleProbe />
      </I18nProvider>
    );

    await waitFor(() => {
      expect(document.documentElement.lang).toBe("de");
    });
  });

  it("persists locale changes for signed-in users", async () => {
    mocks.fetchCurrentUserMock.mockResolvedValue({
      user_id: "u1",
      username: "alice",
      display_name: "Alice",
      is_admin: false,
      preferred_locale: "en"
    });
    mocks.updateCurrentUserLocaleMock.mockResolvedValue({ preferred_locale: "de" });

    render(
      <I18nProvider>
        <LocaleProbe />
      </I18nProvider>
    );

    await waitFor(() => {
      expect(document.documentElement.lang).toBe("en");
    });

    fireEvent.click(screen.getByRole("button", { name: "switch" }));

    await waitFor(() => {
      expect(mocks.updateCurrentUserLocaleMock).toHaveBeenCalledWith("de");
      expect(document.documentElement.lang).toBe("de");
    });
  });

  it("falls back to local or browser state when auth lookup returns 401", async () => {
    window.localStorage.setItem("app.locale", "de");
    mocks.fetchCurrentUserMock.mockRejectedValue(new ApiTransportError(401, "authentication required"));

    render(
      <I18nProvider>
        <LocaleProbe />
      </I18nProvider>
    );

    await waitFor(() => {
      expect(document.documentElement.lang).toBe("de");
    });
  });

  it("prefers the desktop shell locale over stale app-local storage", async () => {
    window.localStorage.setItem("app.locale", "en");
    window.desktopApi?.setLocale?.("de");
    mocks.fetchCurrentUserMock.mockRejectedValue(new ApiTransportError(401, "authentication required"));

    render(
      <I18nProvider>
        <LocaleProbe />
      </I18nProvider>
    );

    await waitFor(() => {
      expect(document.documentElement.lang).toBe("de");
    });
  });

  it("syncs locale changes back to the desktop shell bridge", async () => {
    mocks.fetchCurrentUserMock.mockRejectedValue(new ApiTransportError(401, "authentication required"));

    render(
      <I18nProvider>
        <LocaleProbe />
      </I18nProvider>
    );

    fireEvent.click(screen.getByRole("button", { name: "switch" }));

    await waitFor(() => {
      expect(window.desktopApi?.setLocale).toHaveBeenCalledWith("de");
      expect(document.documentElement.lang).toBe("de");
    });
  });
});
