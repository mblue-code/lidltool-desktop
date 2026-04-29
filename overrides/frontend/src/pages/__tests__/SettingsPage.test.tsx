import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { SettingsPage } from "../SettingsPage";

vi.mock("@/api/users", () => ({
  fetchCurrentUser: vi.fn(async () => ({
    user_id: "u1",
    username: "alice",
    display_name: null,
    is_admin: false,
    preferred_locale: "de"
  })),
  updateCurrentUserLocale: vi.fn()
}));

function renderPage(): void {
  render(
    <MemoryRouter>
      <I18nProvider>
        <SettingsPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    const storage = new Map<string, string>();
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
    window.localStorage.setItem("app.locale", "de");
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the settings hub in german", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Einstellungen" })).toBeInTheDocument();
    expect(screen.getByText("Anbindungsverwaltung")).toBeInTheDocument();
    expect(screen.getByText("KI-Assistent")).toBeInTheDocument();
    expect(screen.getByText("Benutzer und Zugriff")).toBeInTheDocument();
    expect(screen.getByText("Mobile Kopplung")).toBeInTheDocument();
    expect(screen.getByText("Darstellung")).toBeInTheDocument();
    expect(screen.getByText("Desktop-Konfiguration")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Öffnen" })).toHaveLength(6);
    expect(screen.getByText("Telefon koppeln")).toBeInTheDocument();
  });
});
