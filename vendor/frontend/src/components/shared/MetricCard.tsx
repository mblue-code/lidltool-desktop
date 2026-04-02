import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type MetricCardProps = {
  title: string;
  value: string;
  icon?: ReactNode;
  iconClassName?: string;
  subtitle?: string;
  trend?: { direction: "up" | "down" | "flat"; label: string };
  className?: string;
};

export function MetricCard({ title, value, icon, iconClassName, subtitle, trend, className }: MetricCardProps) {
  return (
    <div className={cn("space-y-1.5 px-4 py-3", className)}>
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
          {title}
        </p>
        {icon ? (
          <span className={cn("rounded-md p-1.5", iconClassName)}>
            {icon}
          </span>
        ) : null}
      </div>
      <p className="text-2xl font-bold tabular-nums tracking-tight text-foreground">{value}</p>
      {trend ? (
        <p
          className={cn(
            "text-xs font-medium",
            trend.direction === "up" && "text-success",
            trend.direction === "down" && "text-destructive",
            trend.direction === "flat" && "text-muted-foreground"
          )}
        >
          {trend.label}
        </p>
      ) : null}
      {subtitle ? (
        <p className="text-xs text-muted-foreground/90">{subtitle}</p>
      ) : null}
    </div>
  );
}
