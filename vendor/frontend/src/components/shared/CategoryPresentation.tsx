import { Badge } from "@/components/ui/badge";
import type { SupportedLocale } from "@/i18n";

type CategoryPresentationProps = {
  category: string | null | undefined;
  locale: SupportedLocale;
};

export const CATEGORY_LABELS: Record<SupportedLocale, Record<string, string>> = {
  en: {
    groceries: "Groceries",
    "groceries:dairy": "Dairy",
    "groceries:baking": "Baking",
    "groceries:beverages": "Beverages",
    "groceries:produce": "Produce",
    "groceries:bakery": "Bakery",
    "groceries:fish": "Fish & Seafood",
    "groceries:meat": "Meat",
    "groceries:frozen": "Frozen",
    "groceries:snacks": "Snacks",
    "groceries:pantry": "Pantry",
    household: "Household",
    personal_care: "Personal Care",
    electronics: "Electronics",
    gaming_media: "Gaming & Media",
    shipping_fees: "Shipping",
    deposit: "Deposit",
    other: "Other"
  },
  de: {
    groceries: "Lebensmittel",
    "groceries:dairy": "Molkerei",
    "groceries:baking": "Backzutaten",
    "groceries:beverages": "Getränke",
    "groceries:produce": "Obst & Gemüse",
    "groceries:bakery": "Backwaren",
    "groceries:fish": "Fisch & Meeresfrüchte",
    "groceries:meat": "Fleisch",
    "groceries:frozen": "Tiefkühl",
    "groceries:snacks": "Snacks",
    "groceries:pantry": "Vorrat",
    household: "Haushalt",
    personal_care: "Pflege",
    electronics: "Elektronik",
    gaming_media: "Gaming & Medien",
    shipping_fees: "Versand",
    deposit: "Pfand",
    other: "Sonstiges"
  }
};

export const CATEGORY_OPTIONS: readonly string[] = [
  "groceries",
  "groceries:dairy",
  "groceries:baking",
  "groceries:beverages",
  "groceries:produce",
  "groceries:bakery",
  "groceries:fish",
  "groceries:meat",
  "groceries:frozen",
  "groceries:snacks",
  "groceries:pantry",
  "household",
  "personal_care",
  "electronics",
  "gaming_media",
  "shipping_fees",
  "deposit",
  "other"
] as const;

function humanizeCategoryToken(token: string): string {
  return token
    .split(/[_-]+/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function resolveCategoryLabel(category: string, locale: SupportedLocale): string {
  const trimmed = category.trim();
  if (!trimmed) {
    return "—";
  }
  return CATEGORY_LABELS[locale][trimmed] ?? humanizeCategoryToken(trimmed);
}

export function formatCategoryOptionLabel(category: string, locale: SupportedLocale): string {
  const trimmed = category.trim();
  if (!trimmed) {
    return "—";
  }
  const [parentKey, childKey] = trimmed.split(":");
  if (!parentKey || !childKey) {
    return resolveCategoryLabel(trimmed, locale);
  }
  return `${resolveCategoryLabel(parentKey, locale)} / ${resolveCategoryLabel(trimmed, locale)}`;
}

export function CategoryPresentation({ category, locale }: CategoryPresentationProps) {
  const trimmed = (category ?? "").trim();
  if (!trimmed) {
    return <span className="text-muted-foreground">—</span>;
  }

  const [parentKey, childKey] = trimmed.split(":");
  const hasChild = Boolean(parentKey && childKey);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="outline" className="whitespace-nowrap">
        {resolveCategoryLabel(parentKey || trimmed, locale)}
      </Badge>
      {hasChild ? (
        <Badge variant="secondary" className="whitespace-nowrap">
          {resolveCategoryLabel(`${parentKey}:${childKey}`, locale)}
        </Badge>
      ) : null}
    </div>
  );
}
