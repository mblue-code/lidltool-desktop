import type { AxeResults } from "axe-core";
import * as axe from "axe-core";

type AxeViolation = {
  id: string;
  impact: string | null;
  help: string;
  nodes: number;
};

type AxeAuditResult = {
  skipped: boolean;
  reason?: string;
  violations: AxeViolation[];
};

export async function runAxeAudit(container: HTMLElement): Promise<AxeAuditResult> {
  let result: AxeResults;
  try {
    result = await axe.run(container, {
      rules: {
        // jsdom cannot compute color contrast reliably.
        "color-contrast": {
          enabled: false
        }
      }
    });
  } catch (error) {
    const reason = error instanceof Error ? error.message : "unknown error";
    throw new Error(`Failed to execute axe audit: ${reason}`);
  }

  return {
    skipped: false,
    violations: result.violations.map((violation) => ({
      id: violation.id,
      impact: violation.impact ?? null,
      help: violation.help,
      nodes: violation.nodes.length
    }))
  };
}
