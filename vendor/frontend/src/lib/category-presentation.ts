export type TransactionDirection = "inflow" | "outflow" | "transfer" | "neutral";
type Translate = (key: any, variables?: Record<string, string | number>) => string;

export const FINANCE_CATEGORY_OPTIONS = [
  "groceries",
  "housing:rent",
  "housing:electricity",
  "housing:heating",
  "housing:internet",
  "housing:utilities",
  "insurance:liability",
  "insurance:health",
  "insurance:household",
  "insurance:car",
  "credit:repayment",
  "mobility:train",
  "mobility:public_transit",
  "car:fuel",
  "car:charging",
  "car:maintenance",
  "investment:broker_transfer",
  "subscriptions:software",
  "subscriptions:streaming",
  "subscriptions:fitness",
  "subscriptions:news",
  "shopping:online_retail",
  "shopping:convenience",
  "personal_care:drugstore",
  "education:publications",
  "income:salary",
  "fees:bank",
  "tax:income_tax",
  "other",
  "uncategorized"
] as const;

export function financeCategoryParent(categoryId?: string | null): string | null {
  if (!categoryId) return null;
  return categoryId.split(":", 1)[0] || null;
}

export function financeCategoryLabel(categoryId: string | null | undefined, t: Translate): string {
  const id = categoryId || "uncategorized";
  return t("category.finance." + id.replace(/:/g, "."), { defaultValue: id.replace(/[_:]/g, " ") });
}

export function groceryCategoryLabel(categoryId: string | null | undefined, t: Translate): string {
  const id = categoryId || "uncategorized";
  return t("category.grocery." + id.replace(/:/g, "."), { defaultValue: id.replace(/[_:]/g, " ") });
}

export function directionLabel(direction: string | null | undefined, t: Translate): string {
  const value = direction || "outflow";
  return t("transaction.direction." + value, { defaultValue: value });
}
