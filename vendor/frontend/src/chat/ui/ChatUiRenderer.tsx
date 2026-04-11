import type * as React from "react";
import { CSSProperties, ReactNode } from "react";
import { defineCatalog, type Spec } from "@json-render/core";
import { JSONUIProvider, defineRegistry, Renderer } from "@json-render/react";
import { schema } from "@json-render/react/schema";
import { z } from "zod";

import { ChatUiSpec } from "@/chat/ui/spec";
import { readChatThemeColors } from "@/chat/ui/themeColors";
import { cn } from "@/lib/utils";

type ChartPoint = {
  label: string;
  value: number;
  index?: number;
};

type LineSeriesDefinition = {
  key: string;
  label: string;
  color?: string;
};

type LineSeries = {
  definition: LineSeriesDefinition;
  points: ChartPoint[];
};

type RenderVariant = "inline" | "large" | "export";

function chartViewportWidth({
  points,
  minWidth,
  maxWidth,
  pixelsPerPoint
}: {
  points: number;
  minWidth: number;
  maxWidth: number;
  pixelsPerPoint: number;
}): number {
  return Math.max(minWidth, Math.min(maxWidth, Math.round(points * pixelsPerPoint)));
}

function chartLabelStep({
  pointCount,
  width,
  minLabelWidth
}: {
  pointCount: number;
  width: number;
  minLabelWidth: number;
}): number {
  const labelCapacity = Math.max(1, Math.floor(width / minLabelWidth));
  return Math.max(1, Math.ceil(pointCount / labelCapacity));
}

function formatCompactValue(value: number): string {
  if (Math.abs(value) >= 1000) {
    return new Intl.NumberFormat(undefined, {
      notation: "compact",
      maximumFractionDigits: 1
    }).format(value);
  }
  if (Number.isInteger(value)) {
    return value.toString();
  }
  return value.toFixed(1);
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function chartPointsFromData(
  data: Array<Record<string, unknown>>,
  xKey: string,
  yKey: string
): ChartPoint[] {
  const points: ChartPoint[] = [];
  for (const [index, row] of data.entries()) {
    const yValue = toFiniteNumber(row[yKey]);
    if (yValue === null) {
      continue;
    }
    const rawLabel = row[xKey];
    points.push({
      label: String(rawLabel ?? ""),
      value: yValue,
      index
    });
  }
  return points;
}

function truncateAxisLabel(label: string, maxLength: number): string {
  if (label.length <= maxLength) {
    return label;
  }
  return `${label.slice(0, Math.max(1, maxLength - 1))}…`;
}

function chartFrame(
  title: string | undefined,
  body: React.JSX.Element,
  className?: string
) {
  return (
    <section
      className={cn(
        "overflow-hidden rounded-xl border border-border/70 bg-gradient-to-b from-background to-muted/20 p-4 shadow-sm",
        className
      )}
    >
      {title ? <h4 className="mb-3 text-sm font-semibold tracking-tight">{title}</h4> : null}
      {body}
    </section>
  );
}

function emptyChartState(text = "No plottable numeric data available.") {
  return <p className="text-xs text-muted-foreground">{text}</p>;
}

function MetricCard({
  title,
  value,
  subtitle,
  trend
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  trend?: { value: string | number; direction: "up" | "down" | "neutral" };
}) {
  const trendClass =
    trend?.direction === "up"
      ? "text-success"
      : trend?.direction === "down"
        ? "text-destructive"
        : "text-muted-foreground";

  return chartFrame(
    undefined,
    <div className="space-y-2 rounded-lg bg-background/70 p-1">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">{title}</p>
      <p className="text-3xl font-semibold leading-none tracking-tight">{value}</p>
      {subtitle ? <p className="text-xs text-muted-foreground">{subtitle}</p> : null}
      {trend ? <p className={cn("text-xs font-medium", trendClass)}>{trend.value}</p> : null}
    </div>
  );
}

function Callout({
  tone,
  title,
  body
}: {
  tone: "info" | "success" | "warning" | "error";
  title: string;
  body: string;
}) {
  const toneClassByValue: Record<typeof tone, string> = {
    info: "border-info/40 bg-info/5",
    success: "border-success/40 bg-success/5",
    warning: "border-warning/40 bg-warning/5",
    error: "border-destructive/40 bg-destructive/5"
  };

  return (
    <section className={cn("rounded-lg border p-3", toneClassByValue[tone])}>
      <h4 className="text-sm font-semibold">{title}</h4>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </section>
  );
}

function TableElement({
  title,
  columns,
  rows
}: {
  title?: string;
  columns: string[];
  rows: Array<Array<string | number | null>>;
}) {
  return chartFrame(
    title,
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-sm">
        <thead className="bg-background/95 backdrop-blur">
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                className="border-b border-border/70 px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`row-${rowIndex}`} className={rowIndex % 2 === 0 ? "bg-background/40" : "bg-transparent"}>
              {row.map((value, columnIndex) => (
                <td
                  key={`cell-${rowIndex}-${columnIndex}`}
                  className="border-b border-border/50 px-3 py-2 align-top"
                >
                  {value === null ? "-" : String(value)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function axisTicks({ min, max, count }: { min: number; max: number; count: number }): number[] {
  if (count <= 1 || max <= min) {
    return [min, max];
  }
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, index) => min + step * index);
}

function LineChart({
  title,
  x,
  y,
  series,
  data,
  variant = "inline"
}: {
  title?: string;
  x: string;
  y?: string | string[];
  series?: Array<{ key: string; label?: string; color?: string }>;
  data: Array<Record<string, unknown>>;
  variant?: RenderVariant;
}) {
  const normalizedSeries: LineSeriesDefinition[] = Array.isArray(series) && series.length > 0
    ? series.map((entry) => ({
        key: entry.key,
        label: entry.label?.trim() || entry.key,
        color: entry.color
      }))
    : Array.isArray(y)
      ? y.map((key) => ({ key, label: key }))
      : typeof y === "string"
        ? [{ key: y, label: y }]
        : [];

  const lineSeries = normalizedSeries
    .map<LineSeries>((definition) => ({
      definition,
      points: chartPointsFromData(data, x, definition.key)
    }))
    .filter((entry) => entry.points.length > 0);

  if (lineSeries.length === 0) {
    return chartFrame(title, emptyChartState());
  }
  const palette = readChatThemeColors();
  const expanded = variant !== "inline";
  const exportMode = variant === "export";
  const xLabels = data.map((row) => String(row[x] ?? ""));
  const longestLabel = Math.max(...xLabels.map((label) => label.length), 0);
  const denseLabels = xLabels.length > 8 || longestLabel > 10;
  const isMultiSeries = lineSeries.length > 1;

  const width = chartViewportWidth({
    points: xLabels.length,
    minWidth: expanded ? 920 : 720,
    maxWidth: expanded ? 2400 : 1800,
    pixelsPerPoint: denseLabels ? (expanded ? 96 : 84) : expanded ? 76 : 64
  });
  const height = denseLabels ? (expanded ? 420 : 340) : expanded ? 360 : 300;
  const paddingLeft = expanded ? 62 : 54;
  const paddingRight = expanded ? 30 : 24;
  const paddingTop = expanded ? 28 : 24;
  const paddingBottom = denseLabels ? (expanded ? 120 : 92) : expanded ? 60 : 48;
  const innerWidth = width - paddingLeft - paddingRight;
  const innerHeight = height - paddingTop - paddingBottom;
  const allPoints = lineSeries.flatMap((entry) => entry.points);
  const minValue = Math.min(...allPoints.map((point) => point.value));
  const maxValue = Math.max(...allPoints.map((point) => point.value));
  const yMin = minValue > 0 ? 0 : minValue;
  const yMax = maxValue === yMin ? yMin + 1 : maxValue;

  const xPosition = (index: number): number => {
    if (xLabels.length <= 1) {
      return paddingLeft + innerWidth / 2;
    }
    return paddingLeft + (index / (xLabels.length - 1)) * innerWidth;
  };
  const yPosition = (value: number): number => {
    const ratio = (value - yMin) / (yMax - yMin);
    return paddingTop + (1 - ratio) * innerHeight;
  };

  const ticks = axisTicks({ min: yMin, max: yMax, count: 4 });
  const labelStep = chartLabelStep({
    pointCount: xLabels.length,
    width: innerWidth,
    minLabelWidth: denseLabels ? 92 : 74
  });
  const gradientId = `line-fill-${title ?? x}-${typeof y === "string" ? y : "series"}`
    .replace(/[^a-zA-Z0-9_-]+/g, "-");
  const showDots = Math.max(...lineSeries.map((entry) => entry.points.length), 0) <= (expanded ? 28 : 18);

  const svg = (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={cn("block", expanded ? (denseLabels ? "h-96" : "h-80") : denseLabels ? "h-72" : "h-64")}
      style={exportMode ? { width: `${width}px` } : { width: `${width}px`, minWidth: "100%" }}
    >
      {!isMultiSeries ? (
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={lineSeries[0]?.definition.color || palette.chartColors[0]} stopOpacity="0.28" />
            <stop offset="100%" stopColor={lineSeries[0]?.definition.color || palette.chartColors[0]} stopOpacity="0.03" />
          </linearGradient>
        </defs>
      ) : null}
      <rect
        x={paddingLeft}
        y={paddingTop}
        width={innerWidth}
        height={innerHeight}
        rx={10}
        fill={palette.background}
        fillOpacity={0.42}
        stroke={palette.border}
        strokeOpacity={0.4}
      />
      {ticks.map((tick) => {
        const yTick = yPosition(tick);
        return (
          <g key={`tick-${tick}`}>
            <line
              x1={paddingLeft}
              x2={width - paddingRight}
              y1={yTick}
              y2={yTick}
              stroke={palette.border}
              strokeDasharray="4 6"
            />
            <text
              x={paddingLeft - 10}
              y={yTick + 4}
              textAnchor="end"
              fill={palette.mutedForeground}
              fontSize={expanded ? 12 : 11}
            >
              {formatCompactValue(tick)}
            </text>
          </g>
        );
      })}
      <line
        x1={paddingLeft}
        x2={width - paddingRight}
        y1={paddingTop + innerHeight}
        y2={paddingTop + innerHeight}
        stroke={palette.border}
        strokeOpacity={0.65}
      />
      {!isMultiSeries && lineSeries[0] ? (
        <>
          <polygon
            points={[
              `${paddingLeft},${paddingTop + innerHeight}`,
              ...lineSeries[0].points.map((point) => `${xPosition(point.index ?? 0)},${yPosition(point.value)}`),
              `${paddingLeft + innerWidth},${paddingTop + innerHeight}`
            ].join(" ")}
            fill={`url(#${gradientId})`}
          />
          <polyline
            points={lineSeries[0].points
              .map((point) => `${xPosition(point.index ?? 0)},${yPosition(point.value)}`)
              .join(" ")}
            fill="none"
            stroke={lineSeries[0].definition.color || palette.chartColors[0]}
            strokeWidth={2.5}
          />
        </>
      ) : null}
      {isMultiSeries
        ? lineSeries.map((entry, seriesIndex) => (
            <polyline
              key={`series-line-${entry.definition.key}`}
              points={entry.points
                .map((point) => `${xPosition(point.index ?? 0)},${yPosition(point.value)}`)
                .join(" ")}
              fill="none"
              stroke={entry.definition.color || palette.chartColors[seriesIndex % palette.chartColors.length]}
              strokeWidth={2.4}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))
        : null}
      {showDots
        ? lineSeries.flatMap((entry, seriesIndex) =>
            entry.points.map((point, pointIndex) => {
              const color = entry.definition.color || palette.chartColors[seriesIndex % palette.chartColors.length];
              return (
                <g key={`dot-${entry.definition.key}-${pointIndex}`}>
                  <circle
                    cx={xPosition(point.index ?? 0)}
                    cy={yPosition(point.value)}
                    r={isMultiSeries ? 4 : 5}
                    fill={palette.background}
                    fillOpacity={0.92}
                  />
                  <circle
                    cx={xPosition(point.index ?? 0)}
                    cy={yPosition(point.value)}
                    r={isMultiSeries ? 2.2 : 2.8}
                    fill={color}
                  />
                </g>
              );
            })
          )
        : null}
      {xLabels.map((label, index) => {
        if (index !== xLabels.length - 1 && index % labelStep !== 0) {
          return null;
        }
        const xCoord = xPosition(index);
        const yCoord = height - 16;
        return (
          <text
            key={`x-${index}`}
            x={xCoord}
            y={yCoord}
            textAnchor={denseLabels ? "end" : "middle"}
            transform={denseLabels ? `rotate(-35 ${xCoord} ${yCoord})` : undefined}
            fill={palette.mutedForeground}
            fontSize={expanded ? 12 : 11}
            fontWeight={500}
          >
            {truncateAxisLabel(label, denseLabels ? 16 : 24)}
          </text>
        );
      })}
    </svg>
  );

  return chartFrame(
    title,
    <div className="space-y-3">
      {isMultiSeries ? (
        <div className="flex flex-wrap gap-2">
          {lineSeries.map((entry, seriesIndex) => {
            const color = entry.definition.color || palette.chartColors[seriesIndex % palette.chartColors.length];
            return (
              <span
                key={`legend-${entry.definition.key}`}
                className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/75 px-2.5 py-1 text-[11px] font-medium text-foreground/90"
              >
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: color }}
                />
                {entry.definition.label}
              </span>
            );
          })}
        </div>
      ) : null}
      <div
        className={cn(exportMode ? "inline-block pb-2" : "overflow-x-auto pb-2")}
        style={exportMode ? { width: `${width}px` } : undefined}
      >
        {svg}
      </div>
    </div>
  );
}

function BarChart({
  title,
  x,
  y,
  data,
  variant = "inline"
}: {
  title?: string;
  x: string;
  y: string;
  data: Array<Record<string, unknown>>;
  variant?: RenderVariant;
}) {
  const points = chartPointsFromData(data, x, y);
  if (points.length === 0) {
    return chartFrame(title, emptyChartState());
  }
  const palette = readChatThemeColors();
  const expanded = variant !== "inline";
  const exportMode = variant === "export";
  const longestLabel = Math.max(...points.map((point) => point.label.length), 0);
  const denseLabels = points.length > 8 || longestLabel > 10;

  const width = chartViewportWidth({
    points: points.length,
    minWidth: expanded ? 980 : 760,
    maxWidth: expanded ? 2600 : 1960,
    pixelsPerPoint: denseLabels ? (expanded ? 104 : 88) : expanded ? 84 : 72
  });
  const height = denseLabels ? (expanded ? 440 : 360) : expanded ? 360 : 300;
  const paddingLeft = expanded ? 62 : 54;
  const paddingRight = expanded ? 30 : 24;
  const paddingTop = expanded ? 28 : 24;
  const paddingBottom = denseLabels ? (expanded ? 136 : 112) : expanded ? 68 : 56;
  const innerWidth = width - paddingLeft - paddingRight;
  const innerHeight = height - paddingTop - paddingBottom;
  const maxValue = Math.max(...points.map((point) => point.value), 1);
  const minValue = Math.min(...points.map((point) => point.value), 0);
  const yMin = minValue < 0 ? minValue : 0;
  const yMax = maxValue;
  const ticks = axisTicks({ min: yMin, max: yMax, count: 4 });
  const labelStep = chartLabelStep({
    pointCount: points.length,
    width: innerWidth,
    minLabelWidth: denseLabels ? 92 : 78
  });
  const showValueLabels = points.length <= Math.max(10, Math.floor(width / 110));

  const band = innerWidth / points.length;
  const barWidth = Math.max(12, band * 0.64);

  const yPosition = (value: number): number => {
    const ratio = (value - yMin) / (yMax - yMin || 1);
    return paddingTop + (1 - ratio) * innerHeight;
  };

  const zeroY = yPosition(0);

  return chartFrame(
    title,
    <div
      className={cn(exportMode ? "inline-block pb-2" : "overflow-x-auto pb-2")}
      style={exportMode ? { width: `${width}px` } : undefined}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className={cn("block", expanded ? "h-[28rem]" : "h-72")}
        style={exportMode ? { width: `${width}px` } : { width: `${width}px`, minWidth: "100%" }}
      >
        <rect
          x={paddingLeft}
          y={paddingTop}
          width={innerWidth}
          height={innerHeight}
          rx={10}
          fill={palette.background}
          fillOpacity={0.42}
          stroke={palette.border}
          strokeOpacity={0.4}
        />
        {ticks.map((tick) => {
          const yTick = yPosition(tick);
          return (
            <g key={`tick-${tick}`}>
              <line
                x1={paddingLeft}
                x2={width - paddingRight}
                y1={yTick}
                y2={yTick}
                stroke={palette.border}
                strokeDasharray="4 6"
              />
              <text
                x={paddingLeft - 10}
                y={yTick + 4}
                textAnchor="end"
                fill={palette.mutedForeground}
                fontSize={expanded ? 12 : 11}
              >
                {formatCompactValue(tick)}
              </text>
            </g>
          );
        })}
        <line
          x1={paddingLeft}
          x2={width - paddingRight}
          y1={zeroY}
          y2={zeroY}
          stroke={palette.border}
          strokeOpacity={0.7}
        />
        {points.map((point, index) => {
          const xPos = paddingLeft + index * band + (band - barWidth) / 2;
          const yPos = yPosition(point.value);
          const barHeight = Math.max(1, Math.abs(zeroY - yPos));
          return (
            <g key={`bar-${index}`}>
              <rect
                x={xPos}
                y={point.value >= 0 ? yPos : zeroY}
                width={barWidth}
                height={barHeight}
                rx={4}
                fill={palette.chartColors[index % palette.chartColors.length]}
              />
              {showValueLabels ? (
                <text
                  x={xPos + barWidth / 2}
                  y={point.value >= 0 ? yPos - 8 : zeroY + barHeight + 14}
                  textAnchor="middle"
                  fill={palette.foreground}
                  fontSize={expanded ? 12 : 11}
                  fontWeight={600}
                >
                  {formatCompactValue(point.value)}
                </text>
              ) : null}
              {index === points.length - 1 || index % labelStep === 0 ? (
                <text
                  x={xPos + barWidth / 2}
                  y={height - 18}
                  textAnchor={denseLabels ? "end" : "middle"}
                  transform={denseLabels ? `rotate(-35 ${xPos + barWidth / 2} ${height - 18})` : undefined}
                  fill={palette.mutedForeground}
                  fontSize={expanded ? 12 : 11}
                  fontWeight={500}
                >
                  {truncateAxisLabel(point.label, denseLabels ? 16 : 24)}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function pieSlicePath(
  cx: number,
  cy: number,
  radius: number,
  startAngle: number,
  endAngle: number
): string {
  const startX = cx + radius * Math.cos(startAngle);
  const startY = cy + radius * Math.sin(startAngle);
  const endX = cx + radius * Math.cos(endAngle);
  const endY = cy + radius * Math.sin(endAngle);
  const largeArcFlag = endAngle - startAngle > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${startX} ${startY} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${endX} ${endY} Z`;
}

function PieChart({
  title,
  label,
  value,
  data,
  variant = "inline"
}: {
  title?: string;
  label: string;
  value: string;
  data: Array<Record<string, unknown>>;
  variant?: RenderVariant;
}) {
  const points = chartPointsFromData(data, label, value).filter((point) => point.value > 0);
  const total = points.reduce((sum, point) => sum + point.value, 0);
  if (!points.length || total <= 0) {
    return chartFrame(title, emptyChartState());
  }
  const palette = readChatThemeColors();
  const expanded = variant !== "inline";

  const size = expanded ? 300 : 220;
  const radius = expanded ? 112 : 82;
  const cx = size / 2;
  const cy = size / 2;
  const innerRadius = expanded ? 58 : 44;
  let currentAngle = -Math.PI / 2;

  return chartFrame(
    title,
    <div className="flex flex-col gap-3 md:flex-row md:items-center">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className={cn("mx-auto shrink-0", expanded ? "h-72 w-72" : "h-52 w-52")}
      >
        {points.map((point, index) => {
          const sweep = (point.value / total) * Math.PI * 2;
          const start = currentAngle;
          const end = currentAngle + sweep;
          currentAngle = end;
          return (
            <path
              key={`slice-${point.label}-${index}`}
              d={pieSlicePath(cx, cy, radius, start, end)}
              fill={palette.chartColors[index % palette.chartColors.length]}
              stroke={palette.background}
              strokeWidth={1}
            />
          );
        })}
        <circle cx={cx} cy={cy} r={innerRadius} fill={palette.background} />
        <text
          x={cx}
          y={cy - 2}
          textAnchor="middle"
          fill={palette.foreground}
          fontSize={expanded ? 18 : 14}
          fontWeight={600}
        >
          {formatCompactValue(total)}
        </text>
        <text
          x={cx}
          y={cy + (expanded ? 18 : 14)}
          textAnchor="middle"
          fill={palette.mutedForeground}
          fontSize={expanded ? 12 : 10}
        >
          total
        </text>
      </svg>
      <ul className={cn("space-y-1.5", expanded ? "text-sm" : "text-xs")}>
        {points.map((point, index) => {
          const share = (point.value / total) * 100;
          return (
            <li key={`legend-${point.label}-${index}`} className="flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ backgroundColor: palette.chartColors[index % palette.chartColors.length] } as CSSProperties}
              />
              <span className="font-medium">{point.label}</span>
              <span className="text-muted-foreground">
                {point.value.toFixed(2)} ({share.toFixed(1)}%)
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

type SankeyNode = {
  id: string;
  label?: string;
};

type SankeyLink = {
  source: string;
  target: string;
  value: number;
};

type SankeyNodeLayout = SankeyNode & {
  x: number;
  y: number;
  width: number;
  height: number;
  value: number;
  scale: number;
};

function SankeyChart({
  title,
  nodes,
  links,
  variant = "inline"
}: {
  title?: string;
  nodes: SankeyNode[];
  links: SankeyLink[];
  variant?: RenderVariant;
}) {
  const palette = readChatThemeColors();
  const expanded = variant !== "inline";
  const exportMode = variant === "export";
  const paddingX = expanded ? 56 : 36;
  const paddingY = expanded ? 24 : 16;
  const nodeWidth = expanded ? 22 : 18;
  const verticalGap = expanded ? 18 : 14;

  const incomingByNode = new Map<string, number>();
  const outgoingByNode = new Map<string, number>();

  for (const node of nodes) {
    incomingByNode.set(node.id, 0);
    outgoingByNode.set(node.id, 0);
  }
  for (const link of links) {
    incomingByNode.set(link.target, (incomingByNode.get(link.target) ?? 0) + link.value);
    outgoingByNode.set(link.source, (outgoingByNode.get(link.source) ?? 0) + link.value);
  }

  const layerByNode = new Map<string, number>();
  for (const node of nodes) {
    if ((incomingByNode.get(node.id) ?? 0) === 0) {
      layerByNode.set(node.id, 0);
    } else {
      layerByNode.set(node.id, 0);
    }
  }

  for (let step = 0; step < nodes.length; step += 1) {
    let changed = false;
    for (const link of links) {
      const sourceLayer = layerByNode.get(link.source) ?? 0;
      const targetLayer = layerByNode.get(link.target) ?? 0;
      if (targetLayer < sourceLayer + 1) {
        layerByNode.set(link.target, sourceLayer + 1);
        changed = true;
      }
    }
    if (!changed) {
      break;
    }
  }

  const maxLayer = Math.max(...Array.from(layerByNode.values()), 0);
  const columns: SankeyNode[][] = Array.from({ length: maxLayer + 1 }, () => []);
  for (const node of nodes) {
    columns[layerByNode.get(node.id) ?? 0].push(node);
  }

  const width = Math.max(expanded ? 1320 : 920, (maxLayer + 1) * (expanded ? 290 : 230));
  const maxColumnSize = Math.max(...columns.map((column) => column.length), 1);
  const height = Math.max(expanded ? 620 : 380, maxColumnSize * (expanded ? 64 : 52) + paddingY * 2);
  const availableHeight = height - paddingY * 2;
  const nodeLayouts = new Map<string, SankeyNodeLayout>();

  for (let layerIndex = 0; layerIndex < columns.length; layerIndex += 1) {
    const layerNodes = columns[layerIndex];
    const totalLayerValue = layerNodes.reduce((sum, node) => {
      const incoming = incomingByNode.get(node.id) ?? 0;
      const outgoing = outgoingByNode.get(node.id) ?? 0;
      return sum + Math.max(incoming, outgoing, 1);
    }, 0);
    const totalGap = Math.max(0, layerNodes.length - 1) * verticalGap;
    const scale = (availableHeight - totalGap) / Math.max(totalLayerValue, 1);
    const x = paddingX + (maxLayer === 0 ? 0 : (layerIndex / maxLayer) * (width - paddingX * 2 - nodeWidth));

    let yCursor = paddingY;
    for (const node of layerNodes) {
      const incoming = incomingByNode.get(node.id) ?? 0;
      const outgoing = outgoingByNode.get(node.id) ?? 0;
      const value = Math.max(incoming, outgoing, 1);
      const nodeHeight = Math.max(8, value * scale);
      nodeLayouts.set(node.id, {
        id: node.id,
        label: node.label ?? node.id,
        x,
        y: yCursor,
        width: nodeWidth,
        height: nodeHeight,
        value,
        scale
      });
      yCursor += nodeHeight + verticalGap;
    }
  }

  if (nodeLayouts.size === 0) {
    return chartFrame(title, emptyChartState("No sankey layout data available."));
  }

  const sourceOffset = new Map<string, number>();
  const targetOffset = new Map<string, number>();

  return chartFrame(
    title,
    <div
      className={cn(exportMode ? "inline-block pb-2" : "overflow-x-auto pb-2")}
      style={exportMode ? { width: `${width}px` } : undefined}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className={cn("block", expanded ? "h-[38rem]" : "h-80")}
        style={exportMode ? { width: `${width}px` } : { width: `${width}px`, minWidth: "100%" }}
      >
        {links.map((link, index) => {
          const source = nodeLayouts.get(link.source);
          const target = nodeLayouts.get(link.target);
          if (!source || !target) {
            return null;
          }
          const fromScale = source.height / Math.max(source.value, 1);
          const toScale = target.height / Math.max(target.value, 1);
          const thickness = Math.max(2, link.value * Math.min(fromScale, toScale));

          const sourceProgress = sourceOffset.get(source.id) ?? 0;
          const targetProgress = targetOffset.get(target.id) ?? 0;
          const sourceY = source.y + sourceProgress + thickness / 2;
          const targetY = target.y + targetProgress + thickness / 2;
          sourceOffset.set(source.id, sourceProgress + thickness);
          targetOffset.set(target.id, targetProgress + thickness);

          const startX = source.x + source.width;
          const endX = target.x;
          const curve = Math.max(18, Math.abs(endX - startX) * 0.35);
          const path = `M ${startX} ${sourceY} C ${startX + curve} ${sourceY}, ${endX - curve} ${targetY}, ${endX} ${targetY}`;

          return (
            <path
              key={`link-${link.source}-${link.target}-${index}`}
              d={path}
              fill="none"
              stroke={palette.chartColors[index % palette.chartColors.length]}
              strokeOpacity={expanded ? 0.55 : 0.4}
              strokeWidth={thickness}
              strokeLinecap="butt"
            />
          );
        })}

        {Array.from(nodeLayouts.values()).map((node, index) => (
          <g key={`node-${node.id}`}>
            <rect
              x={node.x}
              y={node.y}
              width={node.width}
              height={node.height}
              rx={4}
              fill={palette.chartColors[index % palette.chartColors.length]}
              fillOpacity={0.9}
            />
            <text
              x={node.x + node.width + 8}
              y={node.y + node.height / 2}
              dominantBaseline="middle"
              fill={palette.foreground}
              fontSize={expanded ? 14 : 11}
              fontWeight={500}
            >
              {truncateAxisLabel(node.label ?? node.id, expanded ? 40 : 28)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

const chartDataPointSchema = z.record(z.string(), z.union([z.string(), z.number()]));

const chatUiCatalog = defineCatalog(schema, {
  components: {
    StackLayout: {
      props: z.object({}),
      slots: ["default"],
      description: "Vertical stack container for chat tool UI cards."
    },
    GridLayout: {
      props: z.object({}),
      slots: ["default"],
      description: "Two-column responsive grid container for chat tool UI cards."
    },
    MetricCard: {
      props: z.object({
        title: z.string(),
        value: z.union([z.string(), z.number()]),
        subtitle: z.string().optional(),
        trend: z
          .object({
            value: z.union([z.string(), z.number()]),
            direction: z.enum(["up", "down", "neutral"])
          })
          .optional()
      }),
      description: "Compact metric card with optional trend."
    },
    Table: {
      props: z.object({
        title: z.string().optional(),
        columns: z.array(z.string()),
        rows: z.array(z.array(z.union([z.string(), z.number(), z.null()])))
      }),
      description: "Simple data table."
    },
    LineChart: {
      props: z.object({
        title: z.string().optional(),
        x: z.string(),
        y: z.string(),
        data: z.array(chartDataPointSchema)
      }),
      description: "Line chart from tabular data."
    },
    BarChart: {
      props: z.object({
        title: z.string().optional(),
        x: z.string(),
        y: z.string(),
        data: z.array(chartDataPointSchema)
      }),
      description: "Bar chart from tabular data."
    },
    PieChart: {
      props: z.object({
        title: z.string().optional(),
        label: z.string(),
        value: z.string(),
        data: z.array(chartDataPointSchema)
      }),
      description: "Pie chart from tabular data."
    },
    SankeyChart: {
      props: z.object({
        title: z.string().optional(),
        nodes: z.array(
          z.object({
            id: z.string(),
            label: z.string().optional()
          })
        ),
        links: z.array(
          z.object({
            source: z.string(),
            target: z.string(),
            value: z.number()
          })
        )
      }),
      description: "Sankey flow diagram."
    },
    Callout: {
      props: z.object({
        tone: z.enum(["info", "success", "warning", "error"]),
        title: z.string(),
        body: z.string()
      }),
      description: "Semantic callout box."
    }
  },
  actions: {}
});

function createChatUiRegistry(variant: RenderVariant) {
  return defineRegistry(chatUiCatalog, {
    components: {
      StackLayout: ({ children }: { children?: ReactNode }) => <section className="space-y-3">{children}</section>,
      GridLayout: ({ children }: { children?: ReactNode }) => (
        <section className="grid gap-3 md:grid-cols-2">{children}</section>
      ),
      MetricCard: ({ props }: { props: Parameters<typeof MetricCard>[0] }) => <MetricCard {...props} />,
      Table: ({ props }: { props: Parameters<typeof TableElement>[0] }) => <TableElement {...props} />,
      LineChart: ({ props }: { props: Parameters<typeof LineChart>[0] }) => (
        <LineChart {...props} variant={variant} />
      ),
      BarChart: ({ props }: { props: Parameters<typeof BarChart>[0] }) => (
        <BarChart {...props} variant={variant} />
      ),
      PieChart: ({ props }: { props: Parameters<typeof PieChart>[0] }) => (
        <PieChart {...props} variant={variant} />
      ),
      SankeyChart: ({ props }: { props: Parameters<typeof SankeyChart>[0] }) => (
        <SankeyChart {...props} variant={variant} />
      ),
      Callout: ({ props }: { props: Parameters<typeof Callout>[0] }) => <Callout {...props} />
    }
  }).registry;
}

function toJsonRenderSpec(spec: ChatUiSpec): Spec {
  const elements: Spec["elements"] = {};
  const childKeys: string[] = [];
  for (let index = 0; index < spec.elements.length; index += 1) {
    const element = spec.elements[index];
    const key = `el-${index}`;
    childKeys.push(key);
    elements[key] = {
      type: element.type,
      props: element.props
    };
  }

  elements.root = {
    type: spec.layout === "grid" ? "GridLayout" : "StackLayout",
    props: {},
    children: childKeys
  };

  return {
    root: "root",
    elements
  };
}

export function ChatUiRenderer({
  spec,
  className,
  variant = "inline"
}: {
  spec: ChatUiSpec;
  className?: string;
  variant?: RenderVariant;
}) {
  const jsonRenderSpec = toJsonRenderSpec(spec);
  const registry = createChatUiRegistry(variant);

  return (
    <section className={cn("space-y-3", className)}>
      <JSONUIProvider registry={registry}>
        <Renderer spec={jsonRenderSpec} registry={registry} />
      </JSONUIProvider>
    </section>
  );
}
