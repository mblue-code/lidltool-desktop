import { type ChangeEvent, type CSSProperties, type ReactNode, useEffect, useMemo, useState } from "react";
import { Check, Copy, Monitor, Moon, RotateCcw, SunMedium } from "lucide-react";
import { useTheme } from "next-themes";
import { toast } from "sonner";

import { useAppearance, type AppearanceThemeConfig } from "@/app/appearance-context";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";

function normalizeDraftHex(value: string): string | null {
  const trimmed = value.trim();
  const withHash = trimmed.startsWith("#") ? trimmed : `#${trimmed}`;
  return /^#[0-9a-fA-F]{6}$/.test(withHash) ? withHash.toLowerCase() : null;
}

function AppearanceModeButton({
  active,
  icon,
  label,
  onClick
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition",
        active
          ? "bg-primary text-primary-foreground shadow-[0_16px_40px_rgb(0_0_0_/_0.18)]"
          : "bg-transparent text-muted-foreground hover:bg-white/5 hover:text-foreground"
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function PresetBadge({
  sample,
  accent,
  background,
  foreground
}: {
  sample: string;
  accent: string;
  background: string;
  foreground: string;
}) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border text-base font-semibold shadow-[inset_0_1px_0_rgb(255_255_255_/_0.08)]"
      style={{
        backgroundColor: background,
        borderColor: `${foreground}33`,
        color: accent,
        boxShadow: `inset 0 1px 0 ${foreground}14`
      }}
    >
      {sample}
    </span>
  );
}

function ColorField({
  label,
  value,
  description,
  onCommit
}: {
  label: string;
  value: string;
  description: string;
  onCommit: (nextValue: string) => void;
}) {
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const commitDraft = () => {
    const normalized = normalizeDraftHex(draft);
    if (normalized) {
      onCommit(normalized);
      setDraft(normalized);
      return;
    }
    setDraft(value);
  };

  return (
    <div className="grid gap-3 rounded-3xl border border-border/60 bg-[var(--app-dashboard-control)]/70 p-4">
      <div className="space-y-1">
        <Label className="text-sm font-medium">{label}</Label>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="flex items-center gap-3">
        <label
          className="relative h-11 w-11 shrink-0 overflow-hidden rounded-2xl border border-white/10 shadow-[inset_0_1px_0_rgb(255_255_255_/_0.12)]"
          style={{ backgroundColor: value }}
        >
          <input
            type="color"
            aria-label={label}
            value={value}
            onChange={(event) => {
              setDraft(event.target.value);
              onCommit(event.target.value);
            }}
            className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
          />
        </label>
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commitDraft}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commitDraft();
            }
          }}
          spellCheck={false}
          className="h-11 rounded-2xl bg-[var(--app-field-surface)] uppercase"
        />
      </div>
    </div>
  );
}

function ThemePreview({
  modeLabel,
  presetLabel,
  config
}: {
  modeLabel: string;
  presetLabel: string;
  config: AppearanceThemeConfig;
}) {
  const previewStyle = useMemo(
    () =>
      ({
        "--preview-accent": config.accent,
        "--preview-background": config.background,
        "--preview-foreground": config.foreground,
        "--preview-card": `color-mix(in srgb, ${config.background} 90%, ${config.foreground} 10%)`,
        "--preview-card-strong": `color-mix(in srgb, ${config.background} 84%, ${config.foreground} 16%)`,
        "--preview-line": `color-mix(in srgb, ${config.foreground} 12%, transparent)`,
        "--preview-muted": `color-mix(in srgb, ${config.foreground} 66%, ${config.background} 34%)`
      }) as CSSProperties,
    [config.accent, config.background, config.foreground]
  );

  return (
    <div
      className="overflow-hidden rounded-[2rem] border border-white/8 shadow-[0_30px_80px_rgb(0_0_0_/_0.18)]"
      style={{
        ...previewStyle,
        background:
          `radial-gradient(circle at top right, ${config.accent}33, transparent 32%), linear-gradient(180deg, color-mix(in srgb, ${config.background} 92%, #ffffff 8%), ${config.background})`
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-4 border-b px-5 py-4" style={{ borderColor: "var(--preview-line)", color: "var(--preview-foreground)" }}>
        <div className="space-y-1">
          <div className="text-sm font-semibold">{modeLabel}</div>
          <div className="text-sm" style={{ color: "var(--preview-muted)" }}>
            {presetLabel}
          </div>
        </div>
        <Badge
          variant="outline"
          className="rounded-full border-white/10 px-3 py-1"
          style={{ color: "var(--preview-foreground)", background: "color-mix(in srgb, var(--preview-card) 80%, transparent)" }}
        >
          {config.accent.toUpperCase()}
        </Badge>
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[1.15fr_0.85fr]">
        <div className="overflow-hidden rounded-[1.5rem] border" style={{ borderColor: "var(--preview-line)", background: "var(--preview-card)" }}>
          <div className="grid grid-cols-2 divide-x" style={{ color: "var(--preview-foreground)", borderColor: "var(--preview-line)" }}>
            {[0, 1].map((index) => (
              <div key={index} className="space-y-2 p-4 font-mono text-sm">
                <div className="flex items-center gap-3 text-xs" style={{ color: "var(--preview-muted)" }}>
                  <span>{index + 1}</span>
                  <span>{index === 0 ? "const themePreview = {" : "surface: \"sidebar-elevated\","}</span>
                </div>
                {index === 0 ? (
                  <>
                    <div>
                      <span style={{ color: "var(--preview-muted)" }}>  accent:</span>{" "}
                      <span style={{ color: "var(--preview-accent)" }}>"{config.accent}"</span>,
                    </div>
                    <div>
                      <span style={{ color: "var(--preview-muted)" }}>  background:</span>{" "}
                      <span>"{config.background}"</span>,
                    </div>
                    <div>
                      <span style={{ color: "var(--preview-muted)" }}>  foreground:</span>{" "}
                      <span>"{config.foreground}"</span>,
                    </div>
                    <div>
                      <span style={{ color: "var(--preview-muted)" }}>  contrast:</span> {config.contrast}
                    </div>
                    <div style={{ color: "var(--preview-muted)" }}>{"};"}</div>
                  </>
                ) : (
                  <>
                    <div className="rounded-2xl border px-3 py-2" style={{ borderColor: "var(--preview-line)", background: "var(--preview-card-strong)" }}>
                      <div className="text-xs" style={{ color: "var(--preview-muted)" }}>
                        UI font
                      </div>
                      <div className="truncate text-base font-medium" style={{ fontFamily: config.uiFontFamily }}>
                        {config.uiFontFamily}
                      </div>
                    </div>
                    <div className="rounded-2xl border px-3 py-2" style={{ borderColor: "var(--preview-line)", background: "var(--preview-card-strong)" }}>
                      <div className="text-xs" style={{ color: "var(--preview-muted)" }}>
                        Code font
                      </div>
                      <div className="truncate text-sm" style={{ fontFamily: config.codeFontFamily }}>
                        {config.codeFontFamily}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 pt-1">
                      <span className="h-3 w-3 rounded-full" style={{ backgroundColor: config.accent }} />
                      <span className="text-xs" style={{ color: "var(--preview-muted)" }}>
                        Sidebar transparency {config.transparentSidebar ? "on" : "off"}
                      </span>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-3">
          <div className="rounded-[1.5rem] border p-4" style={{ borderColor: "var(--preview-line)", background: "var(--preview-card)" }}>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold" style={{ color: "var(--preview-foreground)" }}>
                  Surface sample
                </div>
                <div className="text-xs" style={{ color: "var(--preview-muted)" }}>
                  Primary action, contrast, and quiet surfaces.
                </div>
              </div>
              <button
                type="button"
                className="rounded-full px-3 py-1.5 text-sm font-medium"
                style={{ backgroundColor: config.accent, color: readablePreviewText(config.accent) }}
              >
                Save
              </button>
            </div>
            <div className="space-y-2">
              <div className="h-2 rounded-full" style={{ backgroundColor: `${config.foreground}14` }}>
                <div className="h-full rounded-full" style={{ width: `${Math.max(18, config.contrast)}%`, backgroundColor: config.accent }} />
              </div>
              <div className="grid grid-cols-3 gap-2">
                {[config.accent, config.background, config.foreground].map((color) => (
                  <div key={color} className="rounded-2xl border px-3 py-3 text-xs" style={{ borderColor: "var(--preview-line)", background: color, color: readablePreviewText(color) }}>
                    {color.toUpperCase()}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-[1.5rem] border p-4" style={{ borderColor: "var(--preview-line)", background: "var(--preview-card)" }}>
            <div className="text-xs uppercase tracking-[0.18em]" style={{ color: "var(--preview-muted)" }}>
              Typography
            </div>
            <div className="mt-3 space-y-2">
              <div className="text-lg font-semibold" style={{ fontFamily: config.uiFontFamily, color: "var(--preview-foreground)" }}>
                Ledger, syncs, and receipts stay calm.
              </div>
              <div className="text-sm" style={{ color: "var(--preview-muted)" }}>
                The editor drives shared layout tokens instead of styling one page in isolation.
              </div>
              <div
                className="rounded-2xl border px-3 py-2 font-mono text-sm"
                style={{ borderColor: "var(--preview-line)", background: "var(--preview-card-strong)", color: "var(--preview-foreground)", fontFamily: config.codeFontFamily }}
              >
                theme.apply({"{"} accent: "{config.accent}" {"}"})
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function readablePreviewText(color: string): string {
  const hex = color.replace("#", "");
  const red = Number.parseInt(hex.slice(0, 2), 16);
  const green = Number.parseInt(hex.slice(2, 4), 16);
  const blue = Number.parseInt(hex.slice(4, 6), 16);
  const luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255;
  return luminance > 0.52 ? "#111111" : "#ffffff";
}

export function AppearanceSettingsPage() {
  const { locale } = useI18n();
  const { theme, setTheme, resolvedTheme } = useTheme();
  const { settings, presets, activeScheme, applyPreset, resetThemeConfig, updateGlobalSettings, updateThemeConfig } =
    useAppearance();
  const currentTheme = settings[activeScheme];
  const isGerman = locale === "de";
  const selectedPresetId = activeScheme === "dark" ? settings.darkPresetId : settings.lightPresetId;

  const modeLabel =
    theme === "light"
      ? isGerman
        ? "Helles Design"
        : "Light design"
      : theme === "dark"
        ? isGerman
          ? "Dunkles Design"
          : "Dark design"
        : isGerman
          ? `Systemdesign (${resolvedTheme === "dark" ? "dunkel" : "hell"})`
          : `System design (${resolvedTheme === "dark" ? "dark" : "light"})`;

  const copyTheme = async () => {
    const payload = JSON.stringify(
      {
        mode: theme ?? "system",
        editing: activeScheme,
        preset: selectedPresetId,
        ...currentTheme,
        uiFontSize: settings.uiFontSize,
        codeFontSize: settings.codeFontSize,
        interactiveCursor: settings.interactiveCursor
      },
      null,
      2
    );
    await navigator.clipboard.writeText(payload);
    toast.success(isGerman ? "Design kopiert" : "Theme copied");
  };

  const sectionTitle = isGerman ? "Darstellung" : "Appearance";
  const sectionDescription = isGerman
    ? "Desktop-Optik lokal anpassen: Motiv, Akzent, Typografie und Dichte greifen direkt in die Shell-Tokens ein."
    : "Adjust the desktop look locally. Theme mode, accent, typography, and density feed the shared shell tokens directly.";

  return (
    <div className="space-y-6">
      <PageHeader title={sectionTitle} description={sectionDescription} />

      <section className="overflow-hidden rounded-[2rem] border border-white/8 bg-[var(--app-dashboard-surface)] shadow-[0_30px_80px_rgb(0_0_0_/_0.18)]">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 px-5 py-5 sm:px-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">{isGerman ? "Motiv" : "Theme mode"}</h2>
            <p className="text-sm text-muted-foreground">
              {isGerman
                ? "Hell, dunkel oder an dein System anpassen. Die Vorschau zeigt immer das gerade aktive Design."
                : "Choose light, dark, or system. The editor always previews the currently active design."}
            </p>
          </div>
          <div className="inline-flex items-center gap-1 rounded-full border border-white/8 bg-[var(--app-dashboard-control)] p-1">
            <AppearanceModeButton
              active={(theme ?? "system") === "light"}
              icon={<SunMedium className="h-4 w-4" />}
              label={isGerman ? "Hell" : "Light"}
              onClick={() => setTheme("light")}
            />
            <AppearanceModeButton
              active={(theme ?? "system") === "dark"}
              icon={<Moon className="h-4 w-4" />}
              label={isGerman ? "Dunkel" : "Dark"}
              onClick={() => setTheme("dark")}
            />
            <AppearanceModeButton
              active={(theme ?? "system") === "system"}
              icon={<Monitor className="h-4 w-4" />}
              label={isGerman ? "System" : "System"}
              onClick={() => setTheme("system")}
            />
          </div>
        </div>

        <div className="space-y-6 p-4 sm:p-6">
          <ThemePreview
            modeLabel={modeLabel}
            presetLabel={presets.find((preset) => preset.id === selectedPresetId)?.label ?? "Custom"}
            config={currentTheme}
          />

          <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="rounded-[2rem] border border-white/8 bg-[var(--app-dashboard-control)]/70 p-5 sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold">{modeLabel}</h3>
                  <p className="text-sm text-muted-foreground">
                    {isGerman
                      ? "Presets geben dir einen sauberen Startpunkt, danach kannst du jede Variable weiterziehen."
                      : "Presets provide a clean starting point, then you can push every variable further."}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" variant="outline" className="rounded-2xl" onClick={() => resetThemeConfig(activeScheme)}>
                    <RotateCcw className="mr-2 h-4 w-4" />
                    {isGerman ? "Zurücksetzen" : "Reset"}
                  </Button>
                  <Button type="button" variant="outline" className="rounded-2xl" onClick={() => void copyTheme()}>
                    <Copy className="mr-2 h-4 w-4" />
                    {isGerman ? "Design kopieren" : "Copy theme"}
                  </Button>
                </div>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
                <div className="space-y-2">
                  <Label>{isGerman ? "Design-Preset" : "Theme preset"}</Label>
                  <Select
                    value={selectedPresetId}
                    onValueChange={(value) => {
                      applyPreset(activeScheme, value);
                      toast.success(isGerman ? "Preset angewendet" : "Preset applied");
                    }}
                  >
                    <SelectTrigger className="h-14 rounded-2xl">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {presets.map((preset) => (
                        <SelectItem key={preset.id} value={preset.id}>
                          {preset.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid gap-3 rounded-[1.5rem] border border-border/60 bg-[var(--app-dashboard-surface)] p-4 sm:grid-cols-2 lg:grid-cols-3">
                  {presets.map((preset) => {
                    const swatch = preset[activeScheme];
                    const selected = preset.id === selectedPresetId;
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        onClick={() => applyPreset(activeScheme, preset.id)}
                        className={cn(
                          "flex items-center gap-3 rounded-[1.25rem] border px-3 py-3 text-left transition",
                          selected
                            ? "border-primary bg-primary/10"
                            : "border-white/8 bg-[var(--app-dashboard-control)] hover:border-white/16 hover:bg-white/5"
                        )}
                      >
                        <PresetBadge
                          sample={preset.sample}
                          accent={swatch.accent}
                          background={swatch.background}
                          foreground={swatch.foreground}
                        />
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">{preset.label}</div>
                          <div className="truncate text-xs text-muted-foreground">{swatch.accent.toUpperCase()}</div>
                        </div>
                        {selected ? <Check className="ml-auto h-4 w-4 text-primary" /> : null}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="mt-6 grid gap-4 lg:grid-cols-3">
                <ColorField
                  label={isGerman ? "Akzent" : "Accent"}
                  value={currentTheme.accent}
                  description={
                    isGerman
                      ? "Akzentfarbe fur primare Aktionen, Fokus und Markierungen."
                      : "Primary action, focus, and emphasis color."
                  }
                  onCommit={(nextValue) => updateThemeConfig(activeScheme, { accent: nextValue })}
                />
                <ColorField
                  label={isGerman ? "Hintergrund" : "Background"}
                  value={currentTheme.background}
                  description={
                    isGerman
                      ? "Basis fur Flachen, Verlauf und die ruhige Produktatmosphare."
                      : "Base color for surfaces, gradients, and the overall product atmosphere."
                  }
                  onCommit={(nextValue) => updateThemeConfig(activeScheme, { background: nextValue })}
                />
                <ColorField
                  label={isGerman ? "Vordergrund" : "Foreground"}
                  value={currentTheme.foreground}
                  description={
                    isGerman
                      ? "Schriftfarbe und Kontrastpartner fur Linien und ruhige Texte."
                      : "Text color and the contrast anchor for borders and secondary copy."
                  }
                  onCommit={(nextValue) => updateThemeConfig(activeScheme, { foreground: nextValue })}
                />
              </div>

              <div className="mt-6 grid gap-4 lg:grid-cols-2">
                <div className="grid gap-2 rounded-[1.5rem] border border-border/60 bg-[var(--app-dashboard-surface)] p-4">
                  <Label htmlFor="appearance-ui-font">{isGerman ? "UI-Schriftart" : "UI font family"}</Label>
                  <Input
                    id="appearance-ui-font"
                    value={currentTheme.uiFontFamily}
                    onChange={(event) => updateThemeConfig(activeScheme, { uiFontFamily: event.target.value })}
                    className="h-11 rounded-2xl"
                  />
                </div>
                <div className="grid gap-2 rounded-[1.5rem] border border-border/60 bg-[var(--app-dashboard-surface)] p-4">
                  <Label htmlFor="appearance-code-font">{isGerman ? "Code-Schriftart" : "Code font family"}</Label>
                  <Input
                    id="appearance-code-font"
                    value={currentTheme.codeFontFamily}
                    onChange={(event) => updateThemeConfig(activeScheme, { codeFontFamily: event.target.value })}
                    className="h-11 rounded-2xl"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <Card className="rounded-[2rem] border-white/8 bg-[var(--app-dashboard-control)]/70">
                <CardHeader>
                  <CardTitle>{isGerman ? "Dichte und Verhalten" : "Density and behavior"}</CardTitle>
                  <CardDescription>
                    {isGerman
                      ? "Diese Werte greifen global auf Shell, Menus und Editor-Oberflachen."
                      : "These values feed the shared shell, menus, and editor surfaces."}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                  <div className="grid gap-3 rounded-[1.5rem] border border-border/60 bg-[var(--app-dashboard-surface)] p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <Label htmlFor="appearance-sidebar-transparency">
                          {isGerman ? "Transparente Seitenleiste" : "Transparent sidebar"}
                        </Label>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {isGerman
                            ? "Lasst die Navigation etwas mehr vom Hintergrund aufnehmen."
                            : "Lets the navigation pick up more of the background wash."}
                        </p>
                      </div>
                      <Switch
                        id="appearance-sidebar-transparency"
                        checked={currentTheme.transparentSidebar}
                        onCheckedChange={(checked) => updateThemeConfig(activeScheme, { transparentSidebar: checked })}
                      />
                    </div>
                  </div>

                  <div className="grid gap-3 rounded-[1.5rem] border border-border/60 bg-[var(--app-dashboard-surface)] p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <Label htmlFor="appearance-cursor">
                          {isGerman ? "Zeiger-Cursor verwenden" : "Use pointer cursor"}
                        </Label>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {isGerman
                            ? "Erzwingt einen Pointer auf interaktiven Elementen."
                            : "Forces a pointer cursor on interactive elements."}
                        </p>
                      </div>
                      <Switch
                        id="appearance-cursor"
                        checked={settings.interactiveCursor}
                        onCheckedChange={(checked) => updateGlobalSettings({ interactiveCursor: checked })}
                      />
                    </div>
                  </div>

                  <div className="grid gap-3 rounded-[1.5rem] border border-border/60 bg-[var(--app-dashboard-surface)] p-4">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="appearance-contrast">{isGerman ? "Kontrast" : "Contrast"}</Label>
                      <Badge variant="outline" className="rounded-full px-3 py-1">
                        {currentTheme.contrast}
                      </Badge>
                    </div>
                    <input
                      id="appearance-contrast"
                      type="range"
                      min={0}
                      max={100}
                      value={currentTheme.contrast}
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        updateThemeConfig(activeScheme, { contrast: Number(event.target.value) })
                      }
                      className="h-2 w-full cursor-pointer appearance-none rounded-full bg-primary/20 accent-[var(--primary)]"
                    />
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="grid gap-2 rounded-[1.5rem] border border-border/60 bg-[var(--app-dashboard-surface)] p-4">
                      <Label htmlFor="appearance-ui-size">{isGerman ? "UI-Schriftgrosse" : "UI font size"}</Label>
                      <div className="flex items-center gap-3">
                        <Input
                          id="appearance-ui-size"
                          type="number"
                          min={12}
                          max={18}
                          value={settings.uiFontSize}
                          onChange={(event) => updateGlobalSettings({ uiFontSize: Number(event.target.value) })}
                          className="h-11 rounded-2xl"
                        />
                        <span className="text-sm text-muted-foreground">px</span>
                      </div>
                    </div>
                    <div className="grid gap-2 rounded-[1.5rem] border border-border/60 bg-[var(--app-dashboard-surface)] p-4">
                      <Label htmlFor="appearance-code-size">{isGerman ? "Code-Schriftgrosse" : "Code font size"}</Label>
                      <div className="flex items-center gap-3">
                        <Input
                          id="appearance-code-size"
                          type="number"
                          min={11}
                          max={18}
                          value={settings.codeFontSize}
                          onChange={(event) => updateGlobalSettings({ codeFontSize: Number(event.target.value) })}
                          className="h-11 rounded-2xl"
                        />
                        <span className="text-sm text-muted-foreground">px</span>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="rounded-[2rem] border-white/8 bg-[var(--app-dashboard-control)]/70">
                <CardHeader>
                  <CardTitle>{isGerman ? "Was diese Version kann" : "What this version covers"}</CardTitle>
                  <CardDescription>
                    {isGerman
                      ? "Das ist bewusst die erste produktionsreife Stufe, nicht nur ein Mockup."
                      : "This is intentionally the first production-ready cut, not just a mockup."}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm text-muted-foreground">
                  <p>{isGerman ? "Presets pro Modus, direkte Token-Anwendung und lokale Persistenz." : "Per-mode presets, direct token application, and local persistence."}</p>
                  <p>{isGerman ? "Akzent-, Hintergrund- und Vordergrundfarben beeinflussen die gesamte Desktop-Shell." : "Accent, background, and foreground colors influence the whole desktop shell."}</p>
                  <p>{isGerman ? "Typografie, Kontrast und Sidebar-Transparenz greifen in Navigation, Dialoge und Listen." : "Typography, contrast, and sidebar transparency feed navigation, dialogs, and list surfaces."}</p>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
