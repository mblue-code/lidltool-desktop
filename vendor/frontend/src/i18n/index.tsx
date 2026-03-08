import React, { ReactNode, createContext, useContext, useEffect, useMemo, useState } from "react";
import literalDeCatalog from "@/i18n/literals.de.json";
import literalEnCatalog from "@/i18n/literals.en.json";

export type SupportedLocale = "en" | "de";
export type TranslationVariables = Record<string, string | number>;

const LOCALE_STORAGE_KEY = "app.locale";
const DEFAULT_LOCALE: SupportedLocale = "en";

const INTL_LOCALE_BY_APP_LOCALE: Record<SupportedLocale, string> = {
  en: "en-US",
  de: "de-DE"
};

const EN_MESSAGES = {
  "app.brand.title": "Lidl Receipts",
  "app.brand.subtitle": "Spending Analytics",
  "nav.group.analytics": "Analytics",
  "nav.group.data": "Data",
  "nav.group.system": "System",
  "nav.item.overview": "Overview",
  "nav.item.explore": "Explore",
  "nav.item.products": "Products",
  "nav.item.comparisons": "Comparisons",
  "nav.item.receipts": "Receipts",
  "nav.item.budget": "Budget",
  "nav.item.bills": "Bills",
  "nav.item.patterns": "Patterns",
  "nav.item.dataQuality": "Data Quality",
  "nav.item.connectors": "Connectors",
  "nav.item.sources": "Sources",
  "nav.item.manualImport": "Manual Import",
  "nav.item.ocrImport": "OCR Import",
  "nav.item.automations": "Automations",
  "nav.item.chat": "Chat",
  "nav.item.reliability": "Reliability",
  "nav.item.aiAssistant": "AI Assistant",
  "nav.item.users": "Users",
  "nav.primary": "Primary navigation",
  "app.chat.open": "Open chat",
  "app.chat.close": "Close chat",
  "app.role.admin": "Admin",
  "action.signOut": "Sign out",
  "app.skipToMain": "Skip to main content",
  "app.header.scope": "Scope",
  "app.scope.personal": "Personal",
  "app.scope.family": "Family",
  "app.header.language": "Language",
  "app.language.english": "English",
  "app.language.german": "Deutsch",
  "app.aria.openNavigationMenu": "Open navigation menu",
  "app.defaultPageTitle": "Overview",
  "system.backendWarning": "Backend warning",
  "common.close": "Close",
  "common.changes": "Changes"
} as const;

export type TranslationKey = keyof typeof EN_MESSAGES;

const DE_MESSAGES: Record<TranslationKey, string> = {
  "app.brand.title": "Lidl Belege",
  "app.brand.subtitle": "Ausgabenanalyse",
  "nav.group.analytics": "Analyse",
  "nav.group.data": "Daten",
  "nav.group.system": "System",
  "nav.item.overview": "Übersicht",
  "nav.item.explore": "Erkunden",
  "nav.item.products": "Produkte",
  "nav.item.comparisons": "Vergleiche",
  "nav.item.receipts": "Belege",
  "nav.item.budget": "Budget",
  "nav.item.bills": "Rechnungen",
  "nav.item.patterns": "Muster",
  "nav.item.dataQuality": "Datenqualität",
  "nav.item.connectors": "Konnektoren",
  "nav.item.sources": "Quellen",
  "nav.item.manualImport": "Manueller Import",
  "nav.item.ocrImport": "OCR-Import",
  "nav.item.automations": "Automatisierungen",
  "nav.item.chat": "Chat",
  "nav.item.reliability": "Zuverlässigkeit",
  "nav.item.aiAssistant": "KI-Assistent",
  "nav.item.users": "Benutzer",
  "nav.primary": "Primäre Navigation",
  "app.chat.open": "Chat Öffnen",
  "app.chat.close": "Chat schließen",
  "app.role.admin": "Admin",
  "action.signOut": "Abmelden",
  "app.skipToMain": "Zum Hauptinhalt springen",
  "app.header.scope": "Bereich",
  "app.scope.personal": "Persönlich",
  "app.scope.family": "Familie",
  "app.header.language": "Sprache",
  "app.language.english": "English",
  "app.language.german": "Deutsch",
  "app.aria.openNavigationMenu": "Navigationsmenü Öffnen",
  "app.defaultPageTitle": "Übersicht",
  "system.backendWarning": "Backend-Warnung",
  "common.close": "Schließen",
  "common.changes": "Änderungen"
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

type LocaleStorage = Pick<Storage, "getItem" | "setItem">;

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
  return navigator.language.toLowerCase().startsWith("de") ? "de" : "en";
}

export function isSupportedLocale(value: string): value is SupportedLocale {
  return value === "en" || value === "de";
}

function getLocaleStorage(): LocaleStorage | null {
  if (typeof window === "undefined") {
    return null;
  }

  const storage = window.localStorage;
  if (
    !storage ||
    typeof storage.getItem !== "function" ||
    typeof storage.setItem !== "function"
  ) {
    return null;
  }

  return storage;
}

export function getStoredLocale(): SupportedLocale {
  const storage = getLocaleStorage();
  if (!storage) {
    return detectLocaleFromNavigator();
  }
  const stored = storage.getItem(LOCALE_STORAGE_KEY);
  if (stored && isSupportedLocale(stored)) {
    return stored;
  }
  return detectLocaleFromNavigator();
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

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
    }
    const storage = getLocaleStorage();
    if (storage) {
      storage.setItem(LOCALE_STORAGE_KEY, locale);
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
    const t = (key: TranslationKey, variables?: TranslationVariables) => tForLocale(locale, key, variables);
    const tText = (text: string) => localizeStringPreserveWhitespace(text, locale);
    return {
      locale,
      intlLocale: toIntlLocale(locale),
      setLocale: setLocaleState,
      t,
      tText
    };
  }, [locale]);

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
