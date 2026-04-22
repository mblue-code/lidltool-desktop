import { describe, expect, it } from "vitest";

import { tForLocale } from "@/i18n";
import { ApiDomainError } from "@/lib/api-errors";
import { resolveApiErrorMessage, resolveApiWarningMessage } from "@/lib/backend-messages";

describe("backend message localization", () => {
  it("maps known backend codes to translated copy", () => {
    const error = new ApiDomainError(
      "authentication required",
      [],
      "auth_required"
    );

    expect(resolveApiErrorMessage(error, (key, variables) => tForLocale("en", key, variables))).toBe(
      "Please sign in to continue."
    );
    expect(resolveApiErrorMessage(error, (key, variables) => tForLocale("de", key, variables))).toBe(
      "Bitte melden Sie sich an, um fortzufahren."
    );
  });

  it("falls back to backend prose when the code is unknown", () => {
    const error = new ApiDomainError(
      "Connector preview not available in this environment.",
      [],
      "connector_preview_not_available"
    );

    expect(
      resolveApiErrorMessage(error, (key, variables) => tForLocale("de", key, variables))
    ).toBe("Connector preview not available in this environment.");

    expect(
      resolveApiWarningMessage(
        {
          code: "connector_preview_not_available",
          message: "Connector preview not available in this environment."
        },
        (key, variables) => tForLocale("de", key, variables)
      )
    ).toBe("Connector preview not available in this environment.");
  });

  it("uses the provided fallback when neither code nor prose is usable", () => {
    const error = new ApiDomainError("", [], null);

    expect(
      resolveApiErrorMessage(
        error,
        (key, variables) => tForLocale("en", key, variables),
        "Something went wrong."
      )
    ).toBe("Something went wrong.");
  });
});
