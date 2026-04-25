import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";

import { AppearanceProvider } from "@/app/appearance-context";
import { DateRangeProvider } from "@/app/date-range-context";
import { AccessScopeProvider } from "@/app/scope-provider";
import { Toaster } from "@/components/ui/sonner";
import { I18nProvider, useI18n } from "@/i18n";
import { resolveApiWarningMessage, shouldSuppressApiWarning } from "@/lib/backend-messages";
import { isRetryableApiError } from "@/lib/api-errors";
import { subscribeApiWarnings } from "@/lib/api-warnings";
import { invalidateFinanceWorkspaceQueries } from "@/lib/finance-query-invalidation";

type AppProvidersProps = {
  children: ReactNode;
};

export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) {
    return false;
  }
  return isRetryableApiError(error);
}

function AppProvidersContent({ children }: { children: ReactNode }) {
  const { t } = useI18n();

  useEffect(() => {
    return subscribeApiWarnings((warning) => {
      if (shouldSuppressApiWarning(warning)) {
        return;
      }
      toast.warning(t("system.backendWarning"), {
        description: resolveApiWarningMessage(warning, t),
        duration: 7000
      });
    });
  }, [t]);

  return (
    <>
      {children}
      <Toaster richColors position="top-right" />
    </>
  );
}

export function AppProviders({ children }: AppProvidersProps) {
  const [queryClient] = useState(
    () => {
      let client: QueryClient;
      client = new QueryClient({
        mutationCache: new MutationCache({
          onSuccess: async () => {
            await invalidateFinanceWorkspaceQueries(client);
          }
        }),
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: shouldRetryQuery
          }
        }
      });
      return client;
    }
  );

  return (
    <I18nProvider>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem enableColorScheme>
        <AppearanceProvider>
          <QueryClientProvider client={queryClient}>
            <AccessScopeProvider>
              <DateRangeProvider>
                <AppProvidersContent>{children}</AppProvidersContent>
              </DateRangeProvider>
            </AccessScopeProvider>
          </QueryClientProvider>
        </AppearanceProvider>
      </ThemeProvider>
    </I18nProvider>
  );
}
