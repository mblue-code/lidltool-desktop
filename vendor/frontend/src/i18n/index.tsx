import React, { ReactNode, createContext, useContext, useEffect, useMemo, useState } from "react";

import { fetchCurrentUser, updateCurrentUserLocale } from "@/api/users";
import literalDeCatalog from "@/i18n/literals.de.json";
import literalEnCatalog from "@/i18n/literals.en.json";
import { DE_MESSAGES, EN_MESSAGES, type TranslationKey } from "@/i18n/messages";
import { ApiTransportError } from "@/lib/api-errors";

export type { TranslationKey } from "@/i18n/messages";

export type SupportedLocale = "en" | "de";
export type TranslationVariables = Record<string, string | number>;

const LOCALE_STORAGE_KEY = "app.locale";
const DEFAULT_LOCALE: SupportedLocale = "en";
const SESSION_CHANGED_EVENT = "app:session-changed";

const INTL_LOCALE_BY_APP_LOCALE: Record<SupportedLocale, string> = {
  en: "en-US",
  de: "de-DE"
};

const MANUAL_LITERAL_DE_TRANSLATIONS: Record<string, string> = {
  Close: "Schließen",
  Open: "Öffnen",
  Save: "Speichern",
  Delete: "Löschen",
  Cancel: "Abbrechen",
  Confirm: "Bestätigen",
  Loading: "Lädt",
  Actions: "Aktionen",
  Status: "Status",
  Source: "Quelle",
  Sources: "Quellen",
  Category: "Kategorie",
  Amount: "Betrag",
  Details: "Details",
  Name: "Name",
  Search: "Suche",
  Overview: "Übersicht",
  Products: "Produkte",
  Comparisons: "Vergleiche",
  Receipts: "Belege",
  Budget: "Budget",
  Bills: "Rechnungen",
  Patterns: "Muster",
  Reliability: "Zuverlässigkeit",
  Users: "Benutzer",
  Chat: "Chat",
  Any: "Beliebig",
  Date: "Datum",
  Month: "Monat",
  Year: "Jahr",
  From: "Von",
  To: "Bis",
  Error: "Fehler",
  Success: "Erfolg",
  Amazon: "Amazon",
  Actor: "Akteur",
  "Actor ID": "Akteur-ID",
  "Actor ID must be 120 characters or less.": "Die Akteur-ID darf höchstens 120 Zeichen lang sein.",
  "All receipt": "Alle Belege",
  "All source": "Alle Quellen",
  "Amount tolerance": "Betragstoleranz",
  "Basket Builder": "Warenkorb-Builder",
  "Bill created.": "Rechnung erstellt.",
  "Drop a receipt here, or choose a file": "Beleg hier ablegen oder Datei auswählen",
  "Receipt sharing mode": "Beleg-Freigabemodus",
  Receipt: "Beleg",
  Indicator: "Indikator",
  Group: "Gruppe"
};

const LITERAL_CATALOGS: Record<SupportedLocale, Record<string, string>> = {
  en: literalEnCatalog as Record<string, string>,
  de: literalDeCatalog as Record<string, string>
};

const MESSAGES: Record<SupportedLocale, Record<TranslationKey, string>> = {
  en: EN_MESSAGES,
  de: DE_MESSAGES
};

const LOCALIZABLE_ATTRIBUTES = ["placeholder", "title", "aria-label"] as const;
const NON_LOCALIZABLE_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT"]);
const originalTextByNode = new WeakMap<Text, string>();
const originalAttributesByElement = new WeakMap<Element, Map<string, string>>();

let domLocalizationInProgress = false;

function interpolate(template: string, variables?: TranslationVariables): string {
  if (!variables) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = variables[key];
    return value === undefined ? `{${key}}` : String(value);
  });
}

function translateLiteralText(text: string, locale: SupportedLocale): string {
  if (locale === "en") {
    return text;
  }
  const manual = MANUAL_LITERAL_DE_TRANSLATIONS[text];
  if (manual) {
    return manual;
  }
  const catalog = LITERAL_CATALOGS[locale];
  return catalog[text] ?? text;
}

function localizeStringPreserveWhitespace(text: string, locale: SupportedLocale): string {
  const trimmed = text.trim();
  if (!trimmed) {
    return text;
  }
  const translated = translateLiteralText(trimmed, locale);
  if (translated === trimmed) {
    return text;
  }
  const leading = text.slice(0, text.indexOf(trimmed));
  const trailing = text.slice(text.indexOf(trimmed) + trimmed.length);
  return `${leading}${translated}${trailing}`;
}

function localizeTextNode(node: Text, locale: SupportedLocale): void {
  const parent = node.parentElement;
  if (parent && NON_LOCALIZABLE_TAGS.has(parent.tagName)) {
    return;
  }

  const currentText = node.nodeValue ?? "";
  const originalText = originalTextByNode.get(node) ?? currentText;
  if (!originalTextByNode.has(node)) {
    originalTextByNode.set(node, originalText);
  }

  const localized = localizeStringPreserveWhitespace(originalText, locale);
  if (currentText !== localized) {
    node.nodeValue = localized;
  }
}

function localizeElementAttributes(element: Element, locale: SupportedLocale): void {
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
    const localized = localizeStringPreserveWhitespace(original, locale);
    if (localized !== current) {
      element.setAttribute(attribute, localized);
    }
  }
}

function localizeDomNode(node: Node, locale: SupportedLocale): void {
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

function detectLocaleFromNavigator(): SupportedLocale {
  if (typeof navigator === "undefined") {
    return DEFAULT_LOCALE;
  }
  const language =
    typeof navigator.language === "string" && navigator.language.trim().length > 0
      ? navigator.language
      : DEFAULT_LOCALE;
  return language.toLowerCase().startsWith("de") ? "de" : "en";
}

export function isSupportedLocale(value: string): value is SupportedLocale {
  return value === "en" || value === "de";
}

export function getStoredLocale(): SupportedLocale {
  if (
    typeof window === "undefined" ||
    !window.localStorage ||
    typeof window.localStorage.getItem !== "function"
  ) {
    return detectLocaleFromNavigator();
  }
  const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY);
  if (stored && isSupportedLocale(stored)) {
    return stored;
  }
  return detectLocaleFromNavigator();
}

export function notifySessionChanged(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
}

export function toIntlLocale(locale: SupportedLocale): string {
  return INTL_LOCALE_BY_APP_LOCALE[locale];
}

export function resolveIntlLocale(): string {
  return toIntlLocale(getStoredLocale());
}

export function tForLocale(
  locale: SupportedLocale,
  key: TranslationKey,
  variables?: TranslationVariables
): string {
  const catalog = MESSAGES[locale] ?? MESSAGES.en;
  const template = catalog[key] ?? EN_MESSAGES[key] ?? key;
  return interpolate(template, variables);
}

type I18nContextValue = {
  locale: SupportedLocale;
  intlLocale: string;
  setLocale: (nextLocale: SupportedLocale) => void;
  t: (key: TranslationKey, variables?: TranslationVariables) => string;
  tText: (text: string) => string;
};

const I18nContext = createContext<I18nContextValue>({
  locale: DEFAULT_LOCALE,
  intlLocale: toIntlLocale(DEFAULT_LOCALE),
  setLocale: () => undefined,
  t: (key, variables) => tForLocale(DEFAULT_LOCALE, key, variables),
  tText: (text) => text
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<SupportedLocale>(() => getStoredLocale());
  const [hasAuthenticatedSession, setHasAuthenticatedSession] = useState(false);
  const [, setSignedInLocale] = useState<SupportedLocale | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function refreshSignedInLocale(): Promise<void> {
      try {
        const currentUser = await fetchCurrentUser();
        if (cancelled) {
          return;
        }
        const preferredLocale =
          currentUser.preferred_locale && isSupportedLocale(currentUser.preferred_locale)
            ? currentUser.preferred_locale
            : null;
        setHasAuthenticatedSession(true);
        setSignedInLocale(preferredLocale);
        if (preferredLocale) {
          setLocaleState(preferredLocale);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        if (error instanceof ApiTransportError && error.status === 401) {
          setHasAuthenticatedSession(false);
          setSignedInLocale(null);
        }
      }
    }

    void refreshSignedInLocale();

    const handleSessionChanged = () => {
      void refreshSignedInLocale();
    };

    window.addEventListener(SESSION_CHANGED_EVENT, handleSessionChanged);
    return () => {
      cancelled = true;
      window.removeEventListener(SESSION_CHANGED_EVENT, handleSessionChanged);
    };
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
    }
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    }
  }, [locale]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const originalAlert = window.alert.bind(window);
    const originalConfirm = window.confirm.bind(window);
    const originalPrompt = window.prompt.bind(window);

    window.alert = (message?: string) => {
      originalAlert(typeof message === "string" ? localizeStringPreserveWhitespace(message, locale) : message);
    };
    window.confirm = (message?: string) => {
      return originalConfirm(
        typeof message === "string" ? localizeStringPreserveWhitespace(message, locale) : message
      );
    };
    window.prompt = (message?: string, defaultValue?: string) => {
      return originalPrompt(
        typeof message === "string" ? localizeStringPreserveWhitespace(message, locale) : message,
        defaultValue
      );
    };

    return () => {
      window.alert = originalAlert;
      window.confirm = originalConfirm;
      window.prompt = originalPrompt;
    };
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

  const contextValue = useMemo<I18nContextValue>(() => {
    const setLocale = (nextLocale: SupportedLocale) => {
      setLocaleState(nextLocale);
      if (!hasAuthenticatedSession) {
        return;
      }
      setSignedInLocale(nextLocale);
      void updateCurrentUserLocale(nextLocale)
        .then((result) => {
          const persistedLocale =
            result.preferred_locale && isSupportedLocale(result.preferred_locale)
              ? result.preferred_locale
              : null;
          setSignedInLocale(persistedLocale);
          if (persistedLocale) {
            setLocaleState(persistedLocale);
          }
        })
        .catch(() => {
          setSignedInLocale(null);
        });
    };
    const t = (key: TranslationKey, variables?: TranslationVariables) => tForLocale(locale, key, variables);
    const tText = (text: string) => localizeStringPreserveWhitespace(text, locale);
    return {
      locale,
      intlLocale: toIntlLocale(locale),
      setLocale,
      t,
      tText
    };
  }, [hasAuthenticatedSession, locale]);

  return <I18nContext.Provider value={contextValue}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}

export function localizeNode(node: ReactNode, locale: SupportedLocale): ReactNode {
  if (typeof node === "string") {
    return localizeStringPreserveWhitespace(node, locale);
  }
  if (Array.isArray(node)) {
    return React.Children.map(node, (child) => localizeNode(child, locale));
  }
  if (!React.isValidElement(node)) {
    return node;
  }

  const element = node as React.ReactElement<{ children?: ReactNode }>;
  if (element.props.children === undefined || element.props.children === null) {
    return element;
  }

  const nextChildren = React.Children.map(element.props.children, (child) => localizeNode(child, locale));
  return React.cloneElement(element, undefined, nextChildren);
}
