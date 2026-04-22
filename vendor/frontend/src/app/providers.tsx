import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";

import { DateRangeProvider } from "@/app/date-range-context";
import { AccessScopeProvider } from "@/app/scope-provider";
import { Toaster } from "@/components/ui/sonner";
import { I18nProvider, useI18n } from "@/i18n";
import { resolveApiWarningMessage, shouldSuppressApiWarning } from "@/lib/backend-messages";
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

  return (
    <I18nProvider>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem enableColorScheme>
        <QueryClientProvider client={queryClient}>
          <AccessScopeProvider>
            <DateRangeProvider>
              <AppProvidersContent>{children}</AppProvidersContent>
            </DateRangeProvider>
          </AccessScopeProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </I18nProvider>
  );
}
