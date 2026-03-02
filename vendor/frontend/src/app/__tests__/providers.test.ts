import { describe, expect, it } from "vitest";

import { shouldRetryQuery } from "@/app/providers";
import { ApiDomainError, ApiTransportError, ApiValidationError } from "@/lib/api-errors";

describe("shouldRetryQuery", () => {
  it("does not retry domain, validation, or 4xx transport errors", () => {
    expect(shouldRetryQuery(0, new ApiDomainError("domain", []))).toBe(false);
    expect(shouldRetryQuery(0, new ApiValidationError("invalid"))).toBe(false);
    expect(shouldRetryQuery(0, new ApiTransportError(400, "bad request"))).toBe(false);
    expect(shouldRetryQuery(0, new ApiTransportError(404, "not found"))).toBe(false);
  });

  it("retries network and 5xx transport errors with bounded retry count", () => {
    expect(shouldRetryQuery(0, new ApiTransportError(500, "server error"))).toBe(true);
    expect(shouldRetryQuery(0, new ApiTransportError(503, "unavailable"))).toBe(true);
    expect(shouldRetryQuery(0, new TypeError("Failed to fetch"))).toBe(true);

    expect(shouldRetryQuery(2, new ApiTransportError(500, "server error"))).toBe(false);
    expect(shouldRetryQuery(2, new TypeError("Failed to fetch"))).toBe(false);
  });
});
