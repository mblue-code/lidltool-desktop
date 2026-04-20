import { describe, expect, it } from "vitest";

import { formatEuroInputFromCents, parseOptionalEuroAmountToCents } from "@/utils/currency";

describe("currency helpers", () => {
  it("parses euro amounts to cents without floating point math", () => {
    expect(parseOptionalEuroAmountToCents("12")).toEqual({
      cents: 1200,
      normalized: "12",
      valid: true
    });
    expect(parseOptionalEuroAmountToCents("12.50")).toEqual({
      cents: 1250,
      normalized: "12.50",
      valid: true
    });
    expect(parseOptionalEuroAmountToCents("12,5")).toEqual({
      cents: 1250,
      normalized: "12.50",
      valid: true
    });
  });

  it("treats empty amounts as optional and rejects invalid cent-like input", () => {
    expect(parseOptionalEuroAmountToCents("")).toEqual({
      cents: null,
      normalized: "",
      valid: true
    });
    expect(parseOptionalEuroAmountToCents("12.345")).toEqual({
      cents: null,
      normalized: "12.345",
      valid: false
    });
  });

  it("formats cent values back to canonical euro input values", () => {
    expect(formatEuroInputFromCents(1200)).toBe("12");
    expect(formatEuroInputFromCents(1250)).toBe("12.50");
    expect(formatEuroInputFromCents(50)).toBe("0.50");
  });
});
