import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "../AppErrorBoundary";

function ExplodingComponent(): JSX.Element {
  throw new Error("simulated error");
}

describe("AppErrorBoundary", () => {
  it("renders fallback UI when a child throws", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <AppErrorBoundary>
        <ExplodingComponent />
      </AppErrorBoundary>
    );

    expect(screen.getByText("Unexpected frontend error")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry render" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload app" })).toBeInTheDocument();

    consoleSpy.mockRestore();
  });
});
