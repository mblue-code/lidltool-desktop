import { afterEach, describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { ApiDomainError, ApiTransportError } from "@/lib/api-errors";
import { apiClient } from "@/lib/api-client";
import { subscribeApiWarnings } from "@/lib/api-warnings";
import { setRequestScope } from "@/lib/request-scope";

afterEach(() => {
  setRequestScope("personal");
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("apiClient non-2xx envelope handling", () => {
  it("parses JSON error envelopes on non-2xx responses into ApiDomainError", async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeApiWarnings(listener);

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({
          ok: false,
          result: null,
          warnings: ["api auth credential missing or invalid"],
          warning_details: [
            {
              code: "api_auth_credential_missing_or_invalid",
              message: "api auth credential missing or invalid"
            }
          ],
          error: "backup output directory must be empty: /tmp/backup",
          error_code: "backup_output_directory_not_empty"
        })
      })
    );

    const schema = z.object({ value: z.number() });
    let capturedError: unknown;
    try {
      await apiClient.get("/api/v1/system/backup", schema);
    } catch (error) {
      capturedError = error;
    }

    expect(capturedError).toBeInstanceOf(ApiDomainError);
    expect(capturedError).toMatchObject({
      message: "backup output directory must be empty: /tmp/backup",
      code: "backup_output_directory_not_empty"
    });
    expect(listener).toHaveBeenCalledWith({
      code: "api_auth_credential_missing_or_invalid",
      message: "api auth credential missing or invalid"
    });

    unsubscribe();
  });

  it("keeps transport errors for non-JSON non-2xx responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new SyntaxError("Unexpected token <");
        }
      })
    );

    const schema = z.object({ value: z.number() });
    let capturedError: unknown;
    try {
      await apiClient.get("/api/v1/system/backup", schema);
    } catch (error) {
      capturedError = error;
    }

    expect(capturedError).toBeInstanceOf(ApiTransportError);
    expect(capturedError).toMatchObject({
      message: "Request failed with status 500",
      status: 500
    });
  });
});
