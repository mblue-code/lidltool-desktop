import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppProviders } from "@/app/providers";
import { AppearanceSettingsPage } from "../AppearanceSettingsPage";

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
      <AppProviders>
        <AppearanceSettingsPage />
      </AppProviders>
    </MemoryRouter>
  );
}

describe("AppearanceSettingsPage", () => {
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
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        media: "",
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn()
      }))
    });
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn(async () => {})
      }
    });
    window.localStorage.setItem("app.locale", "de");
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the appearance editor in german and persists preset changes", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Darstellung" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hell" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dunkel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "System" })).toBeInTheDocument();
    expect(screen.getByText("Tokyo Night")).toBeInTheDocument();
    expect(screen.getByText("Codex")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Codex/ }));

    await waitFor(() => {
      expect(window.localStorage.getItem("app.appearance.v1")).toContain("\"lightPresetId\":\"codex\"");
    });
  });
});
