const FALLBACK_THEME_COLORS = {
  background: "#0f1117",
  foreground: "#f3f6fb",
  mutedForeground: "#9aa4b2",
  border: "rgba(148, 163, 184, 0.24)",
  chartColors: ["#4f8cff", "#21c87a", "#f3a712", "#8b5cf6", "#ff5b4d"]
} as const;

function resolveColorFromCssVariable(variableName: string, fallback: string): string {
  if (typeof document === "undefined") {
    return fallback;
  }
  const probe = document.createElement("span");
  probe.style.position = "absolute";
  probe.style.pointerEvents = "none";
  probe.style.opacity = "0";
  probe.style.color = `var(${variableName})`;
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).color;
  probe.remove();
  return resolved || fallback;
}

export function readChatThemeColors() {
  return {
    background: resolveColorFromCssVariable("--background", FALLBACK_THEME_COLORS.background),
    foreground: resolveColorFromCssVariable("--foreground", FALLBACK_THEME_COLORS.foreground),
    mutedForeground: resolveColorFromCssVariable("--muted-foreground", FALLBACK_THEME_COLORS.mutedForeground),
    border: resolveColorFromCssVariable("--border", FALLBACK_THEME_COLORS.border),
    chartColors: [
      resolveColorFromCssVariable("--chart-1", FALLBACK_THEME_COLORS.chartColors[0]),
      resolveColorFromCssVariable("--chart-2", FALLBACK_THEME_COLORS.chartColors[1]),
      resolveColorFromCssVariable("--chart-3", FALLBACK_THEME_COLORS.chartColors[2]),
      resolveColorFromCssVariable("--chart-4", FALLBACK_THEME_COLORS.chartColors[3]),
      resolveColorFromCssVariable("--chart-5", FALLBACK_THEME_COLORS.chartColors[4])
    ]
  };
}
