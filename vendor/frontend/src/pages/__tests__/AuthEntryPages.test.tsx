import type * as React from "react";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
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

  it("redirects setup to login after initial setup is already complete", async () => {
    mocks.getSetupStatus.mockResolvedValue({ required: false, bootstrap_token_required: false });
    mocks.fetchCurrentUser.mockRejectedValue(new Error("authentication required"));

    renderPage(<SetupPage />);

    await waitFor(() => {
      expect(mocks.navigate).toHaveBeenCalledWith("/login", { replace: true });
    });
  });

  it("keeps the setup form accessible while setup is still required", async () => {
    mocks.getSetupStatus.mockResolvedValue({ required: true, bootstrap_token_required: false });

    renderPage(<SetupPage />);

    expect(await screen.findByRole("heading", { name: "Welcome to Lidl Receipts" })).toBeInTheDocument();
    expect(mocks.navigate).not.toHaveBeenCalled();
  });
});
