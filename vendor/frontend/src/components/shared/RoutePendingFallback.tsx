import { Skeleton } from "@/components/ui/skeleton";

export function RoutePendingFallback() {
  return (
    <div className="mx-auto w-full max-w-7xl space-y-4 px-4 py-6 md:px-6" role="status" aria-live="polite">
      <p className="text-sm text-muted-foreground">Loading page...</p>
      <Skeleton className="h-20 w-full rounded-lg" />
      <Skeleton className="h-64 w-full rounded-lg" />
      <Skeleton className="h-64 w-full rounded-lg" />
    </div>
  );
}
