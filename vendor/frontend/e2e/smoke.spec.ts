import { expect, test } from "@playwright/test";

function okEnvelope(result: unknown): Record<string, unknown> {
  return {
    ok: true,
    result,
    warnings: [],
    error: null
  };
}

test("dashboard smoke: renders KPI cards from API", async ({ page }) => {
  await page.route("**/api/v1/dashboard/**", async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === "/api/v1/dashboard/cards") {
      return route.fulfill({
        json: okEnvelope({
          totals: {
            receipt_count: 8,
            paid_cents: 26_400,
            paid_currency: "EUR",
            saved_cents: 3_200,
            saved_currency: "EUR",
            gross_cents: 29_600,
            gross_currency: "EUR",
            savings_rate: 0.1081
          }
        })
      });
    }

    if (url.pathname === "/api/v1/dashboard/trends") {
      return route.fulfill({
        json: okEnvelope({
          points: [
            {
              year: 2026,
              month: 2,
              period_key: "2026-02",
              paid_cents: 26_400,
              saved_cents: 3_200,
              savings_rate: 0.1081
            }
          ]
        })
      });
    }

    if (url.pathname === "/api/v1/dashboard/savings-breakdown") {
      return route.fulfill({
        json: okEnvelope({
          view: "native",
          by_type: [
            {
              type: "promotion",
              saved_cents: 1_800,
              saved_currency: "EUR",
              discount_events: 4
            }
          ]
        })
      });
    }

    if (url.pathname === "/api/v1/dashboard/retailer-composition") {
      return route.fulfill({
        json: okEnvelope({
          retailers: [
            {
              source_id: "lidl",
              retailer: "Lidl",
              paid_cents: 26_400,
              saved_cents: 3_200,
              paid_share: 1,
              saved_share: 1,
              savings_rate: 0.1081
            }
          ]
        })
      });
    }

    return route.fulfill({ status: 404, json: okEnvelope({}) });
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Dashboard", level: 1 })).toBeVisible();
  await expect(page.getByText("Paid Total")).toBeVisible();
  await expect(page.getByText("Saved Total")).toBeVisible();
  await expect(page.getByText(/^Savings Rate$/)).toBeVisible();
});

test("transaction detail smoke: submits override mutation", async ({ page }) => {
  let overrideRequest: Record<string, unknown> | null = null;

  await page.route("**/api/v1/transactions/**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (method === "GET" && url.pathname === "/api/v1/transactions/tx-1") {
      return route.fulfill({
        json: okEnvelope({
          transaction: {
            id: "tx-1",
            source_id: "lidl",
            source_transaction_id: "source-1",
            purchased_at: "2026-02-19T09:00:00Z",
            merchant_name: "Store Alpha",
            total_gross_cents: 920,
            discount_total_cents: 120,
            raw_payload: {}
          },
          items: [
            {
              id: "item-1",
              line_no: 1,
              name: "Milk",
              qty: 1,
              unit: "pcs",
              line_total_cents: 199,
              category: "grocery"
            }
          ],
          discounts: [],
          documents: [
            {
              id: "doc-1",
              mime_type: "application/octet-stream",
              file_name: "receipt.bin",
              created_at: "2026-02-19T09:00:00Z"
            }
          ]
        })
      });
    }

    if (method === "GET" && url.pathname === "/api/v1/transactions/tx-1/history") {
      return route.fulfill({
        json: okEnvelope({
          transaction_id: "tx-1",
          count: 0,
          events: []
        })
      });
    }

    if (method === "PATCH" && url.pathname === "/api/v1/transactions/tx-1/overrides") {
      overrideRequest = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      return route.fulfill({
        json: okEnvelope({
          transaction_id: "tx-1",
          mode: "local",
          local: {
            transaction: {
              transaction_id: "tx-1",
              updated_fields: ["merchant_name"]
            },
            items: []
          },
          global: {
            created: []
          }
        })
      });
    }

    return route.fulfill({ status: 404, json: okEnvelope({}) });
  });

  await page.goto("/transactions/tx-1");

  await expect(page.getByRole("heading", { name: "Transaction Detail" })).toBeVisible();
  await page.getByLabel("Merchant Name").fill("Store Beta");
  await page.getByRole("button", { name: "Apply override" }).click();

  await expect(page.getByText("Overrides applied.")).toBeVisible();
  expect(overrideRequest).not.toBeNull();
  expect((overrideRequest?.transaction_corrections as Record<string, unknown>)?.merchant_name).toBe("Store Beta");
});

test("review queue smoke: patches and rejects a pending document", async ({ page }) => {
  let rejectCalls = 0;
  let transactionPatchCalls = 0;
  let transactionPatchRequest: Record<string, unknown> | null = null;

  await page.route("**/api/v1/review-queue**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (method === "GET" && url.pathname === "/api/v1/review-queue") {
      return route.fulfill({
        json: okEnvelope({
          limit: 25,
          offset: 0,
          count: 1,
          total: 1,
          items: [
            {
              document_id: "doc-1",
              transaction_id: "tx-1",
              source_id: "ocr_upload",
              review_status: "needs_review",
              ocr_status: "completed",
              merchant_name: "Queue Store",
              purchased_at: "2026-02-19T11:59:00Z",
              total_gross_cents: 449,
              currency: "EUR",
              transaction_confidence: 0.7,
              ocr_confidence: 0.82,
              created_at: "2026-02-19T12:00:00Z"
            }
          ]
        })
      });
    }

    if (method === "GET" && url.pathname === "/api/v1/review-queue/doc-1") {
      return route.fulfill({
        json: okEnvelope({
          document: {
            id: "doc-1",
            transaction_id: "tx-1",
            source_id: "ocr_upload",
            review_status: "needs_review",
            ocr_status: "completed",
            file_name: "receipt.png",
            mime_type: "image/png",
            storage_uri: "file:///tmp/receipt.png",
            ocr_provider: "external_api",
            ocr_confidence: 0.82,
            ocr_fallback_used: false,
            ocr_latency_ms: 300,
            ocr_text: "receipt text",
            created_at: "2026-02-19T12:00:00Z",
            processed_at: "2026-02-19T12:01:00Z"
          },
          transaction: {
            id: "tx-1",
            source_id: "ocr_upload",
            source_transaction_id: "source-1",
            purchased_at: "2026-02-19T11:59:00Z",
            merchant_name: "Queue Store",
            total_gross_cents: 449,
            currency: "EUR",
            discount_total_cents: null,
            confidence: 0.7,
            raw_payload: {}
          },
          items: [
            {
              id: "item-1",
              line_no: 1,
              name: "Milk",
              qty: 1,
              unit: "pcs",
              unit_price_cents: 199,
              line_total_cents: 199,
              category: null,
              confidence: 0.65,
              raw_payload: {}
            }
          ],
          confidence: {
            transaction_confidence: 0.7
          }
        })
      });
    }

    if (method === "PATCH" && url.pathname === "/api/v1/review-queue/doc-1/transaction") {
      transactionPatchCalls += 1;
      transactionPatchRequest = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      return route.fulfill({
        json: okEnvelope({
          transaction_id: "tx-1",
          updated_fields: ["merchant_name"]
        })
      });
    }

    if (method === "POST" && url.pathname === "/api/v1/review-queue/doc-1/reject") {
      rejectCalls += 1;
      return route.fulfill({
        json: okEnvelope({
          document_id: "doc-1",
          review_status: "rejected"
        })
      });
    }

    return route.fulfill({ status: 404, json: okEnvelope({}) });
  });

  await page.goto("/review-queue/doc-1");

  await expect(page.getByRole("heading", { name: "Review Detail", level: 2 })).toBeVisible();
  await page.getByLabel("Transaction corrections JSON").fill("{\"merchant_name\":\"Queue Store Updated\"}");
  await page.getByRole("button", { name: "Apply transaction patch" }).click();
  await expect(page.getByText("Transaction fields updated: merchant_name")).toBeVisible();

  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Reject" }).click();

  await expect(page.getByText('Review status updated to "rejected".')).toBeVisible();
  expect(transactionPatchCalls).toBe(1);
  expect((transactionPatchRequest?.corrections as Record<string, unknown>)?.merchant_name).toBe(
    "Queue Store Updated"
  );
  expect(rejectCalls).toBe(1);
});

test("automations smoke: toggles a rule from list action", async ({ page }) => {
  let toggleCalls = 0;
  let toggleRequest: Record<string, unknown> | null = null;

  await page.route("**/api/v1/automations**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (method === "GET" && url.pathname === "/api/v1/automations") {
      return route.fulfill({
        json: okEnvelope({
          count: 1,
          total: 1,
          limit: 25,
          offset: 0,
          items: [
            {
              id: "rule-1",
              name: "Weekly summary rule",
              rule_type: "weekly_summary",
              enabled: true,
              trigger_config: {
                schedule: {
                  interval_seconds: 3600
                }
              },
              action_config: {
                months_back: 3,
                include_breakdown: true
              },
              next_run_at: null,
              last_run_at: null,
              created_at: "2026-02-19T12:00:00Z",
              updated_at: "2026-02-19T12:00:00Z"
            }
          ]
        })
      });
    }

    if (method === "PATCH" && url.pathname === "/api/v1/automations/rule-1") {
      toggleCalls += 1;
      toggleRequest = (route.request().postDataJSON() ?? {}) as Record<string, unknown>;
      return route.fulfill({
        json: okEnvelope({
          id: "rule-1",
          name: "Weekly summary rule",
          rule_type: "weekly_summary",
          enabled: false,
          trigger_config: {
            schedule: {
              interval_seconds: 3600
            }
          },
          action_config: {
            months_back: 3,
            include_breakdown: true
          },
          next_run_at: null,
          last_run_at: null,
          created_at: "2026-02-19T12:00:00Z",
          updated_at: "2026-02-19T12:10:00Z"
        })
      });
    }

    return route.fulfill({ status: 404, json: okEnvelope({}) });
  });

  await page.goto("/automations");

  await expect(page.getByRole("heading", { name: "Automations", level: 1 })).toBeVisible();
  await expect(page.getByText("Weekly summary rule")).toBeVisible();

  await page.getByRole("button", { name: "Disable" }).click();
  await expect(page.getByRole("heading", { name: "Disable automation rule" })).toBeVisible();
  await page.getByRole("button", { name: "Disable" }).click();

  await expect(page.getByText("Rule disabled.")).toBeVisible();
  expect(toggleCalls).toBe(1);
  expect(toggleRequest?.enabled).toBe(false);
});

test("automation inbox smoke: opens execution payload dialog", async ({ page }) => {
  await page.route("**/api/v1/automations/executions**", async (route) => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (method === "GET" && url.pathname === "/api/v1/automations/executions") {
      return route.fulfill({
        json: okEnvelope({
          count: 1,
          total: 1,
          limit: 25,
          offset: 0,
          items: [
            {
              id: "exec-1",
              rule_id: "rule-1",
              rule_name: "Weekly summary rule",
              rule_type: "weekly_summary",
              status: "success",
              triggered_at: "2026-02-19T12:10:00Z",
              executed_at: "2026-02-19T12:10:02Z",
              result: {
                template: "weekly_summary",
                summary: "ok"
              },
              error: null,
              created_at: "2026-02-19T12:10:00Z"
            }
          ]
        })
      });
    }

    return route.fulfill({ status: 404, json: okEnvelope({}) });
  });

  await page.goto("/automation-inbox");

  await expect(page.getByRole("heading", { name: "Automation Inbox", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "View payload" }).click();

  await expect(page.getByRole("heading", { name: "Execution payload" })).toBeVisible();
  await expect(page.getByText(/"id": "exec-1"/)).toBeVisible();
});
