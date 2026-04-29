import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDateRangeContext } from "@/app/date-range-context";
import { AppProviders } from "@/app/providers";

vi.mock("sonner", () => ({
  toast: {
    warning: vi.fn()
  }
}));

vi.mock("@/components/ui/sonner", () => ({
  Toaster: () => null
}));

function DateRangeProbe() {
  const { preset, fromDate, toDate, setPreset } = useDateRangeContext();
  return (
    <div>
      <span>{preset}</span>
      <span>{fromDate}</span>
      <span>{toDate}</span>
      <button type="button" onClick={() => setPreset("this_month")}>
        Select month
      </button>
    </div>
  );
}

describe("AppProviders", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 3, 28, 12, 0, 0));
    const storage = new Map<string, string>();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn()
      }))
    });
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      writable: true,
      value: {
        getItem: vi.fn((key: string) => storage.get(key) ?? null),
        setItem: vi.fn((key: string, value: string) => {
          storage.set(key, value);
        }),
        removeItem: vi.fn((key: string) => {
          storage.delete(key);
        }),
        clear: vi.fn(() => {
          storage.clear();
        })
      }
    });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("provides the desktop date range context to the signed-in shell tree", () => {
    render(
      <AppProviders>
        <DateRangeProbe />
      </AppProviders>
    );

    expect(screen.getByText("this_week")).toBeInTheDocument();
    expect(screen.getByText("2026-04-27")).toBeInTheDocument();
    expect(screen.getByText("2026-05-03")).toBeInTheDocument();
  });

  it("updates the resolved date range when a preset changes", () => {
    render(
      <AppProviders>
        <DateRangeProbe />
      </AppProviders>
    );

    fireEvent.click(screen.getByRole("button", { name: "Select month" }));

    expect(screen.getByText("this_month")).toBeInTheDocument();
    expect(screen.getByText("2026-04-01")).toBeInTheDocument();
    expect(screen.getByText("2026-04-30")).toBeInTheDocument();
  });
});
