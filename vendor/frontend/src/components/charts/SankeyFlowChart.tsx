import { forwardRef, useId, useMemo, useState } from "react";
import {
  sankey,
  sankeyJustify,
  sankeyLinkHorizontal,
  type SankeyGraph,
} from "d3-sankey";

import { readChatThemeColors } from "@/chat/ui/themeColors";
import { cn } from "@/lib/utils";

export type SankeyFlowNode = {
  id: string;
  label?: string;
  color?: string;
  kind?: string;
  amountCents?: number;
  basisAmountCents?: number;
};

export type SankeyFlowLink = {
  source: string;
  target: string;
  value: number;
  color?: string;
  kind?: string;
};

export function buildSankeyFlowLinkKey(source: string, target: string): string {
  return `${source}->${target}`;
}

type SankeyVariant = "compact" | "comfortable" | "export";

type InternalNode = SankeyFlowNode & {
  depth?: number;
  height?: number;
  layer?: number;
  sourceLinks?: InternalLink[];
  targetLinks?: InternalLink[];
  value?: number;
  x0?: number;
  x1?: number;
  y0?: number;
  y1?: number;
};

type InternalLink = Omit<SankeyFlowLink, "source" | "target"> & {
  source: InternalNode;
  target: InternalNode;
  width?: number;
  y0?: number;
  y1?: number;
};

function nodeFallbackColor(node: SankeyFlowNode, palette: ReturnType<typeof readChatThemeColors>): string {
  if (node.kind === "inflow") {
    return palette.chartColors[1];
  }
  if (node.kind === "merchant") {
    return palette.chartColors[2];
  }
  return palette.chartColors[0];
}

function truncateLabel(label: string, maxLength: number): string {
  if (label.length <= maxLength) {
    return label;
  }
  return `${label.slice(0, Math.max(1, maxLength - 3))}...`;
}

function formatCompactValue(value: number): string {
  return new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
}

export const SankeyFlowChart = forwardRef<SVGSVGElement, {
  className?: string;
  emptyText?: string;
  formatValue?: (value: number) => string;
  links: SankeyFlowLink[];
  nodes: SankeyFlowNode[];
  onLinkSelect?: (linkKey: string) => void;
  onNodeSelect?: (nodeId: string) => void;
  onNodeRenameRequest?: (nodeId: string) => void;
  selectedLinkKey?: string | null;
  selectedNodeId?: string | null;
  variant?: SankeyVariant;
}>(
  function SankeyFlowChart(
    {
      className,
      emptyText = "No sankey layout data available.",
      formatValue = formatCompactValue,
      links,
      nodes,
      onLinkSelect,
      onNodeSelect,
      onNodeRenameRequest,
      selectedLinkKey = null,
      selectedNodeId = null,
      variant = "comfortable",
    },
    ref,
  ) {
    const palette = readChatThemeColors();
    const gradientNamespace = useId().replace(/:/g, "-");
    const clipPathId = gradientNamespace + "-plot-clip";
    const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
    const [hoveredLinkKey, setHoveredLinkKey] = useState<string | null>(null);
    const exportMode = variant === "export";
    const compact = variant === "compact";

    const layout = useMemo(() => {
      const positiveLinks = links
        .filter((link) => Number.isFinite(link.value) && link.value > 0)
        .map((link) => ({ ...link }));
      if (nodes.length === 0 || positiveLinks.length === 0) {
        return null;
      }

      const safeNodes = nodes.map((node) => ({ ...node }));
      const width = exportMode ? 1520 : compact ? 960 : 1320;
      const height = Math.max(compact ? 340 : 520, Math.min(1120, safeNodes.length * (compact ? 34 : 46) + 210));
      const graph = sankey<InternalNode, InternalLink>()
        .nodeId((node) => node.id)
        .nodeAlign(sankeyJustify)
        .nodeWidth(compact ? 16 : 20)
        .nodePadding(compact ? 16 : 22)
        .nodeSort((left, right) => (right.amountCents ?? 0) - (left.amountCents ?? 0))
        .linkSort((left, right) => right.value - left.value)
        .extent([
          [compact ? 26 : 40, compact ? 18 : 30],
          [width - (compact ? 34 : 56), height - (compact ? 18 : 30)],
        ])({
          nodes: safeNodes,
          links: positiveLinks as unknown as InternalLink[],
        } as unknown as SankeyGraph<InternalNode, InternalLink>);

      return {
        width,
        height,
        nodes: graph.nodes,
        links: graph.links,
      };
    }, [compact, exportMode, links, nodes]);

    const focusLinkKey = hoveredLinkKey ?? selectedLinkKey;
    const focusNodeId = hoveredNodeId ?? selectedNodeId;
    const focusedLink = focusLinkKey
      ? layout?.links.find(
          (link) => buildSankeyFlowLinkKey(link.source.id, link.target.id) === focusLinkKey,
        ) ?? null
      : null;
    const focusedNode = focusNodeId
      ? layout?.nodes.find((node) => node.id === focusNodeId) ?? null
      : null;
    const connectedNodeIds = new Set<string>();
    if (focusedLink) {
      connectedNodeIds.add(focusedLink.source.id);
      connectedNodeIds.add(focusedLink.target.id);
    }
    if (focusedNode) {
      connectedNodeIds.add(focusedNode.id);
      for (const link of focusedNode.sourceLinks ?? []) {
        connectedNodeIds.add(link.target.id);
      }
      for (const link of focusedNode.targetLinks ?? []) {
        connectedNodeIds.add(link.source.id);
      }
    }

    if (!layout) {
      return <p className={cn("text-xs text-muted-foreground", className)}>{emptyText}</p>;
    }

    const infoLine = focusedLink
      ? {
          label: `${focusedLink.source.label ?? focusedLink.source.id} -> ${focusedLink.target.label ?? focusedLink.target.id}`,
          value: formatValue(focusedLink.value),
          detail: focusedLink.kind === "period_proportional_attribution" ? "Attributed period flow" : "Observed outflow",
        }
      : focusedNode
        ? {
            label: focusedNode.label ?? focusedNode.id,
            value: formatValue(focusedNode.value ?? focusedNode.amountCents ?? 0),
            detail:
              focusedNode.kind === "inflow" && focusedNode.basisAmountCents !== undefined
                ? `Basis ${formatValue(focusedNode.basisAmountCents)}`
                : focusedNode.kind === "merchant"
                  ? "Merchant sink"
                  : focusedNode.kind === "outflow_category"
                    ? "Outflow bucket"
                    : "Flow node",
          }
        : null;

    return (
      <div className={cn("space-y-3", className)}>
        <div className="flex min-h-10 flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/60 bg-background/55 px-3 py-2.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            <span>Flow diagram</span>
            <span className="rounded-full border border-border/60 bg-background/75 px-2 py-0.5 normal-case tracking-normal text-foreground/80">
              {layout.nodes.length} nodes
            </span>
            <span className="rounded-full border border-border/60 bg-background/75 px-2 py-0.5 normal-case tracking-normal text-foreground/80">
              {layout.links.length} links
            </span>
          </div>
          <div className="min-h-6 text-right text-xs text-muted-foreground">
            {infoLine ? (
              <>
                <p className="font-medium text-foreground/90">{infoLine.label}</p>
                <p>{infoLine.value} - {infoLine.detail}</p>
              </>
            ) : (
              <p>{onLinkSelect || onNodeSelect ? "Hover or click a band or node for detail." : "Hover a band or node for detail."}</p>
            )}
          </div>
        </div>

        <div
          className={cn(
            exportMode ? "inline-block" : "overflow-x-auto",
            "rounded-[28px] border border-border/50 bg-[radial-gradient(circle_at_top_left,rgba(79,140,255,0.16),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(33,200,122,0.12),transparent_32%),linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0.01))] p-3 shadow-[0_20px_70px_rgba(15,23,42,0.16)]",
          )}
          style={exportMode ? { width: `${layout.width}px` } : undefined}
        >
          <svg
            ref={ref}
            viewBox={`0 0 ${layout.width} ${layout.height}`}
            className={cn(
              "block animate-in fade-in-0 slide-in-from-bottom-3 duration-500",
            )}
            style={
              exportMode
                ? { width: `${layout.width}px`, height: `${layout.height}px` }
                : compact
                  ? { width: `${layout.width}px`, minWidth: "100%", height: "22rem" }
                  : { width: `${layout.width}px`, minWidth: "100%", height: `${layout.height}px` }
            }
          >
            <defs>
              <clipPath id={clipPathId}>
                <rect
                  x={6}
                  y={6}
                  width={layout.width - 12}
                  height={layout.height - 12}
                  rx={24}
                />
              </clipPath>
              {layout.links.map((link, index) => {
                const gradientId = `${gradientNamespace}-link-${index}`;
                const sourceColor = link.source.color ?? nodeFallbackColor(link.source, palette);
                const targetColor = link.target.color ?? nodeFallbackColor(link.target, palette);
                return (
                  <linearGradient
                    id={gradientId}
                    key={gradientId}
                    gradientUnits="userSpaceOnUse"
                    x1={link.source.x1 ?? 0}
                    x2={link.target.x0 ?? layout.width}
                    y1={link.y0 ?? 0}
                    y2={link.y1 ?? 0}
                  >
                    <stop offset="0%" stopColor={sourceColor} stopOpacity="0.72" />
                    <stop offset="100%" stopColor={targetColor} stopOpacity="0.42" />
                  </linearGradient>
                );
              })}
            </defs>

            <rect
              x={0}
              y={0}
              width={layout.width}
              height={layout.height}
              rx={26}
              fill={palette.background}
              fillOpacity={0.22}
            />

            <g clipPath={`url(#${clipPathId})`}>
              {layout.links.map((link, index) => {
                const key = buildSankeyFlowLinkKey(link.source.id, link.target.id);
                const gradientId = `${gradientNamespace}-link-${index}`;
                const active = focusLinkKey === null && focusNodeId === null
                  ? true
                  : focusLinkKey === key || connectedNodeIds.has(link.source.id) || connectedNodeIds.has(link.target.id);
                return (
                  <path
                    key={key}
                    data-link-key={key}
                    d={sankeyLinkHorizontal()(link) ?? undefined}
                    fill="none"
                    stroke={link.color ?? `url(#${gradientId})`}
                    strokeWidth={Math.max(link.width ?? 0, compact ? 2 : 3)}
                    strokeOpacity={active ? 0.88 : 0.14}
                    strokeLinecap="butt"
                    style={{ transition: "stroke-opacity 180ms ease", cursor: onLinkSelect ? "pointer" : "default" }}
                    onMouseEnter={() => {
                      setHoveredLinkKey(key);
                      setHoveredNodeId(null);
                    }}
                    onMouseLeave={() => setHoveredLinkKey(null)}
                    onClick={() => onLinkSelect?.(key)}
                  />
                );
              })}
            </g>

            {layout.nodes.map((node) => {
              const width = Math.max(0, (node.x1 ?? 0) - (node.x0 ?? 0));
              const height = Math.max(0, (node.y1 ?? 0) - (node.y0 ?? 0));
              const color = node.color ?? nodeFallbackColor(node, palette);
              const active = focusLinkKey === null && focusNodeId === null
                ? true
                : connectedNodeIds.has(node.id);
              const x = node.x0 ?? 0;
              const y = node.y0 ?? 0;
              const label = node.label ?? node.id;
              const textAnchor = x < layout.width * 0.55 ? "start" : "end";
              const textX = textAnchor === "start" ? (node.x1 ?? 0) + 12 : x - 12;
              const crampedNode = height < (compact ? 22 : 34);
              const labelY = crampedNode ? y + height / 2 + 4 : y + height / 2 - (compact ? 6 : 8);
              const valueY = y + height / 2 + (compact ? 8 : 14);
              const labelFontSize = crampedNode ? (compact ? 10 : 11) : (compact ? 11 : 13);
              const valueFontSize = crampedNode ? 0 : (compact ? 10 : 11);
              const labelMaxLength = crampedNode ? (compact ? 16 : 18) : (compact ? 22 : 30);
              const valueLine = formatValue(node.value ?? node.amountCents ?? 0);
              return (
                <g
                  key={node.id}
                  data-node-id={node.id}
                  style={{ transition: "opacity 180ms ease", cursor: onNodeSelect ? "pointer" : "default" }}
                  onMouseEnter={() => {
                    setHoveredNodeId(node.id);
                    setHoveredLinkKey(null);
                  }}
                  onMouseLeave={() => setHoveredNodeId(null)}
                  onClick={() => onNodeSelect?.(node.id)}
                  onDoubleClick={(event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    onNodeRenameRequest?.(node.id);
                  }}
                >
                  <rect
                    x={x}
                    y={y}
                    width={width}
                    height={height}
                    rx={6}
                    fill={color}
                    fillOpacity={active ? 0.92 : 0.26}
                    stroke={palette.background}
                    strokeOpacity={0.62}
                  />
                  <text
                    x={textX}
                    y={labelY}
                    textAnchor={textAnchor}
                    fill={palette.foreground}
                    fontSize={labelFontSize}
                    fontWeight={650}
                    style={{ pointerEvents: "none" }}
                  >
                    {truncateLabel(label, labelMaxLength)}
                  </text>
                  {valueFontSize > 0 ? (
                    <text
                      x={textX}
                      y={valueY}
                      textAnchor={textAnchor}
                      fill={palette.mutedForeground}
                      fontSize={valueFontSize}
                      fontWeight={500}
                      style={{ pointerEvents: "none" }}
                    >
                      {valueLine}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>
        </div>
      </div>
    );
  },
);
