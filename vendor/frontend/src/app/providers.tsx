import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";

import { AccessScopeProvider } from "@/app/scope-provider";
import { Toaster } from "@/components/ui/sonner";
import { isRetryableApiError } from "@/lib/api-errors";
import { subscribeApiWarnings } from "@/lib/api-warnings";

type AppProvidersProps = {
  children: ReactNode;
};

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) {
    return false;
  }
  return isRetryableApiError(error);
}

export function AppProviders({ children }: AppProvidersProps): JSX.Element {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: shouldRetryQuery
          }
        }
      })
  );

  useEffect(() => {
    return subscribeApiWarnings((warning) => {
      toast.warning("Backend warning", {
        description: warning,
        duration: 7000
      });
    });
  }, []);

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <QueryClientProvider client={queryClient}>
        <AccessScopeProvider>
          {children}
          <Toaster richColors position="top-right" />
        </AccessScopeProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
