import { z } from "zod";

import { ApiDomainError, ApiValidationError } from "@/lib/api-errors";

const baseEnvelopeSchema = z.object({
  ok: z.boolean(),
  result: z.unknown().nullable(),
  warnings: z.array(z.string()).default([]),
  error: z.string().nullable().default(null)
});

export function parseEnvelopeResult<T>(payload: unknown, resultSchema: z.ZodType<T>): {
  result: T;
  warnings: string[];
} {
  const envelope = baseEnvelopeSchema.safeParse(payload);
  if (!envelope.success) {
    throw new ApiValidationError(`Invalid API envelope: ${envelope.error.message}`);
  }

  if (!envelope.data.ok || envelope.data.result === null) {
    throw new ApiDomainError(
      envelope.data.error ?? "Request failed with domain error",
      envelope.data.warnings
    );
  }

  const parsedResult = resultSchema.safeParse(envelope.data.result);
  if (!parsedResult.success) {
    throw new ApiValidationError(`Invalid API payload: ${parsedResult.error.message}`);
  }

  return {
    result: parsedResult.data,
    warnings: envelope.data.warnings
  };
}
