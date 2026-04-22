import { resolveIntlLocale } from "@/i18n";

function stripCurrencyDecorators(value: string): string {
  return value.replace(/\s+/g, "").replace(/[€]/g, "");
}

function normalizeEuroInput(value: string): string | null {
  const trimmed = stripCurrencyDecorators(value.trim());
  if (!trimmed) {
    return null;
  }

  const lastDot = trimmed.lastIndexOf(".");
  const lastComma = trimmed.lastIndexOf(",");
  const decimalIndex = Math.max(lastDot, lastComma);

  if (decimalIndex === -1) {
    return /^\d+$/.test(trimmed) ? trimmed : null;
  }

  const integerPart = trimmed.slice(0, decimalIndex);
  const fractionPart = trimmed.slice(decimalIndex + 1);
  const separators = /[.,]/g;
  const integerDigits = integerPart.replace(separators, "");

  if (!/^\d+$/.test(integerDigits)) {
    return null;
  }

  if (!/^\d*$/.test(fractionPart)) {
    return null;
  }

  if (fractionPart.length === 0) {
    return `${integerDigits}.`;
  }

  if (fractionPart.length <= 2) {
    return `${integerDigits}.${fractionPart}`;
  }

  if (fractionPart.length === 3 && integerPart.length > 0) {
    return `${integerDigits}${fractionPart}`;
  }

  return null;
}

export function parseEuroInputToCents(value: string): number | undefined {
  const normalized = normalizeEuroInput(value);
  if (!normalized) {
    return undefined;
  }

  const parsed = Number(normalized);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return undefined;
  }

  return Math.round(parsed * 100);
}

export function formatEuroInputFromCents(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }

  const numericValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numericValue)) {
    return "";
  }

  return new Intl.NumberFormat(resolveIntlLocale(), {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
    useGrouping: false
  }).format(numericValue / 100);
}
