import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CategoryPresentation } from "@/components/shared/CategoryPresentation";

describe("CategoryPresentation", () => {
  it("renders canonical grocery categories as split English badges", () => {
    render(<CategoryPresentation category="groceries:beverages" locale="en" />);

    expect(screen.getByText("Groceries")).toBeInTheDocument();
    expect(screen.getByText("Beverages")).toBeInTheDocument();
    expect(screen.queryByText("groceries:beverages")).not.toBeInTheDocument();
  });

  it("renders canonical grocery categories as split German badges", () => {
    render(<CategoryPresentation category="groceries:beverages" locale="de" />);

    expect(screen.getByText("Lebensmittel")).toBeInTheDocument();
    expect(screen.getByText("Getränke")).toBeInTheDocument();
    expect(screen.queryByText("groceries:beverages")).not.toBeInTheDocument();
  });
});
