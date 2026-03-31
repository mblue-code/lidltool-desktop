import { resolveIntlLocale } from "@/i18n";

type ParseEuroInputOptions = {
  allowNegative?: boolean;
};

export function parseEuroInputToCents(
  input: string,
  options: ParseEuroInputOptions = {}
): number | null {
  const trimmed = input.trim();
  if (!trimmed) {
    return null;
  }

  const signPrefix = trimmed[0] === "-" || trimmed[0] === "+" ? trimmed[0] : "";
  const unsigned = signPrefix ? trimmed.slice(1) : trimmed;
  if (!unsigned) {
    return null;
  }
  if (signPrefix === "-" && !options.allowNegative) {
    return null;
  }
  if (!/^\d*(?:[.,]\d*)?$/.test(unsigned)) {
    return null;
  }

  const [eurosPartRaw = "", centsPartRaw = ""] = unsigned.split(/[.,]/);
  if (!eurosPartRaw && !centsPartRaw) {
    return null;
  }
  if (centsPartRaw.length > 2) {
    return null;
  }

  const eurosPart = eurosPartRaw || "0";
  if (!/^\d+$/.test(eurosPart) || (centsPartRaw && !/^\d+$/.test(centsPartRaw))) {
    return null;
  }

  const centsValue = Number.parseInt(`${eurosPart}${centsPartRaw.padEnd(2, "0")}`, 10);
  if (!Number.isSafeInteger(centsValue)) {
    return null;
  }

  return signPrefix === "-" ? -centsValue : centsValue;
}

export function formatCentsForInput(cents: number | null): string {
  if (cents === null) {
    return "";
  }
  return new Intl.NumberFormat(resolveIntlLocale(), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: false
  }).format(cents / 100);
}
