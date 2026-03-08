import { resolveIntlLocale } from "@/i18n";

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

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return value;
  }
  return new Intl.DateTimeFormat(resolveIntlLocale(), {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}
