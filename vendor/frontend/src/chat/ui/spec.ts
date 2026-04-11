import { z } from "zod";

const MAX_ELEMENTS = 12;
const MAX_LABEL_LENGTH = 120;
const MAX_TEXT_LENGTH = 500;
const MAX_TABLE_COLUMNS = 12;
const MAX_TABLE_ROWS = 120;
const MAX_DATA_POINTS = 240;
const MAX_LINE_SERIES = 12;
const MAX_SANKEY_NODES = 64;
const MAX_SANKEY_LINKS = 200;

const numberValueSchema = z
  .number()
  .finite();

const shortTextSchema = z.string().trim().min(1).max(MAX_LABEL_LENGTH);
const longTextSchema = z.string().trim().min(1).max(MAX_TEXT_LENGTH);

const metricCardPropsSchema = z.object({
  title: shortTextSchema,
  value: z.union([numberValueSchema, longTextSchema]),
  subtitle: z.string().trim().max(MAX_TEXT_LENGTH).optional(),
  trend: z
    .object({
      value: z.union([numberValueSchema, shortTextSchema]),
      direction: z.enum(["up", "down", "neutral"]).default("neutral")
    })
    .optional()
});

const calloutPropsSchema = z.object({
  tone: z.enum(["info", "success", "warning", "error"]).default("info"),
  title: shortTextSchema,
  body: longTextSchema
});

const tableValueSchema = z.union([numberValueSchema, z.string().max(MAX_TEXT_LENGTH), z.null()]);
const tablePropsSchema = z
  .object({
    title: shortTextSchema.optional(),
    columns: z.array(shortTextSchema).min(1).max(MAX_TABLE_COLUMNS),
    rows: z.array(z.array(tableValueSchema).max(MAX_TABLE_COLUMNS)).max(MAX_TABLE_ROWS)
  })
  .superRefine((value, context) => {
    const expectedColumns = value.columns.length;
    value.rows.forEach((row, rowIndex) => {
      if (row.length !== expectedColumns) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["rows", rowIndex],
          message: `Row ${rowIndex + 1} has ${row.length} values; expected ${expectedColumns}`
        });
      }
    });
  });

const dataPointSchema = z.record(
  z.string(),
  z.union([z.string().max(MAX_TEXT_LENGTH), numberValueSchema])
);

const lineChartSeriesSchema = z.object({
  key: shortTextSchema,
  label: shortTextSchema.optional(),
  color: z.string().trim().min(1).max(32).optional()
});

const singleLineChartPropsSchema = z.object({
  title: shortTextSchema.optional(),
  x: shortTextSchema,
  y: shortTextSchema,
  data: z.array(dataPointSchema).min(1).max(MAX_DATA_POINTS)
});

const multiLineChartKeysPropsSchema = z.object({
  title: shortTextSchema.optional(),
  x: shortTextSchema,
  y: z.array(shortTextSchema).min(1).max(MAX_LINE_SERIES),
  data: z.array(dataPointSchema).min(1).max(MAX_DATA_POINTS)
});

const multiLineChartSeriesPropsSchema = z
  .object({
    title: shortTextSchema.optional(),
    x: shortTextSchema,
    series: z.array(lineChartSeriesSchema).min(1).max(MAX_LINE_SERIES),
    data: z.array(dataPointSchema).min(1).max(MAX_DATA_POINTS)
  })
  .superRefine((value, context) => {
    const keys = new Set<string>();
    value.series.forEach((series, index) => {
      if (keys.has(series.key)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["series", index, "key"],
          message: `Duplicate line-series key '${series.key}'`
        });
      }
      keys.add(series.key);
    });
  });

const lineChartPropsSchema = z.union([
  singleLineChartPropsSchema,
  multiLineChartKeysPropsSchema,
  multiLineChartSeriesPropsSchema
]);

const barChartPropsSchema = z.object({
  title: shortTextSchema.optional(),
  x: shortTextSchema,
  y: shortTextSchema,
  data: z.array(dataPointSchema).min(1).max(MAX_DATA_POINTS)
});

const pieChartPropsSchema = z.object({
  title: shortTextSchema.optional(),
  label: shortTextSchema,
  value: shortTextSchema,
  data: z.array(dataPointSchema).min(1).max(MAX_DATA_POINTS)
});

const sankeyNodeSchema = z.object({
  id: shortTextSchema,
  label: shortTextSchema.optional()
});

const sankeyLinkSchema = z.object({
  source: shortTextSchema,
  target: shortTextSchema,
  value: numberValueSchema.positive()
});

const sankeyChartPropsSchema = z
  .object({
    title: shortTextSchema.optional(),
    nodes: z.array(sankeyNodeSchema).min(2).max(MAX_SANKEY_NODES),
    links: z.array(sankeyLinkSchema).min(1).max(MAX_SANKEY_LINKS)
  })
  .superRefine((value, context) => {
    const nodeIds = new Set(value.nodes.map((node) => node.id));
    if (nodeIds.size !== value.nodes.length) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["nodes"],
        message: "Sankey node ids must be unique"
      });
    }
    value.links.forEach((link, index) => {
      if (!nodeIds.has(link.source)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["links", index, "source"],
          message: `Unknown source node '${link.source}'`
        });
      }
      if (!nodeIds.has(link.target)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["links", index, "target"],
          message: `Unknown target node '${link.target}'`
        });
      }
    });
  });

const metricCardElementSchema = z.object({
  type: z.literal("MetricCard"),
  props: metricCardPropsSchema
});

const tableElementSchema = z.object({
  type: z.literal("Table"),
  props: tablePropsSchema
});

const lineChartElementSchema = z.object({
  type: z.literal("LineChart"),
  props: lineChartPropsSchema
});

const barChartElementSchema = z.object({
  type: z.literal("BarChart"),
  props: barChartPropsSchema
});

const pieChartElementSchema = z.object({
  type: z.literal("PieChart"),
  props: pieChartPropsSchema
});

const sankeyChartElementSchema = z.object({
  type: z.literal("SankeyChart"),
  props: sankeyChartPropsSchema
});

const calloutElementSchema = z.object({
  type: z.literal("Callout"),
  props: calloutPropsSchema
});

export const chatUiElementSchema = z.discriminatedUnion("type", [
  metricCardElementSchema,
  tableElementSchema,
  lineChartElementSchema,
  barChartElementSchema,
  pieChartElementSchema,
  sankeyChartElementSchema,
  calloutElementSchema
]);

export const chatUiSpecSchema = z.object({
  version: z.literal("v1"),
  layout: z.enum(["stack", "grid"]).default("stack"),
  elements: z.array(chatUiElementSchema).min(1).max(MAX_ELEMENTS)
});

export type ChatUiElement = z.infer<typeof chatUiElementSchema>;
export type ChatUiSpec = z.infer<typeof chatUiSpecSchema>;

export const CHAT_UI_COMPONENT_NAMES = [
  "MetricCard",
  "Table",
  "LineChart",
  "BarChart",
  "PieChart",
  "SankeyChart",
  "Callout"
] as const;

export function parseChatUiSpec(input: unknown): ChatUiSpec {
  return chatUiSpecSchema.parse(input);
}

export function tryParseChatUiSpec(input: unknown): ChatUiSpec | null {
  const parsed = chatUiSpecSchema.safeParse(input);
  if (!parsed.success) {
    return null;
  }
  return parsed.data;
}
