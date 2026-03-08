import {
  DEFAULT_DESKTOP_LOCALE,
  DESKTOP_MESSAGES,
  INTL_LOCALE_BY_DESKTOP_LOCALE,
  SUPPORTED_DESKTOP_LOCALES,
  type DesktopLocale,
  type DesktopMessageKey
} from "./generated";

export type { DesktopLocale, DesktopMessageKey } from "./generated";

export type DesktopTranslationVariables = Record<string, string | number>;

export function isDesktopLocale(value: string): value is DesktopLocale {
  return (SUPPORTED_DESKTOP_LOCALES as readonly string[]).includes(value);
}

export function resolveDesktopLocale(value: string | null | undefined): DesktopLocale {
  if (!value) {
    return DEFAULT_DESKTOP_LOCALE;
  }
  const normalized = value.toLowerCase();
  if (isDesktopLocale(normalized)) {
    return normalized;
  }
  return normalized.startsWith("de") ? "de" : "en";
}

export function detectDesktopLocaleFromNavigator(): DesktopLocale {
  if (typeof navigator === "undefined") {
    return DEFAULT_DESKTOP_LOCALE;
  }
  return resolveDesktopLocale(navigator.language);
}

export function toDesktopIntlLocale(locale: DesktopLocale): string {
  return INTL_LOCALE_BY_DESKTOP_LOCALE[locale];
}

export function interpolateDesktopMessage(
  template: string,
  variables?: DesktopTranslationVariables
): string {
  if (!variables) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (_match, key: string) => {
    const value = variables[key];
    return value === undefined ? `{${key}}` : String(value);
  });
}

export function translateDesktopMessage(
  locale: DesktopLocale,
  key: DesktopMessageKey,
  variables?: DesktopTranslationVariables
): string {
  const template = DESKTOP_MESSAGES[locale][key] ?? DESKTOP_MESSAGES.en[key] ?? key;
  return interpolateDesktopMessage(template, variables);
}
