import type { ApiWarning } from "@/lib/api-messages";

export class ApiTransportError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiTransportError";
    this.status = status;
  }
}

export class ApiDomainError extends Error {
  readonly warnings: ApiWarning[];
  readonly code: string | null;

  constructor(message: string, warnings: ApiWarning[], code: string | null = null) {
    super(message);
    this.name = "ApiDomainError";
    this.warnings = warnings;
    this.code = code;
  }
}

export class ApiValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiValidationError";
  }
}

export function isRetryableApiError(error: unknown): boolean {
  if (error instanceof ApiDomainError || error instanceof ApiValidationError) {
    return false;
  }

  if (error instanceof ApiTransportError) {
    return error.status >= 500 || error.status <= 0;
  }

  // Browser fetch network failures generally throw TypeError.
  return error instanceof TypeError;
}
