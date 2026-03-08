import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { ReactNode, useEffect, useState } from "react";
import { toast } from "sonner";

import { AccessScopeProvider } from "@/app/scope-provider";
import { Toaster } from "@/components/ui/sonner";
import { I18nProvider, useI18n } from "@/i18n";
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
      toast.warning(t("system.backendWarning"), {
        description: warning,
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
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
        <QueryClientProvider client={queryClient}>
          <AccessScopeProvider>
            <AppProvidersContent>{children}</AppProvidersContent>
          </AccessScopeProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </I18nProvider>
  );
}
