import { beforeEach, describe, expect, it } from "vitest";

import { formatEurFromCents, formatMonthName, formatMonthYear, formatNumber } from "@/utils/format";

const LOCALE_STORAGE_KEY = "app.locale";

describe("format helpers", () => {
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
  });

  it("formats currency and month labels in english", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");

    expect(formatEurFromCents(12345)).toBe("€123.45");
    expect(formatNumber(1234.5, { minimumFractionDigits: 1, maximumFractionDigits: 1 })).toBe("1,234.5");
    expect(formatMonthName(3)).toBe("March");
    expect(formatMonthYear(new Date("2026-03-15T12:00:00Z"))).toBe("March 2026");
  });

  it("formats currency and month labels in german", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "de");

    expect(formatEurFromCents(12345)).toBe("123,45 €");
    expect(formatNumber(1234.5, { minimumFractionDigits: 1, maximumFractionDigits: 1 })).toBe("1.234,5");
    expect(formatMonthName(3)).toBe("März");
    expect(formatMonthYear(new Date("2026-03-15T12:00:00Z"))).toBe("März 2026");
  });
});
