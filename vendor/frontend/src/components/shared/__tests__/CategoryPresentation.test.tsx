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

  it("renders fish as its own canonical grocery subcategory", () => {
    render(<CategoryPresentation category="groceries:fish" locale="de" />);

    expect(screen.getAllByText("Lebensmittel").length).toBeGreaterThan(0);
    expect(screen.getByText("Fisch & Meeresfrüchte")).toBeInTheDocument();
  });

  it("renders desktop-vendored dining labels", () => {
    render(<CategoryPresentation category="dining:restaurant" locale="en" />);

    expect(screen.getByText("Dining Out")).toBeInTheDocument();
    expect(screen.getByText("Restaurant")).toBeInTheDocument();
  });

  it("renders desktop-vendored personal care labels", () => {
    render(<CategoryPresentation category="personal_care:cosmetics" locale="de" />);

    expect(screen.getByText("Pflege")).toBeInTheDocument();
    expect(screen.getByText("Kosmetik")).toBeInTheDocument();
  });
});
