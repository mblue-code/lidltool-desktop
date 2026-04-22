import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  const { preset, fromDate, toDate } = useDateRangeContext();
  return (
    <div>
      <span>{preset}</span>
      <span>{fromDate}</span>
      <span>{toDate}</span>
    </div>
  );
}

describe("AppProviders", () => {
  beforeEach(() => {
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

  it("provides the desktop date range context to the signed-in shell tree", () => {
    render(
      <AppProviders>
        <DateRangeProbe />
      </AppProviders>
    );

    expect(screen.getByText("this_week")).toBeInTheDocument();
  });
});
