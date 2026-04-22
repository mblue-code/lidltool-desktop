import { beforeEach, describe, expect, it } from "vitest";

import { formatEuroInputFromCents, parseEuroInputToCents } from "@/utils/currency";

const LOCALE_STORAGE_KEY = "app.locale";

describe("currency helpers", () => {
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

  it("parses euro-denominated input into cents", () => {
    expect(parseEuroInputToCents("12.34")).toBe(1234);
    expect(parseEuroInputToCents("24,5")).toBe(2450);
    expect(parseEuroInputToCents("1.234,56")).toBe(123456);
    expect(parseEuroInputToCents("1,234.56")).toBe(123456);
    expect(parseEuroInputToCents("1.234")).toBe(123400);
  });

  it("rejects invalid euro-denominated input", () => {
    expect(parseEuroInputToCents("")).toBeUndefined();
    expect(parseEuroInputToCents("abc")).toBeUndefined();
    expect(parseEuroInputToCents("12.3456")).toBeUndefined();
    expect(parseEuroInputToCents("-1")).toBeUndefined();
  });

  it("formats cents for euro-denominated inputs using the active locale", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    expect(formatEuroInputFromCents(1234)).toBe("12.34");

    window.localStorage.setItem(LOCALE_STORAGE_KEY, "de");
    expect(formatEuroInputFromCents(1234)).toBe("12,34");
    expect(formatEuroInputFromCents("")).toBe("");
    expect(formatEuroInputFromCents("invalid")).toBe("");
  });
});
