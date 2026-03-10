import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type MetricCardProps = {
  title: string;
  value: string;
  icon?: ReactNode;
  iconClassName?: string;
  subtitle?: string;
  trend?: { direction: "up" | "down" | "flat"; label: string };
};

export function MetricCard({ title, value, icon, iconClassName, subtitle, trend }: MetricCardProps) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {title}
          </CardTitle>
          {icon ? (
            <span className={cn("rounded-md p-1.5", iconClassName)}>
              {icon}
            </span>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold tabular-nums">{value}</p>
        {trend ? (
          <p
            className={cn(
              "mt-1 text-xs font-medium",
              trend.direction === "up" && "text-success",
              trend.direction === "down" && "text-destructive",
              trend.direction === "flat" && "text-muted-foreground"
            )}
          >
            {trend.label}
          </p>
        ) : null}
        {subtitle ? (
          <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
