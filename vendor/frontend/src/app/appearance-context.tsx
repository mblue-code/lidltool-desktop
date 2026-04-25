import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { useTheme } from "next-themes";

type ThemeScheme = "light" | "dark";

export type AppearanceThemeConfig = {
  accent: string;
  background: string;
  foreground: string;
  uiFontFamily: string;
  codeFontFamily: string;
  transparentSidebar: boolean;
  contrast: number;
};

type AppearancePreset = {
  id: string;
  label: string;
  sample: string;
  light: AppearanceThemeConfig;
  dark: AppearanceThemeConfig;
};

type AppearanceSettings = {
  lightPresetId: string;
  darkPresetId: string;
  light: AppearanceThemeConfig;
  dark: AppearanceThemeConfig;
  uiFontSize: number;
  codeFontSize: number;
  interactiveCursor: boolean;
};

type AppearanceContextValue = {
  settings: AppearanceSettings;
  presets: AppearancePreset[];
  activeScheme: ThemeScheme;
  updateThemeConfig: (scheme: ThemeScheme, patch: Partial<AppearanceThemeConfig>) => void;
  applyPreset: (scheme: ThemeScheme, presetId: string) => void;
  resetThemeConfig: (scheme: ThemeScheme) => void;
  updateGlobalSettings: (patch: Partial<Pick<AppearanceSettings, "uiFontSize" | "codeFontSize" | "interactiveCursor">>) => void;
};

const APPEARANCE_STORAGE_KEY = "app.appearance.v1";

const APPEARANCE_PRESETS: AppearancePreset[] = [
  {
    id: "ledger-blue",
    label: "Ledger Blue",
    sample: "Aa",
    light: {
      accent: "#2563eb",
      background: "#eef4ff",
      foreground: "#14213d",
      uiFontFamily: "Geist, Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"Geist Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 58
    },
    dark: {
      accent: "#60a5fa",
      background: "#111827",
      foreground: "#dbeafe",
      uiFontFamily: "Geist, Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"Geist Mono\", ui-monospace, monospace",
      transparentSidebar: true,
      contrast: 64
    }
  },
  {
    id: "savings-mint",
    label: "Savings Mint",
    sample: "Aa",
    light: {
      accent: "#0f9f6e",
      background: "#eefbf5",
      foreground: "#153b2e",
      uiFontFamily: "Geist, Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"IBM Plex Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 52
    },
    dark: {
      accent: "#34d399",
      background: "#0f1f1a",
      foreground: "#d1fae5",
      uiFontFamily: "Geist, Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"IBM Plex Mono\", ui-monospace, monospace",
      transparentSidebar: true,
      contrast: 59
    }
  },
  {
    id: "receipt-paper",
    label: "Receipt Paper",
    sample: "Aa",
    light: {
      accent: "#b7791f",
      background: "#faf3e7",
      foreground: "#3d2f1f",
      uiFontFamily: "\"IBM Plex Sans\", Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"IBM Plex Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 48
    },
    dark: {
      accent: "#f6ad55",
      background: "#241b14",
      foreground: "#f6e7d3",
      uiFontFamily: "\"IBM Plex Sans\", Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"IBM Plex Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 56
    }
  },
  {
    id: "github",
    label: "GitHub",
    sample: "Aa",
    light: {
      accent: "#0969da",
      background: "#f6f8fa",
      foreground: "#1f2328",
      uiFontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      codeFontFamily: "\"SFMono-Regular\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 54
    },
    dark: {
      accent: "#2f81f7",
      background: "#0d1117",
      foreground: "#c9d1d9",
      uiFontFamily: "Inter, ui-sans-serif, system-ui, sans-serif",
      codeFontFamily: "\"SFMono-Regular\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 62
    }
  },
  {
    id: "tokyo-night",
    label: "Tokyo Night",
    sample: "Aa",
    light: {
      accent: "#34548a",
      background: "#d5d6db",
      foreground: "#343b58",
      uiFontFamily: "Geist, Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"Geist Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 50
    },
    dark: {
      accent: "#3d59a1",
      background: "#1a1b26",
      foreground: "#a9b1d6",
      uiFontFamily: "Geist, Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"Geist Mono\", ui-monospace, monospace",
      transparentSidebar: true,
      contrast: 68
    }
  },
  {
    id: "codex",
    label: "Codex",
    sample: "Aa",
    light: {
      accent: "#2f6fed",
      background: "#edf2fb",
      foreground: "#172033",
      uiFontFamily: "Geist, Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"Geist Mono\", ui-monospace, monospace",
      transparentSidebar: true,
      contrast: 56
    },
    dark: {
      accent: "#2563eb",
      background: "#10151d",
      foreground: "#f5f7fb",
      uiFontFamily: "IBM Plex Sans, Segoe UI, sans-serif",
      codeFontFamily: "\"Geist Mono\", ui-monospace, monospace",
      transparentSidebar: true,
      contrast: 60
    }
  },
  {
    id: "catppuccin",
    label: "Catppuccin",
    sample: "Aa",
    light: {
      accent: "#8839ef",
      background: "#eff1f5",
      foreground: "#4c4f69",
      uiFontFamily: "Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"JetBrains Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 51
    },
    dark: {
      accent: "#cba6f7",
      background: "#1e1e2e",
      foreground: "#cdd6f4",
      uiFontFamily: "Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"JetBrains Mono\", ui-monospace, monospace",
      transparentSidebar: true,
      contrast: 63
    }
  },
  {
    id: "dracula",
    label: "Dracula",
    sample: "Aa",
    light: {
      accent: "#bd93f9",
      background: "#f5f2ff",
      foreground: "#372e52",
      uiFontFamily: "Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"JetBrains Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 50
    },
    dark: {
      accent: "#ff79c6",
      background: "#282a36",
      foreground: "#f8f8f2",
      uiFontFamily: "Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"JetBrains Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 65
    }
  },
  {
    id: "linear",
    label: "Linear",
    sample: "Aa",
    light: {
      accent: "#4f7cff",
      background: "#f4f5f8",
      foreground: "#111318",
      uiFontFamily: "Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"IBM Plex Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 48
    },
    dark: {
      accent: "#5e6ad2",
      background: "#0f1013",
      foreground: "#f7f8f8",
      uiFontFamily: "Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"IBM Plex Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 58
    }
  },
  {
    id: "everforest",
    label: "Everforest",
    sample: "Aa",
    light: {
      accent: "#4f7a5f",
      background: "#f2efdf",
      foreground: "#3a4a42",
      uiFontFamily: "Geist, Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"Geist Mono\", ui-monospace, monospace",
      transparentSidebar: false,
      contrast: 46
    },
    dark: {
      accent: "#7fbbb3",
      background: "#272e33",
      foreground: "#d3c6aa",
      uiFontFamily: "Geist, Inter, ui-sans-serif, sans-serif",
      codeFontFamily: "\"Geist Mono\", ui-monospace, monospace",
      transparentSidebar: true,
      contrast: 57
    }
  }
];

const DEFAULT_LIGHT_PRESET_ID = "ledger-blue";
const DEFAULT_DARK_PRESET_ID = "tokyo-night";

const AppearanceContext = createContext<AppearanceContextValue | null>(null);

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function normalizeHex(input: string | undefined, fallback: string): string {
  const trimmed = input?.trim() ?? "";
  const withHash = trimmed.startsWith("#") ? trimmed : `#${trimmed}`;
  if (/^#[0-9a-fA-F]{6}$/.test(withHash)) {
    return withHash.toLowerCase();
  }
  return fallback.toLowerCase();
}

function parseHex(input: string): [number, number, number] {
  const normalized = input.replace("#", "");
  return [
    Number.parseInt(normalized.slice(0, 2), 16),
    Number.parseInt(normalized.slice(2, 4), 16),
    Number.parseInt(normalized.slice(4, 6), 16)
  ];
}

function toHex([red, green, blue]: [number, number, number]): string {
  return (
    "#" +
    [red, green, blue]
      .map((value) => Math.round(clamp(value, 0, 255)).toString(16).padStart(2, "0"))
      .join("")
  );
}

function mixHex(left: string, right: string, ratio: number): string {
  const [lr, lg, lb] = parseHex(left);
  const [rr, rg, rb] = parseHex(right);
  const normalized = clamp(ratio, 0, 1);
  return toHex([
    lr + (rr - lr) * normalized,
    lg + (rg - lg) * normalized,
    lb + (rb - lb) * normalized
  ]);
}

function withAlpha(input: string, alpha: number): string {
  const [red, green, blue] = parseHex(input);
  return `rgb(${red} ${green} ${blue} / ${clamp(alpha, 0, 1).toFixed(3)})`;
}

function relativeLuminance(input: string): number {
  const [red, green, blue] = parseHex(input).map((value) => value / 255);
  const normalize = (channel: number) =>
    channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  return 0.2126 * normalize(red) + 0.7152 * normalize(green) + 0.0722 * normalize(blue);
}

function readableTextColor(background: string): string {
  return relativeLuminance(background) > 0.42 ? "#111111" : "#ffffff";
}

function getPresetById(presetId: string): AppearancePreset {
  return APPEARANCE_PRESETS.find((preset) => preset.id === presetId) ?? APPEARANCE_PRESETS[0];
}

function sanitizeThemeConfig(config: AppearanceThemeConfig, fallback: AppearanceThemeConfig): AppearanceThemeConfig {
  return {
    accent: normalizeHex(config.accent, fallback.accent),
    background: normalizeHex(config.background, fallback.background),
    foreground: normalizeHex(config.foreground, fallback.foreground),
    uiFontFamily: config.uiFontFamily?.trim() || fallback.uiFontFamily,
    codeFontFamily: config.codeFontFamily?.trim() || fallback.codeFontFamily,
    transparentSidebar: Boolean(config.transparentSidebar),
    contrast: clamp(Number(config.contrast) || fallback.contrast, 0, 100)
  };
}

function defaultSettings(): AppearanceSettings {
  const lightPreset = getPresetById(DEFAULT_LIGHT_PRESET_ID);
  const darkPreset = getPresetById(DEFAULT_DARK_PRESET_ID);
  return {
    lightPresetId: lightPreset.id,
    darkPresetId: darkPreset.id,
    light: { ...lightPreset.light },
    dark: { ...darkPreset.dark },
    uiFontSize: 16,
    codeFontSize: 13,
    interactiveCursor: false
  };
}

function loadSettings(): AppearanceSettings {
  if (typeof window === "undefined") {
    return defaultSettings();
  }

  const fallback = defaultSettings();
  const raw = window.localStorage?.getItem(APPEARANCE_STORAGE_KEY);
  if (!raw) {
    return fallback;
  }

  try {
    const parsed = JSON.parse(raw) as Partial<AppearanceSettings>;
    const lightPreset = getPresetById(parsed.lightPresetId ?? fallback.lightPresetId);
    const darkPreset = getPresetById(parsed.darkPresetId ?? fallback.darkPresetId);
    return {
      lightPresetId: lightPreset.id,
      darkPresetId: darkPreset.id,
      light: sanitizeThemeConfig(parsed.light ?? fallback.light, lightPreset.light),
      dark: sanitizeThemeConfig(parsed.dark ?? fallback.dark, darkPreset.dark),
      uiFontSize: clamp(Number(parsed.uiFontSize) || fallback.uiFontSize, 12, 18),
      codeFontSize: clamp(Number(parsed.codeFontSize) || fallback.codeFontSize, 11, 18),
      interactiveCursor: Boolean(parsed.interactiveCursor)
    };
  } catch {
    return fallback;
  }
}

function createBackgroundImage(background: string, accent: string, scheme: ThemeScheme): string {
  if (scheme === "dark") {
    return [
      `radial-gradient(circle at top right, ${withAlpha(accent, 0.22)}, transparent 28%)`,
      `radial-gradient(circle at 16% 10%, ${withAlpha(mixHex(accent, "#f59e0b", 0.7), 0.12)}, transparent 22%)`,
      `linear-gradient(160deg, ${mixHex(background, "#000000", 0.08)} 0%, ${background} 52%, ${mixHex(background, "#000000", 0.16)} 100%)`
    ].join(", ");
  }

  return [
    `radial-gradient(circle at top right, ${withAlpha(accent, 0.16)}, transparent 32%)`,
    `radial-gradient(circle at 14% 8%, ${withAlpha(mixHex(accent, "#f59e0b", 0.82), 0.11)}, transparent 24%)`,
    `linear-gradient(180deg, ${mixHex(background, "#ffffff", 0.22)}, ${background})`
  ].join(", ");
}

function buildThemeVariables(
  config: AppearanceThemeConfig,
  scheme: ThemeScheme,
  settings: Pick<AppearanceSettings, "uiFontSize" | "codeFontSize" | "interactiveCursor">
): Record<string, string> {
  const contrastRatio = config.contrast / 100;
  const accentForeground = readableTextColor(config.accent);
  const success = scheme === "dark" ? mixHex(config.accent, "#22c55e", 0.6) : mixHex(config.accent, "#16a34a", 0.65);
  const warning = scheme === "dark" ? mixHex(config.accent, "#f59e0b", 0.7) : mixHex(config.accent, "#d97706", 0.72);
  const info = scheme === "dark" ? mixHex(config.accent, "#38bdf8", 0.52) : mixHex(config.accent, "#0284c7", 0.58);
  const destructive = scheme === "dark" ? "#f87171" : "#dc2626";

  if (scheme === "dark") {
    const cardBase = mixHex(config.background, config.foreground, 0.06 + contrastRatio * 0.08);
    const mutedBase = mixHex(config.background, config.foreground, 0.12 + contrastRatio * 0.08);
    const sidebarBase = mixHex(config.background, config.accent, 0.1 + contrastRatio * 0.08);
    return {
      "--background": config.background,
      "--foreground": config.foreground,
      "--card": withAlpha(cardBase, 0.88),
      "--card-foreground": config.foreground,
      "--popover": withAlpha(mixHex(config.background, config.foreground, 0.1), 0.96),
      "--popover-foreground": config.foreground,
      "--primary": config.accent,
      "--primary-foreground": accentForeground,
      "--secondary": withAlpha(mixHex(config.background, config.accent, 0.16), 0.92),
      "--secondary-foreground": config.foreground,
      "--muted": withAlpha(mutedBase, 0.76),
      "--muted-foreground": mixHex(config.foreground, config.background, 0.26),
      "--accent": withAlpha(mixHex(config.background, config.accent, 0.2), 0.88),
      "--accent-foreground": config.foreground,
      "--destructive": destructive,
      "--border": withAlpha(mixHex(config.foreground, config.background, 0.68 - contrastRatio * 0.12), 0.36),
      "--input": withAlpha(mixHex(config.background, "#000000", 0.12), 0.9),
      "--ring": config.accent,
      "--chart-1": config.accent,
      "--chart-2": mixHex(config.accent, "#34d399", 0.56),
      "--chart-3": mixHex(config.accent, "#fbbf24", 0.66),
      "--chart-4": mixHex(config.accent, "#c084fc", 0.58),
      "--chart-5": mixHex(config.accent, "#fb7185", 0.56),
      "--success": success,
      "--success-foreground": readableTextColor(success),
      "--warning": warning,
      "--warning-foreground": readableTextColor(warning),
      "--info": info,
      "--info-foreground": readableTextColor(info),
      "--sidebar": withAlpha(sidebarBase, config.transparentSidebar ? 0.72 : 0.92),
      "--sidebar-foreground": mixHex(config.foreground, config.background, 0.12),
      "--sidebar-primary": config.accent,
      "--sidebar-primary-foreground": accentForeground,
      "--sidebar-accent": withAlpha(mixHex(config.background, config.accent, 0.16), 0.9),
      "--sidebar-accent-foreground": config.foreground,
      "--sidebar-border": withAlpha(mixHex(config.foreground, config.background, 0.75), 0.22),
      "--sidebar-ring": config.accent,
      "--app-background-image": createBackgroundImage(config.background, config.accent, scheme),
      "--app-shell-surface": withAlpha(config.background, 0.18),
      "--app-header-surface": withAlpha(mixHex(config.background, config.foreground, 0.05), 0.74),
      "--app-soft-surface": withAlpha(cardBase, 0.76),
      "--app-overlay-surface": withAlpha(mixHex(config.background, config.foreground, 0.08), 0.92),
      "--app-sticky-surface": withAlpha(mixHex(config.background, config.foreground, 0.06), 0.84),
      "--app-field-surface": withAlpha(mixHex(config.background, "#000000", 0.08), 0.9),
      "--app-dashboard-surface": withAlpha(cardBase, 0.88),
      "--app-dashboard-surface-strong": withAlpha(mixHex(config.background, config.foreground, 0.08), 0.94),
      "--app-dashboard-control": withAlpha(mixHex(config.background, "#000000", 0.1), 0.96),
      "--app-hero-surface": [
        `radial-gradient(circle at top right, ${withAlpha(config.accent, 0.24)}, transparent 28%)`,
        `linear-gradient(135deg, ${withAlpha(mixHex(config.background, config.foreground, 0.08), 0.96)} 0%, ${withAlpha(mixHex(config.background, config.foreground, 0.04), 0.94)} 100%)`
      ].join(", "),
      "--app-soft-shadow": "0 18px 50px rgb(0 0 0 / 0.24)",
      "--app-overlay-shadow": "0 24px 72px rgb(0 0 0 / 0.4)",
      "--app-ui-font-family": config.uiFontFamily,
      "--app-code-font-family": config.codeFontFamily,
      "--app-ui-font-size": String(settings.uiFontSize),
      "--app-code-font-size": String(settings.codeFontSize)
    };
  }

  const cardBase = mixHex(config.background, "#ffffff", 0.48 - contrastRatio * 0.12);
  const sidebarBase = mixHex(config.foreground, config.accent, 0.16);
  return {
    "--background": config.background,
    "--foreground": config.foreground,
    "--card": withAlpha(cardBase, 0.92),
    "--card-foreground": config.foreground,
    "--popover": withAlpha(mixHex(config.background, "#ffffff", 0.65), 0.97),
    "--popover-foreground": config.foreground,
    "--primary": config.accent,
    "--primary-foreground": accentForeground,
    "--secondary": withAlpha(mixHex(config.background, config.accent, 0.08), 0.9),
    "--secondary-foreground": mixHex(config.foreground, "#000000", 0.06),
    "--muted": withAlpha(mixHex(config.background, config.foreground, 0.05 + contrastRatio * 0.05), 0.82),
    "--muted-foreground": mixHex(config.foreground, config.background, 0.34),
    "--accent": withAlpha(mixHex(config.background, config.accent, 0.1), 0.88),
    "--accent-foreground": config.foreground,
    "--destructive": destructive,
    "--border": withAlpha(mixHex(config.foreground, config.background, 0.84 - contrastRatio * 0.06), 0.16),
    "--input": withAlpha(mixHex(config.background, "#ffffff", 0.22), 0.94),
    "--ring": config.accent,
    "--chart-1": config.accent,
    "--chart-2": mixHex(config.accent, "#059669", 0.72),
    "--chart-3": mixHex(config.accent, "#d97706", 0.72),
    "--chart-4": mixHex(config.accent, "#7c3aed", 0.66),
    "--chart-5": mixHex(config.accent, "#ea580c", 0.66),
    "--success": success,
    "--success-foreground": readableTextColor(success),
    "--warning": warning,
    "--warning-foreground": readableTextColor(warning),
    "--info": info,
    "--info-foreground": readableTextColor(info),
    "--sidebar": withAlpha(sidebarBase, config.transparentSidebar ? 0.76 : 0.96),
    "--sidebar-foreground": "#f8fafc",
    "--sidebar-primary": config.accent,
    "--sidebar-primary-foreground": accentForeground,
    "--sidebar-accent": withAlpha(mixHex(sidebarBase, "#ffffff", 0.18), 0.88),
    "--sidebar-accent-foreground": "#f8fafc",
    "--sidebar-border": withAlpha("#ffffff", 0.1),
    "--sidebar-ring": config.accent,
    "--app-background-image": createBackgroundImage(config.background, config.accent, scheme),
    "--app-shell-surface": "transparent",
    "--app-header-surface": withAlpha(mixHex(config.background, "#ffffff", 0.4), 0.88),
    "--app-soft-surface": withAlpha(mixHex(config.background, "#ffffff", 0.3), 0.8),
    "--app-overlay-surface": withAlpha(mixHex(config.background, "#ffffff", 0.46), 0.92),
    "--app-sticky-surface": withAlpha(mixHex(config.background, "#ffffff", 0.5), 0.94),
    "--app-field-surface": withAlpha(mixHex(config.background, "#ffffff", 0.26), 0.94),
    "--app-dashboard-surface": withAlpha(cardBase, 0.9),
    "--app-dashboard-surface-strong": withAlpha(mixHex(config.background, "#ffffff", 0.42), 0.95),
    "--app-dashboard-control": withAlpha(mixHex(config.background, "#ffffff", 0.32), 0.98),
    "--app-hero-surface": [
      `radial-gradient(circle at top right, ${withAlpha(config.accent, 0.14)}, transparent 32%)`,
      `linear-gradient(145deg, ${withAlpha(mixHex(config.background, "#ffffff", 0.36), 0.9)}, ${withAlpha(mixHex(config.background, "#ffffff", 0.22), 0.92)})`
    ].join(", "),
    "--app-soft-shadow": "0 18px 40px rgb(15 23 42 / 0.08)",
    "--app-overlay-shadow": "0 24px 60px rgb(15 23 42 / 0.16)",
    "--app-ui-font-family": config.uiFontFamily,
    "--app-code-font-family": config.codeFontFamily,
    "--app-ui-font-size": String(settings.uiFontSize),
    "--app-code-font-size": String(settings.codeFontSize)
  };
}

function writeAppearanceToDom(settings: AppearanceSettings, scheme: ThemeScheme): void {
  if (typeof document === "undefined") {
    return;
  }

  const root = document.documentElement;
  const variables = buildThemeVariables(settings[scheme], scheme, settings);
  for (const [name, value] of Object.entries(variables)) {
    root.style.setProperty(name, value);
  }
  root.style.colorScheme = scheme;
  root.dataset.interactiveCursor = settings.interactiveCursor ? "true" : "false";
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const { resolvedTheme } = useTheme();
  const [settings, setSettings] = useState<AppearanceSettings>(() => loadSettings());
  const activeScheme: ThemeScheme = resolvedTheme === "dark" ? "dark" : "light";

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage?.setItem(APPEARANCE_STORAGE_KEY, JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    writeAppearanceToDom(settings, activeScheme);
  }, [activeScheme, settings]);

  const value = useMemo<AppearanceContextValue>(
    () => ({
      settings,
      presets: APPEARANCE_PRESETS,
      activeScheme,
      updateThemeConfig: (scheme, patch) => {
        setSettings((current) => {
          const preset = getPresetById(scheme === "light" ? current.lightPresetId : current.darkPresetId);
          const nextConfig = sanitizeThemeConfig(
            { ...current[scheme], ...patch },
            preset[scheme]
          );
          return {
            ...current,
            [scheme]: nextConfig
          };
        });
      },
      applyPreset: (scheme, presetId) => {
        const preset = getPresetById(presetId);
        setSettings((current) =>
          scheme === "light"
            ? {
                ...current,
                light: { ...preset.light },
                lightPresetId: preset.id
              }
            : {
                ...current,
                dark: { ...preset.dark },
                darkPresetId: preset.id
              }
        );
      },
      resetThemeConfig: (scheme) => {
        setSettings((current) => {
          const preset = getPresetById(scheme === "light" ? current.lightPresetId : current.darkPresetId);
          return {
            ...current,
            [scheme]: { ...preset[scheme] }
          };
        });
      },
      updateGlobalSettings: (patch) => {
        setSettings((current) => ({
          ...current,
          uiFontSize: clamp(Number(patch.uiFontSize ?? current.uiFontSize), 12, 18),
          codeFontSize: clamp(Number(patch.codeFontSize ?? current.codeFontSize), 11, 18),
          interactiveCursor:
            typeof patch.interactiveCursor === "boolean" ? patch.interactiveCursor : current.interactiveCursor
        }));
      }
    }),
    [activeScheme, settings]
  );

  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}

export function useAppearance(): AppearanceContextValue {
  const value = useContext(AppearanceContext);
  if (!value) {
    throw new Error("useAppearance must be used within an AppearanceProvider.");
  }
  return value;
}
