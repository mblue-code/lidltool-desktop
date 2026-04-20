export type ParsedOptionalEuroAmount = {
  cents: number | null;
  normalized: string;
  valid: boolean;
};

function stripEuroDecorations(raw: string): string {
  return raw.trim().replace(/\s+/g, "").replace(/^€/, "").replace(/€$/, "");
}

export function parseOptionalEuroAmountToCents(raw: string): ParsedOptionalEuroAmount {
  const normalized = stripEuroDecorations(raw);
  if (!normalized) {
    return { cents: null, normalized: "", valid: true };
  }

  const match = normalized.match(/^(\d+)(?:[.,](\d{1,2}))?$/);
  if (!match) {
    return { cents: null, normalized, valid: false };
  }

  const euros = Number(match[1]);
  const hasFractionalDigits = match[2] !== undefined;
  const fractional = (match[2] ?? "").padEnd(2, "0");
  const cents = euros * 100 + Number(fractional || "0");
  const canonical = hasFractionalDigits ? `${euros}.${fractional}` : String(euros);

  return { cents, normalized: canonical, valid: true };
}

export function formatEuroInputFromCents(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "";
  }

  const cents = Math.trunc(value);
  const absoluteCents = Math.abs(cents);
  const euros = Math.trunc(absoluteCents / 100);
  const fractional = absoluteCents % 100;
  const prefix = cents < 0 ? "-" : "";

  if (fractional === 0) {
    return `${prefix}${euros}`;
  }

  return `${prefix}${euros}.${String(fractional).padStart(2, "0")}`;
}
