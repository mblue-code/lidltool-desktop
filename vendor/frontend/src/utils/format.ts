import { resolveIntlLocale } from "@/i18n";

function toDate(value: string | Date): Date | null {
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.valueOf()) ? null : date;
}

export function formatEurFromCents(value: number): string {
  return new Intl.NumberFormat(resolveIntlLocale(), {
    style: "currency",
    currency: "EUR"
  }).format(value / 100);
}

export function formatPercent(value: number): string {
  return new Intl.NumberFormat(resolveIntlLocale(), {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(resolveIntlLocale(), options).format(value);
}

export function formatDate(value: string | Date): string {
  const date = toDate(value);
  if (!date) {
    return String(value);
  }
  return new Intl.DateTimeFormat(resolveIntlLocale(), {
    dateStyle: "medium"
  }).format(date);
}

export function formatDateTime(value: string | Date): string {
  const date = toDate(value);
  if (!date) {
    return String(value);
  }
  return new Intl.DateTimeFormat(resolveIntlLocale(), {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

export function formatMonthDay(value: string | Date): string {
  const date = toDate(value);
  if (!date) {
    return String(value);
  }
  return new Intl.DateTimeFormat(resolveIntlLocale(), {
    month: "short",
    day: "numeric"
  }).format(date);
}

export function formatMonthYear(value: string | Date): string {
  const date = toDate(value);
  if (!date) {
    return String(value);
  }
  return new Intl.DateTimeFormat(resolveIntlLocale(), {
    month: "long",
    year: "numeric"
  }).format(date);
}

export function formatMonthName(month: number, width: "long" | "short" = "long"): string {
  const safeMonth = Math.min(12, Math.max(1, Math.trunc(month)));
  const date = new Date(Date.UTC(2026, safeMonth - 1, 1, 12, 0, 0));
  return new Intl.DateTimeFormat(resolveIntlLocale(), { month: width, timeZone: "UTC" }).format(date);
}
