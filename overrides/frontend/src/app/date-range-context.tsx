import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

export type DateRangePreset = "this_week" | "last_7_days" | "this_month" | "last_month" | "custom";

type DateRangeSelection = {
  preset: DateRangePreset;
  fromDate: string;
  toDate: string;
  comparisonFromDate: string;
  comparisonToDate: string;
};

type DateRangeContextValue = DateRangeSelection & {
  setPreset: (preset: DateRangePreset) => void;
  setCustomRange: (fromDate: string, toDate: string) => void;
};

const DateRangeContext = createContext<DateRangeContextValue | null>(null);

function formatDateOnly(value: Date): string {
  const copy = new Date(value);
  copy.setHours(0, 0, 0, 0);
  const year = copy.getFullYear();
  const month = String(copy.getMonth() + 1).padStart(2, "0");
  const day = String(copy.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(value: Date, days: number): Date {
  const copy = new Date(value);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function startOfWeek(today: Date): Date {
  const copy = new Date(today);
  const weekday = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - weekday);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function endOfWeek(today: Date): Date {
  return addDays(startOfWeek(today), 6);
}

function startOfMonth(today: Date): Date {
  return new Date(today.getFullYear(), today.getMonth(), 1);
}

function endOfMonth(today: Date): Date {
  return new Date(today.getFullYear(), today.getMonth() + 1, 0);
}

function resolvePreset(preset: DateRangePreset): DateRangeSelection {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  if (preset === "this_week") {
    const from = startOfWeek(today);
    const to = endOfWeek(today);
    return {
      preset,
      fromDate: formatDateOnly(from),
      toDate: formatDateOnly(to),
      comparisonFromDate: formatDateOnly(addDays(from, -7)),
      comparisonToDate: formatDateOnly(addDays(to, -7))
    };
  }

  if (preset === "last_7_days") {
    const to = today;
    const from = addDays(today, -6);
    return {
      preset,
      fromDate: formatDateOnly(from),
      toDate: formatDateOnly(to),
      comparisonFromDate: formatDateOnly(addDays(from, -7)),
      comparisonToDate: formatDateOnly(addDays(to, -7))
    };
  }

  if (preset === "last_month") {
    const reference = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    const from = startOfMonth(reference);
    const to = endOfMonth(reference);
    const previousReference = new Date(reference.getFullYear(), reference.getMonth() - 1, 1);
    return {
      preset,
      fromDate: formatDateOnly(from),
      toDate: formatDateOnly(to),
      comparisonFromDate: formatDateOnly(startOfMonth(previousReference)),
      comparisonToDate: formatDateOnly(endOfMonth(previousReference))
    };
  }

  const from = startOfMonth(today);
  const to = endOfMonth(today);
  const previousReference = new Date(today.getFullYear(), today.getMonth() - 1, 1);
  return {
    preset,
    fromDate: formatDateOnly(from),
    toDate: formatDateOnly(to),
    comparisonFromDate: formatDateOnly(startOfMonth(previousReference)),
    comparisonToDate: formatDateOnly(endOfMonth(previousReference))
  };
}

export function DateRangeProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<DateRangeSelection>(() => resolvePreset("this_week"));

  const value = useMemo<DateRangeContextValue>(
    () => ({
      ...selection,
      setPreset: (preset) => {
        setSelection(resolvePreset(preset));
      },
      setCustomRange: (fromDate, toDate) => {
        const from = new Date(fromDate);
        const to = new Date(toDate);
        const days = Math.max(1, Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1);
        setSelection({
          preset: "custom",
          fromDate,
          toDate,
          comparisonFromDate: formatDateOnly(addDays(from, -days)),
          comparisonToDate: formatDateOnly(addDays(to, -days))
        });
      }
    }),
    [selection]
  );

  return <DateRangeContext.Provider value={value}>{children}</DateRangeContext.Provider>;
}

export function useDateRangeContext(): DateRangeContextValue {
  const context = useContext(DateRangeContext);
  if (!context) {
    throw new Error("useDateRangeContext must be used within a DateRangeProvider");
  }
  return context;
}
