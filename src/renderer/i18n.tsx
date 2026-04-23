import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import type { DesktopLocale, DesktopMessageKey, DesktopTranslationVariables } from "../i18n";
import {
  detectDesktopLocaleFromNavigator,
  localizeDesktopStringPreserveWhitespace,
  resolveDesktopLocale,
  toDesktopIntlLocale,
  translateDesktopMessage
} from "../i18n";

const SHELL_LOCALE_STORAGE_KEY = "desktop.shell.locale";
const LOCALIZABLE_ATTRIBUTES = ["placeholder", "title", "aria-label"] as const;
const NON_LOCALIZABLE_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT"]);
const originalTextByNode = new WeakMap<Text, string>();
const originalAttributesByElement = new WeakMap<Element, Map<string, string>>();

let domLocalizationInProgress = false;

type DesktopI18nContextValue = {
  locale: DesktopLocale;
  intlLocale: string;
  setLocale: (nextLocale: DesktopLocale) => void;
  t: (key: DesktopMessageKey, variables?: DesktopTranslationVariables) => string;
  tText: (text: string) => string;
};

const DesktopI18nContext = createContext<DesktopI18nContextValue>({
  locale: detectDesktopLocaleFromNavigator(),
  intlLocale: toDesktopIntlLocale(detectDesktopLocaleFromNavigator()),
  setLocale: () => undefined,
  t: (key, variables) => translateDesktopMessage(detectDesktopLocaleFromNavigator(), key, variables),
  tText: (text) => localizeDesktopStringPreserveWhitespace(detectDesktopLocaleFromNavigator(), text)
});

function getStoredShellLocale(): DesktopLocale {
  if (typeof window === "undefined" || !window.localStorage) {
    return detectDesktopLocaleFromNavigator();
  }
  return resolveDesktopLocale(window.localStorage.getItem(SHELL_LOCALE_STORAGE_KEY));
}

function localizeTextNode(node: Text, locale: DesktopLocale): void {
  const parent = node.parentElement;
  if (parent && NON_LOCALIZABLE_TAGS.has(parent.tagName)) {
    return;
  }

  const currentText = node.nodeValue ?? "";
  const originalText = originalTextByNode.get(node) ?? currentText;
  if (!originalTextByNode.has(node)) {
    originalTextByNode.set(node, originalText);
  }

  const localized = localizeDesktopStringPreserveWhitespace(locale, originalText);
  if (currentText !== localized) {
    node.nodeValue = localized;
  }
}

function localizeElementAttributes(element: Element, locale: DesktopLocale): void {
  let originalAttributes = originalAttributesByElement.get(element);
  if (!originalAttributes) {
    originalAttributes = new Map<string, string>();
    originalAttributesByElement.set(element, originalAttributes);
  }

  for (const attribute of LOCALIZABLE_ATTRIBUTES) {
    const current = element.getAttribute(attribute);
    if (current === null) {
      continue;
    }
    if (!originalAttributes.has(attribute)) {
      originalAttributes.set(attribute, current);
    }
    const original = originalAttributes.get(attribute) ?? current;
    const localized = localizeDesktopStringPreserveWhitespace(locale, original);
    if (localized !== current) {
      element.setAttribute(attribute, localized);
    }
  }
}

function localizeDomNode(node: Node, locale: DesktopLocale): void {
  if (node.nodeType === Node.TEXT_NODE) {
    localizeTextNode(node as Text, locale);
    return;
  }

  if (node.nodeType !== Node.ELEMENT_NODE) {
    return;
  }

  localizeElementAttributes(node as Element, locale);

  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let current: Node | null = walker.currentNode;
  while (current) {
    if (current.nodeType === Node.TEXT_NODE) {
      localizeTextNode(current as Text, locale);
    } else if (current.nodeType === Node.ELEMENT_NODE) {
      localizeElementAttributes(current as Element, locale);
    }
    current = walker.nextNode();
  }
}

function withDomLocalizationGuard(action: () => void): void {
  if (domLocalizationInProgress) {
    return;
  }
  domLocalizationInProgress = true;
  try {
    action();
  } finally {
    domLocalizationInProgress = false;
  }
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

  useEffect(() => {
    if (typeof document === "undefined" || !document.body) {
      return;
    }

    withDomLocalizationGuard(() => {
      localizeDomNode(document.body, locale);
    });

    const observer = new MutationObserver((mutations) => {
      withDomLocalizationGuard(() => {
        for (const mutation of mutations) {
          if (mutation.type === "childList") {
            mutation.addedNodes.forEach((node) => {
              localizeDomNode(node, locale);
            });
          } else if (mutation.type === "characterData" && mutation.target.nodeType === Node.TEXT_NODE) {
            localizeTextNode(mutation.target as Text, locale);
          } else if (mutation.type === "attributes" && mutation.target.nodeType === Node.ELEMENT_NODE) {
            localizeElementAttributes(mutation.target as Element, locale);
          }
        }
      });
    });

    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: [...LOCALIZABLE_ATTRIBUTES]
    });

    return () => observer.disconnect();
  }, [locale]);

  const value = useMemo<DesktopI18nContextValue>(
    () => ({
      locale,
      intlLocale: toDesktopIntlLocale(locale),
      setLocale: (nextLocale) => {
        setLocaleState(nextLocale);
        void window.desktopApi.setLocale(nextLocale);
      },
      t: (key, variables) => translateDesktopMessage(locale, key, variables),
      tText: (text) => localizeDesktopStringPreserveWhitespace(locale, text)
    }),
    [locale]
  );

  return <DesktopI18nContext.Provider value={value}>{children}</DesktopI18nContext.Provider>;
}

export function useDesktopI18n(): DesktopI18nContextValue {
  return useContext(DesktopI18nContext);
}
