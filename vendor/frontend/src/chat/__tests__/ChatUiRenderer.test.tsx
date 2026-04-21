import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChatUiRenderer } from "@/chat/ui/ChatUiRenderer";

describe("ChatUiRenderer", () => {
  it("renders multiple chart and card components", () => {
    const { container } = render(
      <ChatUiRenderer
        spec={{
          version: "v1",
          layout: "stack",
          elements: [
            { type: "MetricCard", props: { title: "Net Spend", value: "€320.12", subtitle: "Last 30 days" } },
            {
              type: "LineChart",
              props: {
                title: "Monthly Trend",
                x: "month",
                y: "amount",
                data: [
                  { month: "Jan", amount: 100 },
                  { month: "Feb", amount: 140 }
                ]
              }
            },
            {
              type: "BarChart",
              props: {
                title: "Retailer Spend",
                x: "store",
                y: "amount",
                data: [
                  { store: "Lidl", amount: 220 },
                  { store: "Rewe", amount: 180 }
                ]
              }
            },
            {
              type: "PieChart",
              props: {
                title: "Category Mix",
                label: "category",
                value: "amount",
                data: [
                  { category: "Produce", amount: 120 },
                  { category: "Dairy", amount: 80 }
                ]
              }
            },
            {
              type: "SankeyChart",
              props: {
                title: "Budget Flow",
                nodes: [
                  { id: "income", label: "Income" },
                  { id: "groceries", label: "Groceries" },
                  { id: "savings", label: "Savings" }
                ],
                links: [
                  { source: "income", target: "groceries", value: 300 },
                  { source: "income", target: "savings", value: 150 }
                ]
              }
            },
            {
              type: "Table",
              props: {
                title: "Top Items",
                columns: ["Item", "Amount"],
                rows: [
                  ["Milk", 12.5],
                  ["Bread", 7.8]
                ]
              }
            }
          ]
        }}
      />
    );

    expect(screen.getByText("Net Spend")).toBeInTheDocument();
    expect(screen.getByText("Monthly Trend")).toBeInTheDocument();
    expect(screen.getByText("Retailer Spend")).toBeInTheDocument();
    expect(screen.getByText("Category Mix")).toBeInTheDocument();
    expect(screen.getByText("Budget Flow")).toBeInTheDocument();
    expect(screen.getByText("Top Items")).toBeInTheDocument();
    expect(container.querySelectorAll('path[stroke-linecap="butt"]')).toHaveLength(2);
  });

  it("renders multi-series line charts from a y-array spec", () => {
    const { container } = render(
      <ChatUiRenderer
        spec={{
          version: "v1",
          layout: "stack",
          elements: [
            {
              type: "LineChart",
              props: {
                title: "Egg Price Comparison",
                x: "month",
                y: ["boden_10er", "bio_6er"],
                data: [
                  { month: "2025-01", boden_10er: 2.29, bio_6er: 2.69 },
                  { month: "2025-02", boden_10er: 2.39, bio_6er: 2.79 },
                  { month: "2025-03", boden_10er: 2.49, bio_6er: 2.89 }
                ]
              }
            }
          ]
        }}
      />
    );

    expect(screen.getByText("Egg Price Comparison")).toBeInTheDocument();
    expect(screen.getByText("boden_10er")).toBeInTheDocument();
    expect(screen.getByText("bio_6er")).toBeInTheDocument();
    expect(container.querySelectorAll("polyline")).toHaveLength(2);
  });

  it("keeps dense-axis line charts wide and rotated in export mode", () => {
    const spec = {
      version: "v1" as const,
      layout: "stack" as const,
      elements: [
        {
          type: "LineChart" as const,
          props: {
            title: "Dense Axis Trend",
            x: "month",
            y: "amount",
            data: Array.from({ length: 10 }, (_, index) => ({
              month: `2025-${String(index + 1).padStart(2, "0")}-retail-history`,
              amount: 100 + index * 15
            }))
          }
        }
      ]
    };

    const { container, rerender } = render(<ChatUiRenderer spec={spec} variant="inline" />);

    expect(screen.getByText("Dense Axis Trend")).toBeInTheDocument();
    expect(container.querySelector("svg")).toHaveStyle({
      width: "840px",
      minWidth: "100%"
    });
    expect(container.querySelector('text[transform^="rotate(-35"]')).toBeTruthy();

    rerender(<ChatUiRenderer spec={spec} variant="export" />);

    expect(container.querySelector("svg")).toHaveStyle({
      width: "960px"
    });
    expect(container.querySelector("svg")).not.toHaveStyle({
      minWidth: "100%"
    });
    expect(container.querySelector('text[transform^="rotate(-35"]')).toBeTruthy();
  });
});
