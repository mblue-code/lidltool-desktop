import { beforeEach, describe, expect, it } from "vitest";

import { formatCentsForInput, parseEuroInputToCents } from "@/utils/money-input";

const LOCALE_STORAGE_KEY = "app.locale";

describe("money input helpers", () => {
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

  it("parses euro input strings into cents", () => {
    expect(parseEuroInputToCents("12,99")).toBe(1299);
    expect(parseEuroInputToCents("12.99")).toBe(1299);
    expect(parseEuroInputToCents("12")).toBe(1200);
    expect(parseEuroInputToCents("0,50")).toBe(50);
    expect(parseEuroInputToCents(",99")).toBe(99);
  });

  it("rejects empty and over-precise euro input", () => {
    expect(parseEuroInputToCents("")).toBeNull();
    expect(parseEuroInputToCents("12,999")).toBeNull();
    expect(parseEuroInputToCents("-1,00")).toBeNull();
    expect(parseEuroInputToCents("-1,00", { allowNegative: true })).toBe(-100);
  });

  it("formats cents for english input fields", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "en");

    expect(formatCentsForInput(1299)).toBe("12.99");
    expect(formatCentsForInput(1200)).toBe("12.00");
    expect(formatCentsForInput(123450)).toBe("1234.50");
  });

  it("formats cents for german input fields", () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, "de");

    expect(formatCentsForInput(1299)).toBe("12,99");
    expect(formatCentsForInput(null)).toBe("");
  });
});
