import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import type { DesktopLocale, DesktopMessageKey, DesktopTranslationVariables } from "../i18n";
import {
  detectDesktopLocaleFromNavigator,
  resolveDesktopLocale,
  toDesktopIntlLocale,
  translateDesktopMessage
} from "../i18n";

const SHELL_LOCALE_STORAGE_KEY = "desktop.shell.locale";

type DesktopI18nContextValue = {
  locale: DesktopLocale;
  intlLocale: string;
  setLocale: (nextLocale: DesktopLocale) => void;
  t: (key: DesktopMessageKey, variables?: DesktopTranslationVariables) => string;
};

const DesktopI18nContext = createContext<DesktopI18nContextValue>({
  locale: detectDesktopLocaleFromNavigator(),
  intlLocale: toDesktopIntlLocale(detectDesktopLocaleFromNavigator()),
  setLocale: () => undefined,
  t: (key, variables) => translateDesktopMessage(detectDesktopLocaleFromNavigator(), key, variables)
});

function getStoredShellLocale(): DesktopLocale {
  if (typeof window === "undefined" || !window.localStorage) {
    return detectDesktopLocaleFromNavigator();
  }
  return resolveDesktopLocale(window.localStorage.getItem(SHELL_LOCALE_STORAGE_KEY));
}

export function DesktopI18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<DesktopLocale>(() => getStoredShellLocale());

  useEffect(() => {
    let cancelled = false;

    async function loadDesktopLocale(): Promise<void> {
      try {
        const stored = await window.desktopApi.getLocale();
        if (!cancelled) {
          setLocaleState(resolveDesktopLocale(stored));
        }
      } catch {
        if (!cancelled) {
          setLocaleState(getStoredShellLocale());
        }
      }
    }

    void loadDesktopLocale();
    const dispose = window.desktopApi.onLocaleChanged((nextLocale) => {
      if (!cancelled) {
        setLocaleState(resolveDesktopLocale(nextLocale));
      }
    });

    return () => {
      cancelled = true;
      dispose();
    };
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(SHELL_LOCALE_STORAGE_KEY, locale);
    }
    document.documentElement.lang = locale;
    document.title = translateDesktopMessage(locale, "shell.windowTitle");
  }, [locale]);

  const value = useMemo<DesktopI18nContextValue>(
    () => ({
      locale,
      intlLocale: toDesktopIntlLocale(locale),
      setLocale: (nextLocale) => {
        setLocaleState(nextLocale);
        void window.desktopApi.setLocale(nextLocale);
      },
      t: (key, variables) => translateDesktopMessage(locale, key, variables)
    }),
    [locale]
  );

  return <DesktopI18nContext.Provider value={value}>{children}</DesktopI18nContext.Provider>;
}

export function useDesktopI18n(): DesktopI18nContextValue {
  return useContext(DesktopI18nContext);
}
