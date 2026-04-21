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
    dining: "Dining Out",
    "dining:restaurant": "Restaurant",
    "dining:takeaway_delivery": "Delivery & Takeaway",
    "dining:coffee_snacks": "Coffee & Snacks",
    household: "Household",
    "household:cleaning": "Cleaning Supplies",
    "household:paper_goods": "Paper Goods",
    "household:home_misc": "Home Misc",
    personal_care: "Personal Care",
    "personal_care:cosmetics": "Cosmetics",
    "personal_care:hygiene": "Hygiene",
    "personal_care:baby": "Baby Care",
    health: "Health",
    "health:pharmacy": "Pharmacy",
    "health:medical": "Medical",
    transport: "Transport",
    "transport:fuel": "Fuel",
    "transport:public_transit": "Public Transit",
    "transport:taxi_rideshare": "Taxi & Rideshare",
    "transport:parking_tolls": "Parking & Tolls",
    shopping: "Shopping",
    "shopping:clothing": "Clothing",
    "shopping:electronics": "Electronics",
    "shopping:general": "General Shopping",
    entertainment: "Entertainment",
    "entertainment:streaming": "Streaming",
    "entertainment:games_hobbies": "Games & Hobbies",
    "entertainment:events_leisure": "Events & Leisure",
    travel: "Travel",
    "travel:transport": "Travel Transport",
    "travel:lodging": "Lodging",
    fees: "Fees",
    "fees:shipping": "Shipping Fees",
    "fees:service": "Service Fees",
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
    dining: "Auswärtsessen",
    "dining:restaurant": "Restaurant",
    "dining:takeaway_delivery": "Lieferservice & Take-away",
    "dining:coffee_snacks": "Kaffee & Snacks",
    household: "Haushalt",
    "household:cleaning": "Reinigungsmittel",
    "household:paper_goods": "Papierwaren",
    "household:home_misc": "Haushaltswaren",
    personal_care: "Pflege",
    "personal_care:cosmetics": "Kosmetik",
    "personal_care:hygiene": "Hygiene",
    "personal_care:baby": "Baby",
    health: "Gesundheit",
    "health:pharmacy": "Apotheke",
    "health:medical": "Arzt & Medizin",
    transport: "Mobilität",
    "transport:fuel": "Tanken",
    "transport:public_transit": "ÖPNV",
    "transport:taxi_rideshare": "Taxi & Fahrdienste",
    "transport:parking_tolls": "Parken & Maut",
    shopping: "Einkaufen",
    "shopping:clothing": "Kleidung",
    "shopping:electronics": "Elektronik",
    "shopping:general": "Sonstiger Einkauf",
    entertainment: "Freizeit",
    "entertainment:streaming": "Streaming",
    "entertainment:games_hobbies": "Spiele & Hobbys",
    "entertainment:events_leisure": "Events & Freizeit",
    travel: "Reisen",
    "travel:transport": "Reisetransport",
    "travel:lodging": "Unterkunft",
    fees: "Gebühren",
    "fees:shipping": "Versandgebühren",
    "fees:service": "Servicegebühren",
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
  "dining",
  "dining:restaurant",
  "dining:takeaway_delivery",
  "dining:coffee_snacks",
  "household",
  "household:cleaning",
  "household:paper_goods",
  "household:home_misc",
  "personal_care",
  "personal_care:cosmetics",
  "personal_care:hygiene",
  "personal_care:baby",
  "health",
  "health:pharmacy",
  "health:medical",
  "transport",
  "transport:fuel",
  "transport:public_transit",
  "transport:taxi_rideshare",
  "transport:parking_tolls",
  "shopping",
  "shopping:clothing",
  "shopping:electronics",
  "shopping:general",
  "entertainment",
  "entertainment:streaming",
  "entertainment:games_hobbies",
  "entertainment:events_leisure",
  "travel",
  "travel:transport",
  "travel:lodging",
  "fees",
  "fees:shipping",
  "fees:service",
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
