export class ApiTransportError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiTransportError";
    this.status = status;
  }
}

export class ApiDomainError extends Error {
  readonly warnings: string[];

  constructor(message: string, warnings: string[]) {
    super(message);
    this.name = "ApiDomainError";
    this.warnings = warnings;
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
