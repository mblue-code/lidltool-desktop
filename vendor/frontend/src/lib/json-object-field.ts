import { z } from "zod";

export function jsonObjectStringSchema(fieldLabel: string) {
  return z
    .string()
    .trim()
    .transform((value, context): Record<string, unknown> => {
      if (!value) {
        return {};
      }

      let parsed: unknown;
      try {
        parsed = JSON.parse(value);
      } catch {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: `${fieldLabel} must be valid JSON.`
        });
        return z.NEVER;
      }

      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          message: `${fieldLabel} must be a JSON object.`
        });
        return z.NEVER;
      }

      return parsed as Record<string, unknown>;
    });
}
