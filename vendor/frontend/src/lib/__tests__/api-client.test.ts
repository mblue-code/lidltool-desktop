import { describe, expect, it, vi, afterEach } from "vitest";
import { z } from "zod";

import { ApiDomainError } from "@/lib/api-errors";
import { apiClient } from "@/lib/api-client";
import { subscribeApiWarnings } from "@/lib/api-warnings";
import { setRequestScope } from "@/lib/request-scope";

afterEach(() => {
  setRequestScope("personal");
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("apiClient warning handling", () => {
  it("emits envelope warnings and deduplicates repeated warning messages", async () => {
    const warning = `warning-success-${Date.now()}`;
    const expectedWarning = { code: null, message: warning };
    const listener = vi.fn();
    const unsubscribe = subscribeApiWarnings(listener);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          result: { value: 7 },
          warnings: [warning],
          error: null
        })
      })
    );

    const schema = z.object({ value: z.number() });
    await expect(apiClient.get("/api/v1/dashboard/cards", schema)).resolves.toEqual({ value: 7 });
    await expect(apiClient.get("/api/v1/dashboard/cards", schema)).resolves.toEqual({ value: 7 });

    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(expectedWarning);
    unsubscribe();
  });

  it("emits domain warnings before throwing ApiDomainError", async () => {
    const warning = `warning-domain-${Date.now()}`;
    const expectedWarning = { code: null, message: warning };
    const listener = vi.fn();
    const unsubscribe = subscribeApiWarnings(listener);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: false,
          result: null,
          warnings: [warning],
          error: "Domain failure"
        })
      })
    );

    const schema = z.object({ value: z.number() });
    await expect(apiClient.get("/api/v1/dashboard/cards", schema)).rejects.toBeInstanceOf(ApiDomainError);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(expectedWarning);
    unsubscribe();
  });

  it("prefers structured warning details when codes are present", async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeApiWarnings(listener);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          result: { value: 7 },
          warnings: ["api auth credential missing or invalid"],
          warning_details: [
            {
              code: "api_auth_credential_missing_or_invalid",
              message: "api auth credential missing or invalid"
            }
          ],
          error: null,
          error_code: null
        })
      })
    );

    const schema = z.object({ value: z.number() });
    await expect(apiClient.get("/api/v1/dashboard/cards", schema)).resolves.toEqual({ value: 7 });

    expect(listener).toHaveBeenCalledWith({
      code: "api_auth_credential_missing_or_invalid",
      message: "api auth credential missing or invalid"
    });
    unsubscribe();
  });
});

describe("apiClient scope wiring", () => {
  it("adds family scope query param automatically", async () => {
    setRequestScope("family");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        result: { value: 7 },
        warnings: [],
        error: null
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const schema = z.object({ value: z.number() });
    await expect(apiClient.get("/api/v1/dashboard/cards", schema, { year: 2026 })).resolves.toEqual({
      value: 7
    });

    const calledUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(calledUrl.searchParams.get("scope")).toBe("family");
    expect(calledUrl.searchParams.get("year")).toBe("2026");
  });

  it("does not include scope query param while personal scope is active", async () => {
    setRequestScope("personal");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        result: { value: 7 },
        warnings: [],
        error: null
      })
    });
    vi.stubGlobal("fetch", fetchMock);

    const schema = z.object({ value: z.number() });
    await expect(apiClient.get("/api/v1/dashboard/cards", schema, { year: 2026 })).resolves.toEqual({
      value: 7
    });

    const calledUrl = new URL(String(fetchMock.mock.calls[0]?.[0]));
    expect(calledUrl.searchParams.get("scope")).toBeNull();
    expect(calledUrl.searchParams.get("year")).toBe("2026");
  });
});
