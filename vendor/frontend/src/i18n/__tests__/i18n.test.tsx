import React from "react";
import { describe, expect, it } from "vitest";

import { localizeNode, tForLocale } from "@/i18n";

describe("i18n plumbing", () => {
  it("returns german catalog values for known keys", () => {
    expect(tForLocale("de", "nav.item.overview")).toBe("Übersicht");
    expect(tForLocale("de", "common.changes")).toBe("Änderungen");
  });

  it("keeps unknown literal text unchanged and translates known literals", () => {
    expect(localizeNode(" Close ", "de")).toBe(" Schließen ");
    expect(localizeNode("Custom merchant", "de")).toBe("Custom merchant");
  });

  it("localizes child text within react elements", () => {
    const element = localizeNode(<span>Open</span>, "de") as React.ReactElement<{ children: string }>;
    expect(element.props.children).toEqual(["Öffnen"]);
  });
});
