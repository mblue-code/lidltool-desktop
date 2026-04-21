import type * as React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { LoginPage } from "../LoginPage";
import { SetupPage } from "../SetupPage";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  checkSetupRequired: vi.fn(),
  getSetupStatus: vi.fn(),
  login: vi.fn(),
  setup: vi.fn(),
  fetchCurrentUser: vi.fn()
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mocks.navigate
  };
});

vi.mock("@/api/auth", () => ({
  checkSetupRequired: mocks.checkSetupRequired,
  getSetupStatus: mocks.getSetupStatus,
  login: mocks.login,
  setup: mocks.setup
}));

vi.mock("@/api/users", () => ({
  fetchCurrentUser: mocks.fetchCurrentUser
}));

function renderPage(ui: React.JSX.Element): void {
  render(
    <MemoryRouter>
      <I18nProvider>{ui}</I18nProvider>
    </MemoryRouter>
  );
}

describe("auth entry pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
    window.desktopApi = undefined;
  });

  afterEach(() => {
    cleanup();
  });

  it("redirects login to setup when the instance still needs its first admin", async () => {
    mocks.checkSetupRequired.mockResolvedValue(true);

    renderPage(<LoginPage />);

    await waitFor(() => {
      expect(mocks.navigate).toHaveBeenCalledWith("/setup", { replace: true });
    });
  });

  it("keeps the setup form accessible while setup is still required", async () => {
    mocks.getSetupStatus.mockResolvedValue({ required: true, bootstrap_token_required: false });

    renderPage(<SetupPage />);

    expect(await screen.findByRole("heading", { name: "Welcome to Lidl Receipts" })).toBeInTheDocument();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it("reloads sign-in after a successful desktop restore from setup", async () => {
    const originalLocation = window.location;
    const assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        ...originalLocation,
        assign: assignSpy
      }
    });
    mocks.getSetupStatus.mockResolvedValue({ required: true, bootstrap_token_required: false });
    window.desktopApi = {
      runImport: vi.fn().mockResolvedValue({
        ok: true,
        command: "desktop:import",
        args: [],
        exitCode: 0,
        stdout: "",
        stderr: ""
      })
    } as typeof window.desktopApi;

    renderPage(<SetupPage />);

    fireEvent.change(await screen.findByLabelText("Backup directory"), {
      target: { value: "/tmp/desktop-backup" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Restore backup and sign in" }));

    await waitFor(() => {
      expect(window.desktopApi?.runImport).toHaveBeenCalled();
      expect(assignSpy).toHaveBeenCalledWith("/login?restored=1");
    });
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation
    });
  });
});
