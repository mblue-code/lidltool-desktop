import { z } from "zod";

import { ApiDomainError, ApiValidationError } from "@/lib/api-errors";
import { normalizeApiWarnings, type ApiWarning } from "@/lib/api-messages";

const baseEnvelopeSchema = z.object({
  ok: z.boolean(),
  result: z.unknown().nullable(),
  warnings: z.array(z.string()).default([]),
  warning_details: z
    .array(
      z.object({
        code: z.string().nullable().optional(),
        message: z.string()
      })
    )
    .default([]),
  error: z.string().nullable().default(null),
  error_code: z.string().nullable().default(null)
});

export function parseEnvelopeResult<T>(payload: unknown, resultSchema: z.ZodType<T>): {
  result: T;
  warnings: ApiWarning[];
} {
  const envelope = baseEnvelopeSchema.safeParse(payload);
  if (!envelope.success) {
    throw new ApiValidationError(`Invalid API envelope: ${envelope.error.message}`);
  }

  const warnings = normalizeApiWarnings(
    envelope.data.warnings,
    envelope.data.warning_details
  );

  if (!envelope.data.ok || envelope.data.result === null) {
    throw new ApiDomainError(envelope.data.error ?? "Request failed with domain error", warnings, envelope.data.error_code);
  }

  const parsedResult = resultSchema.safeParse(envelope.data.result);
  if (!parsedResult.success) {
    throw new ApiValidationError(`Invalid API payload: ${parsedResult.error.message}`);
  }

  return {
    result: parsedResult.data,
    warnings
  };
}
