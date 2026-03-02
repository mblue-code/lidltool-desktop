import { CSSProperties, ReactNode } from "react";
import { defineCatalog, type Spec } from "@json-render/core";
import { JSONUIProvider, defineRegistry, Renderer } from "@json-render/react";
import { schema } from "@json-render/react/schema";
import { z } from "zod";

import { ChatUiSpec } from "@/chat/ui/spec";
import { cn } from "@/lib/utils";

const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)"
];

type ChartPoint = {
  label: string;
  value: number;
};

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
  for (const row of data) {
    const yValue = toFiniteNumber(row[yKey]);
    if (yValue === null) {
      continue;
    }
    const rawLabel = row[xKey];
    points.push({
      label: String(rawLabel ?? ""),
      value: yValue
    });
  }
  return points;
}

function chartFrame(
  title: string | undefined,
  body: JSX.Element,
  className?: string
): JSX.Element {
  return (
    <section className={cn("rounded-lg border bg-background p-3", className)}>
      {title ? <h4 className="mb-3 text-sm font-medium">{title}</h4> : null}
      {body}
    </section>
  );
}

function emptyChartState(text = "No plottable numeric data available."): JSX.Element {
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
}): JSX.Element {
  const trendClass =
    trend?.direction === "up"
      ? "text-emerald-600"
      : trend?.direction === "down"
        ? "text-rose-600"
        : "text-muted-foreground";

  return chartFrame(
    undefined,
    <div className="space-y-1">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</p>
      <p className="text-2xl font-semibold leading-none">{value}</p>
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
}): JSX.Element {
  const toneClassByValue: Record<typeof tone, string> = {
    info: "border-sky-500/40 bg-sky-500/5",
    success: "border-emerald-500/40 bg-emerald-500/5",
    warning: "border-amber-500/40 bg-amber-500/5",
    error: "border-rose-500/40 bg-rose-500/5"
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
}): JSX.Element {
  return chartFrame(
    title,
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} className="border-b px-2 py-1.5 text-left text-xs font-medium text-muted-foreground">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`row-${rowIndex}`}>
              {row.map((value, columnIndex) => (
                <td key={`cell-${rowIndex}-${columnIndex}`} className="border-b px-2 py-1.5 align-top">
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
  data
}: {
  title?: string;
  x: string;
  y: string;
  data: Array<Record<string, unknown>>;
}): JSX.Element {
  const points = chartPointsFromData(data, x, y);
  if (points.length === 0) {
    return chartFrame(title, emptyChartState());
  }

  const width = 640;
  const height = 260;
  const paddingLeft = 46;
  const paddingRight = 18;
  const paddingTop = 16;
  const paddingBottom = 36;
  const innerWidth = width - paddingLeft - paddingRight;
  const innerHeight = height - paddingTop - paddingBottom;
  const minValue = Math.min(...points.map((point) => point.value));
  const maxValue = Math.max(...points.map((point) => point.value));
  const yMin = minValue > 0 ? 0 : minValue;
  const yMax = maxValue === yMin ? yMin + 1 : maxValue;

  const xPosition = (index: number): number => {
    if (points.length === 1) {
      return paddingLeft + innerWidth / 2;
    }
    return paddingLeft + (index / (points.length - 1)) * innerWidth;
  };
  const yPosition = (value: number): number => {
    const ratio = (value - yMin) / (yMax - yMin);
    return paddingTop + (1 - ratio) * innerHeight;
  };

  const polylinePoints = points
    .map((point, index) => `${xPosition(index)},${yPosition(point.value)}`)
    .join(" ");

  const ticks = axisTicks({ min: yMin, max: yMax, count: 4 });

  return chartFrame(
    title,
    <svg viewBox={`0 0 ${width} ${height}`} className="h-56 w-full">
      {ticks.map((tick) => {
        const yTick = yPosition(tick);
        return (
          <g key={`tick-${tick}`}>
            <line x1={paddingLeft} x2={width - paddingRight} y1={yTick} y2={yTick} stroke="var(--border)" strokeDasharray="3 3" />
            <text x={paddingLeft - 8} y={yTick + 4} textAnchor="end" className="fill-muted-foreground text-[10px]">
              {tick.toFixed(0)}
            </text>
          </g>
        );
      })}
      <polyline points={polylinePoints} fill="none" stroke="var(--chart-1)" strokeWidth={2.5} />
      {points.map((point, index) => (
        <circle key={`dot-${index}`} cx={xPosition(index)} cy={yPosition(point.value)} r={2.8} fill="var(--chart-1)" />
      ))}
      {points.map((point, index) => (
        <text
          key={`x-${index}`}
          x={xPosition(index)}
          y={height - 14}
          textAnchor="middle"
          className="fill-muted-foreground text-[10px]"
        >
          {point.label}
        </text>
      ))}
    </svg>,
    "overflow-x-auto"
  );
}

function BarChart({
  title,
  x,
  y,
  data
}: {
  title?: string;
  x: string;
  y: string;
  data: Array<Record<string, unknown>>;
}): JSX.Element {
  const points = chartPointsFromData(data, x, y);
  if (points.length === 0) {
    return chartFrame(title, emptyChartState());
  }

  const width = 640;
  const height = 260;
  const paddingLeft = 46;
  const paddingRight = 16;
  const paddingTop = 16;
  const paddingBottom = 36;
  const innerWidth = width - paddingLeft - paddingRight;
  const innerHeight = height - paddingTop - paddingBottom;
  const maxValue = Math.max(...points.map((point) => point.value), 1);
  const minValue = Math.min(...points.map((point) => point.value), 0);
  const yMin = minValue < 0 ? minValue : 0;
  const yMax = maxValue;

  const band = innerWidth / points.length;
  const barWidth = Math.max(8, band * 0.7);

  const yPosition = (value: number): number => {
    const ratio = (value - yMin) / (yMax - yMin || 1);
    return paddingTop + (1 - ratio) * innerHeight;
  };

  const zeroY = yPosition(0);

  return chartFrame(
    title,
    <svg viewBox={`0 0 ${width} ${height}`} className="h-56 w-full">
      <line x1={paddingLeft} x2={width - paddingRight} y1={zeroY} y2={zeroY} stroke="var(--border)" />
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
              rx={3}
              fill={CHART_COLORS[index % CHART_COLORS.length]}
            />
            <text x={xPos + barWidth / 2} y={height - 14} textAnchor="middle" className="fill-muted-foreground text-[10px]">
              {point.label}
            </text>
          </g>
        );
      })}
    </svg>,
    "overflow-x-auto"
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
  data
}: {
  title?: string;
  label: string;
  value: string;
  data: Array<Record<string, unknown>>;
}): JSX.Element {
  const points = chartPointsFromData(data, label, value).filter((point) => point.value > 0);
  const total = points.reduce((sum, point) => sum + point.value, 0);
  if (!points.length || total <= 0) {
    return chartFrame(title, emptyChartState());
  }

  const size = 220;
  const radius = 82;
  const cx = size / 2;
  const cy = size / 2;
  let currentAngle = -Math.PI / 2;

  return chartFrame(
    title,
    <div className="flex flex-col gap-3 md:flex-row md:items-center">
      <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto h-52 w-52 shrink-0">
        {points.map((point, index) => {
          const sweep = (point.value / total) * Math.PI * 2;
          const start = currentAngle;
          const end = currentAngle + sweep;
          currentAngle = end;
          return (
            <path
              key={`slice-${point.label}-${index}`}
              d={pieSlicePath(cx, cy, radius, start, end)}
              fill={CHART_COLORS[index % CHART_COLORS.length]}
              stroke="var(--background)"
              strokeWidth={1}
            />
          );
        })}
      </svg>
      <ul className="space-y-1.5 text-xs">
        {points.map((point, index) => {
          const share = (point.value / total) * 100;
          return (
            <li key={`legend-${point.label}-${index}`} className="flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] } as CSSProperties}
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
  links
}: {
  title?: string;
  nodes: SankeyNode[];
  links: SankeyLink[];
}): JSX.Element {
  const width = 760;
  const height = 320;
  const paddingX = 36;
  const paddingY = 16;
  const nodeWidth = 14;
  const verticalGap = 10;

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
    <svg viewBox={`0 0 ${width} ${height}`} className="h-72 w-full">
      {links.map((link, index) => {
        const source = nodeLayouts.get(link.source);
        const target = nodeLayouts.get(link.target);
        if (!source || !target) {
          return null;
        }
        const fromScale = source.height / Math.max(source.value, 1);
        const toScale = target.height / Math.max(target.value, 1);
        const thickness = Math.max(1.5, link.value * Math.min(fromScale, toScale));

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
            stroke={CHART_COLORS[index % CHART_COLORS.length]}
            strokeOpacity={0.35}
            strokeWidth={thickness}
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
            rx={3}
            fill={CHART_COLORS[index % CHART_COLORS.length]}
            fillOpacity={0.9}
          />
          <text
            x={node.x + node.width + 6}
            y={node.y + Math.max(10, node.height / 2)}
            className="fill-foreground text-[10px]"
          >
            {node.label}
          </text>
        </g>
      ))}
    </svg>,
    "overflow-x-auto"
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

const { registry: chatUiRegistry } = defineRegistry(chatUiCatalog, {
  components: {
    StackLayout: ({ children }: { children?: ReactNode }) => <section className="space-y-3">{children}</section>,
    GridLayout: ({ children }: { children?: ReactNode }) => (
      <section className="grid gap-3 md:grid-cols-2">{children}</section>
    ),
    MetricCard: ({ props }: { props: Parameters<typeof MetricCard>[0] }) => <MetricCard {...props} />,
    Table: ({ props }: { props: Parameters<typeof TableElement>[0] }) => <TableElement {...props} />,
    LineChart: ({ props }: { props: Parameters<typeof LineChart>[0] }) => <LineChart {...props} />,
    BarChart: ({ props }: { props: Parameters<typeof BarChart>[0] }) => <BarChart {...props} />,
    PieChart: ({ props }: { props: Parameters<typeof PieChart>[0] }) => <PieChart {...props} />,
    SankeyChart: ({ props }: { props: Parameters<typeof SankeyChart>[0] }) => <SankeyChart {...props} />,
    Callout: ({ props }: { props: Parameters<typeof Callout>[0] }) => <Callout {...props} />
  }
});

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

export function ChatUiRenderer({ spec, className }: { spec: ChatUiSpec; className?: string }): JSX.Element {
  const jsonRenderSpec = toJsonRenderSpec(spec);

  return (
    <section className={cn(className)}>
      <JSONUIProvider registry={chatUiRegistry}>
        <Renderer spec={jsonRenderSpec} registry={chatUiRegistry} />
      </JSONUIProvider>
    </section>
  );
}
