type Envelope<T> = {
  ok: true;
  result: T;
  warnings: [];
  error: null;
  error_code?: null;
};

function ok<T>(result: T): Envelope<T> {
  return {
    ok: true,
    result,
    warnings: [],
    error: null,
    error_code: null
  };
}

const now = "2026-04-14T09:30:00Z";

export const demoAuth = {
  setupRequired: ok({
    required: false,
    bootstrap_token_required: false
  }),
  me: ok({
    user_id: "demo-user",
    username: "demo",
    display_name: "Demo Snapshot",
    is_admin: false,
    preferred_locale: "en"
  }),
  logout: ok({
    logged_out: true
  })
};

export const demoAISettings = ok({
  enabled: false,
  base_url: null,
  model: "gpt-5.4-mini",
  api_key_set: false,
  oauth_provider: null,
  oauth_connected: false,
  oauth_model: "gpt-5.4-mini",
  remote_enabled: false,
  local_runtime_enabled: true,
  local_runtime_ready: true,
  local_runtime_status: "demo snapshot",
  categorization_enabled: false,
  categorization_provider: "api_compatible",
  categorization_base_url: null,
  categorization_api_key_set: false,
  categorization_model: "gpt-5.4-mini",
  categorization_runtime_ready: true,
  categorization_runtime_status: "demo snapshot"
});

export const demoAIAgentConfig = ok({
  proxy_url: "https://demo.invalid/proxy",
  auth_token: "demo-token",
  model: "gpt-5.4-mini",
  default_model: "gpt-5.4-mini",
  local_model: "gpt-5.4-mini",
  preferred_model: "gpt-5.4-mini",
  oauth_provider: null,
  oauth_connected: false,
  available_models: [
    {
      id: "gpt-5.4-mini",
      label: "Pi Demo Model",
      source: "local",
      enabled: true,
      description: "Read-only showcase model selection for the public demo."
    }
  ]
});

export const demoSources = ok({
  sources: [
    {
      id: "lidl_plus_de",
      user_id: "demo-user",
      owner_username: "demo",
      owner_display_name: "Demo Snapshot",
      kind: "grocery",
      display_name: "Lidl Plus",
      status: "connected",
      enabled: true,
      family_share_mode: "all"
    },
    {
      id: "rewe_de",
      user_id: "demo-user",
      owner_username: "demo",
      owner_display_name: "Demo Snapshot",
      kind: "grocery",
      display_name: "REWE",
      status: "connected",
      enabled: true,
      family_share_mode: "manual"
    },
    {
      id: "amazon_de",
      user_id: "demo-user",
      owner_username: "demo",
      owner_display_name: "Demo Snapshot",
      kind: "marketplace",
      display_name: "Amazon",
      status: "connected",
      enabled: true,
      family_share_mode: "none"
    },
    {
      id: "dm_de",
      user_id: "demo-user",
      owner_username: "demo",
      owner_display_name: "Demo Snapshot",
      kind: "drugstore",
      display_name: "dm",
      status: "review",
      enabled: true,
      family_share_mode: "manual"
    }
  ]
});

export const demoDashboardCards = ok({
  totals: {
    receipt_count: 18,
    gross_cents: 49100,
    gross_currency: "491.00",
    net_cents: 42860,
    net_currency: "428.60",
    discount_total_cents: 6240,
    discount_total_currency: "62.40",
    paid_cents: 42860,
    paid_currency: "428.60",
    saved_cents: 6240,
    saved_currency: "62.40",
    savings_rate: 0.1271
  }
});

export const demoDashboardTrends = ok({
  points: [
    { year: 2025, month: 8, period_key: "2025-08", gross_cents: 40200, net_cents: 35640, discount_total_cents: 4560, paid_cents: 35640, saved_cents: 4560, savings_rate: 0.1134 },
    { year: 2025, month: 9, period_key: "2025-09", gross_cents: 43450, net_cents: 38610, discount_total_cents: 4840, paid_cents: 38610, saved_cents: 4840, savings_rate: 0.1113 },
    { year: 2025, month: 10, period_key: "2025-10", gross_cents: 42180, net_cents: 37120, discount_total_cents: 5060, paid_cents: 37120, saved_cents: 5060, savings_rate: 0.12 },
    { year: 2025, month: 11, period_key: "2025-11", gross_cents: 46290, net_cents: 40640, discount_total_cents: 5650, paid_cents: 40640, saved_cents: 5650, savings_rate: 0.1221 },
    { year: 2025, month: 12, period_key: "2025-12", gross_cents: 45540, net_cents: 40190, discount_total_cents: 5350, paid_cents: 40190, saved_cents: 5350, savings_rate: 0.1175 },
    { year: 2026, month: 1, period_key: "2026-01", gross_cents: 50310, net_cents: 43890, discount_total_cents: 6420, paid_cents: 43890, saved_cents: 6420, savings_rate: 0.1276 },
    { year: 2026, month: 2, period_key: "2026-02", gross_cents: 48780, net_cents: 42950, discount_total_cents: 5830, paid_cents: 42950, saved_cents: 5830, savings_rate: 0.1195 },
    { year: 2026, month: 3, period_key: "2026-03", gross_cents: 49100, net_cents: 42860, discount_total_cents: 6240, paid_cents: 42860, saved_cents: 6240, savings_rate: 0.1271 }
  ]
});

export const demoSavingsBreakdown = ok({
  view: "normalized",
  by_type: [
    { type: "member_discount", saved_cents: 2980, saved_currency: "29.80", discount_events: 17 },
    { type: "promotion", saved_cents: 2140, saved_currency: "21.40", discount_events: 12 },
    { type: "markdown", saved_cents: 1120, saved_currency: "11.20", discount_events: 6 }
  ]
});

export const demoRetailerComposition = ok({
  retailers: [
    { source_id: "lidl_plus_de", retailer: "Lidl", receipt_count: 8, gross_cents: 20140, net_cents: 17680, discount_total_cents: 2460, paid_cents: 17680, saved_cents: 2460, gross_share: 0.4101, net_share: 0.4125, paid_share: 0.4125, saved_share: 0.3942, savings_rate: 0.1221 },
    { source_id: "rewe_de", retailer: "REWE", receipt_count: 5, gross_cents: 12940, net_cents: 11570, discount_total_cents: 1370, paid_cents: 11570, saved_cents: 1370, gross_share: 0.2635, net_share: 0.2699, paid_share: 0.2699, saved_share: 0.2196, savings_rate: 0.1059 },
    { source_id: "amazon_de", retailer: "Amazon", receipt_count: 2, gross_cents: 8650, net_cents: 8650, discount_total_cents: 0, paid_cents: 8650, saved_cents: 0, gross_share: 0.1762, net_share: 0.2018, paid_share: 0.2018, saved_share: 0, savings_rate: 0 },
    { source_id: "dm_de", retailer: "dm", receipt_count: 3, gross_cents: 7370, net_cents: 4960, discount_total_cents: 2410, paid_cents: 4960, saved_cents: 2410, gross_share: 0.1501, net_share: 0.1157, paid_share: 0.1157, saved_share: 0.3862, savings_rate: 0.327 }
  ]
});

export const demoDepositAnalytics = ok({
  date_from: "2025-10-01",
  date_to: "2026-03-31",
  total_paid_cents: 1820,
  total_returned_cents: 1090,
  net_outstanding_cents: 730,
  monthly: [
    { month: "2025-10", paid_cents: 210, returned_cents: 140, net_cents: 70 },
    { month: "2025-11", paid_cents: 290, returned_cents: 120, net_cents: 170 },
    { month: "2025-12", paid_cents: 360, returned_cents: 210, net_cents: 150 },
    { month: "2026-01", paid_cents: 310, returned_cents: 170, net_cents: 140 },
    { month: "2026-02", paid_cents: 290, returned_cents: 230, net_cents: 60 },
    { month: "2026-03", paid_cents: 360, returned_cents: 220, net_cents: 140 }
  ]
});

export const demoRecurringCalendar = ok({
  year: 2026,
  month: 3,
  days: [
    {
      date: "2026-04-16",
      items: [
        {
          occurrence_id: "occ-spotify-apr",
          bill_id: "bill-spotify",
          bill_name: "Spotify Family",
          status: "upcoming",
          expected_amount_cents: 1799,
          actual_amount_cents: null
        }
      ],
      count: 1,
      total_expected_cents: 1799
    },
    {
      date: "2026-04-19",
      items: [
        {
          occurrence_id: "occ-catfood-apr",
          bill_id: "bill-catfood",
          bill_name: "Cat food subscription",
          status: "upcoming",
          expected_amount_cents: 3440,
          actual_amount_cents: null
        }
      ],
      count: 1,
      total_expected_cents: 3440
    },
    {
      date: "2026-04-24",
      items: [
        {
          occurrence_id: "occ-dm-apr",
          bill_id: "bill-dm",
          bill_name: "Drugstore restock",
          status: "upcoming",
          expected_amount_cents: 2800,
          actual_amount_cents: null
        }
      ],
      count: 1,
      total_expected_cents: 2800
    }
  ],
  count: 3
});

export const demoRecurringForecast = ok({
  months: 3,
  points: [
    { period: "2026-04", projected_cents: 8039, currency: "EUR" },
    { period: "2026-05", projected_cents: 8210, currency: "EUR" },
    { period: "2026-06", projected_cents: 8210, currency: "EUR" }
  ],
  total_projected_cents: 24459,
  currency: "EUR"
});

export const demoTransactionsList = ok({
  count: 6,
  total: 6,
  limit: 25,
  offset: 0,
  items: [
    { id: "tx-demo-1", purchased_at: "2026-03-28T09:14:00", source_id: "lidl_plus_de", user_id: "demo-user", source_transaction_id: "lidl-2026-03-28", store_name: "Lidl Wasbuettel Nord", total_gross_cents: 4892, discount_total_cents: 840, currency: "EUR", family_share_mode: "inherit", source_family_share_mode: "all", owner_username: "demo", owner_display_name: "Demo Snapshot", is_owner: false },
    { id: "tx-demo-2", purchased_at: "2026-03-24T18:42:00", source_id: "rewe_de", user_id: "demo-user", source_transaction_id: "rewe-2026-03-24", store_name: "REWE Braunschweig", total_gross_cents: 3718, discount_total_cents: 279, currency: "EUR", family_share_mode: "inherit", source_family_share_mode: "manual", owner_username: "demo", owner_display_name: "Demo Snapshot", is_owner: false },
    { id: "tx-demo-3", purchased_at: "2026-03-19T11:08:00", source_id: "amazon_de", user_id: "demo-user", source_transaction_id: "amazon-2026-03-19", store_name: "Amazon EU", total_gross_cents: 2999, discount_total_cents: 0, currency: "EUR", family_share_mode: "inherit", source_family_share_mode: "none", owner_username: "demo", owner_display_name: "Demo Snapshot", is_owner: false },
    { id: "tx-demo-4", purchased_at: "2026-03-13T16:21:00", source_id: "dm_de", user_id: "demo-user", source_transaction_id: "dm-2026-03-13", store_name: "dm Wolfsburg", total_gross_cents: 2364, discount_total_cents: 135, currency: "EUR", family_share_mode: "inherit", source_family_share_mode: "manual", owner_username: "demo", owner_display_name: "Demo Snapshot", is_owner: false },
    { id: "tx-demo-5", purchased_at: "2026-03-08T10:04:00", source_id: "lidl_plus_de", user_id: "demo-user", source_transaction_id: "lidl-2026-03-08", store_name: "Lidl Wasbuettel Nord", total_gross_cents: 5644, discount_total_cents: 910, currency: "EUR", family_share_mode: "inherit", source_family_share_mode: "all", owner_username: "demo", owner_display_name: "Demo Snapshot", is_owner: false },
    { id: "tx-demo-6", purchased_at: "2026-03-03T19:11:00", source_id: "rewe_de", user_id: "demo-user", source_transaction_id: "rewe-2026-03-03", store_name: "REWE Braunschweig", total_gross_cents: 4180, discount_total_cents: 230, currency: "EUR", family_share_mode: "inherit", source_family_share_mode: "manual", owner_username: "demo", owner_display_name: "Demo Snapshot", is_owner: false }
  ]
});

export const demoTransactionDetails = {
  "tx-demo-1": ok({
    transaction: {
      id: "tx-demo-1",
      source_id: "lidl_plus_de",
      user_id: "demo-user",
      source_transaction_id: "lidl-2026-03-28",
      source_account_id: "member-demo",
      purchased_at: "2026-03-28T09:14:00",
      merchant_name: "Lidl Wasbuettel Nord",
      total_gross_cents: 4892,
      currency: "EUR",
      discount_total_cents: 840,
      family_share_mode: "inherit",
      source_family_share_mode: "all",
      owner_username: "demo",
      owner_display_name: "Demo Snapshot",
      is_owner: false,
      raw_payload: {
        source: "demo",
        note: "Synthetic public demo receipt."
      }
    },
    items: [
      { id: "tx-demo-1-item-1", source_item_id: "1", line_no: 1, name: "Bio Bananen", qty: 1, unit: "kg", unit_price_cents: 229, line_total_cents: 229, category: "produce", family_shared: true },
      { id: "tx-demo-1-item-2", source_item_id: "2", line_no: 2, name: "Milbona Vollmilch 3.5%", qty: 1, unit: "l", unit_price_cents: 139, line_total_cents: 139, category: "dairy", family_shared: true },
      { id: "tx-demo-1-item-3", source_item_id: "3", line_no: 3, name: "Junger Gouda 400g", qty: 1, unit: "pack", unit_price_cents: 279, line_total_cents: 279, category: "dairy", family_shared: true },
      { id: "tx-demo-1-item-4", source_item_id: "4", line_no: 4, name: "Parkside Kuechenpapier", qty: 1, unit: "pack", unit_price_cents: 499, line_total_cents: 499, category: "household", family_shared: true }
    ],
    discounts: [
      { id: "tx-demo-1-disc-1", transaction_item_id: null, source_label: "Lidl Plus", scope: "transaction", kind: "member_discount", amount_cents: 510 },
      { id: "tx-demo-1-disc-2", transaction_item_id: null, source_label: "Promo", scope: "transaction", kind: "promotion", amount_cents: 220 },
      { id: "tx-demo-1-disc-3", transaction_item_id: null, source_label: "Markdown", scope: "transaction", kind: "markdown", amount_cents: 110 }
    ],
    documents: [
      { id: "doc-demo-1", mime_type: "image/svg+xml", file_name: "lidl-demo-receipt.svg", created_at: "2026-03-28T09:15:00" }
    ]
  }),
  "tx-demo-2": ok({
    transaction: {
      id: "tx-demo-2",
      source_id: "rewe_de",
      user_id: "demo-user",
      source_transaction_id: "rewe-2026-03-24",
      source_account_id: null,
      purchased_at: "2026-03-24T18:42:00",
      merchant_name: "REWE Braunschweig",
      total_gross_cents: 3718,
      currency: "EUR",
      discount_total_cents: 279,
      family_share_mode: "inherit",
      source_family_share_mode: "manual",
      owner_username: "demo",
      owner_display_name: "Demo Snapshot",
      is_owner: false,
      raw_payload: { source: "demo" }
    },
    items: [
      { id: "tx-demo-2-item-1", source_item_id: "1", line_no: 1, name: "Mineralwasser 6x1.5L", qty: 1, unit: "crate", unit_price_cents: 349, line_total_cents: 349, category: "beverages", family_shared: true },
      { id: "tx-demo-2-item-2", source_item_id: "2", line_no: 2, name: "Ja! Fusilli", qty: 2, unit: "pack", unit_price_cents: 89, line_total_cents: 178, category: "pantry", family_shared: true },
      { id: "tx-demo-2-item-3", source_item_id: "3", line_no: 3, name: "Hummus Pikant", qty: 1, unit: "cup", unit_price_cents: 199, line_total_cents: 199, category: "snacks", family_shared: true }
    ],
    discounts: [{ id: "tx-demo-2-disc-1", transaction_item_id: null, source_label: "Promo", scope: "transaction", kind: "promotion", amount_cents: 279 }],
    documents: [{ id: "doc-demo-2", mime_type: "image/svg+xml", file_name: "rewe-demo-receipt.svg", created_at: "2026-03-24T18:43:00" }]
  })
};

export const demoTransactionHistories = {
  "tx-demo-1": ok({
    transaction_id: "tx-demo-1",
    count: 3,
    events: [
      { id: "hist-1", created_at: "2026-03-28T09:15:02", action: "ingested", actor_id: null, entity_type: "transaction", details: { source: "lidl_plus_de" } },
      { id: "hist-2", created_at: "2026-03-28T09:15:03", action: "discounts_normalized", actor_id: null, entity_type: "discount", details: { kinds: 3 } },
      { id: "hist-3", created_at: "2026-03-28T09:15:08", action: "product_linked", actor_id: "system", entity_type: "item", details: { linked_items: 4 } }
    ]
  }),
  "tx-demo-2": ok({
    transaction_id: "tx-demo-2",
    count: 2,
    events: [
      { id: "hist-4", created_at: "2026-03-24T18:43:02", action: "ingested", actor_id: null, entity_type: "transaction", details: { source: "rewe_de" } },
      { id: "hist-5", created_at: "2026-03-24T18:43:04", action: "promotion_detected", actor_id: "system", entity_type: "discount", details: { amount_cents: 279 } }
    ]
  })
};

export const demoProducts = ok({
  items: [
    { product_id: "prod-gouda", canonical_name: "Junger Gouda 400g", brand: "Milbona", default_unit: "pack", category_id: "dairy", gtin_ean: null, alias_count: 4 },
    { product_id: "prod-milk", canonical_name: "Milbona Vollmilch 3.5%", brand: "Milbona", default_unit: "l", category_id: "dairy", gtin_ean: null, alias_count: 6 },
    { product_id: "prod-bananas", canonical_name: "Bio Bananen", brand: null, default_unit: "kg", category_id: "produce", gtin_ean: null, alias_count: 5 }
  ],
  count: 3
});

export const demoProductDetails = {
  "prod-gouda": ok({
    product: { product_id: "prod-gouda", canonical_name: "Junger Gouda 400g", brand: "Milbona", default_unit: "pack", category_id: "dairy", gtin_ean: null, created_at: "2025-10-04T12:00:00Z" },
    aliases: [
      { alias_id: "alias-gouda-1", source_kind: "grocery", raw_name: "Junger Gouda 400g", raw_sku: null, match_confidence: 0.98, match_method: "name_cluster", created_at: "2025-10-04T12:00:01Z" },
      { alias_id: "alias-gouda-2", source_kind: "grocery", raw_name: "Gouda Jung 400g", raw_sku: null, match_confidence: 0.94, match_method: "name_cluster", created_at: "2025-11-01T12:00:01Z" }
    ]
  }),
  "prod-milk": ok({
    product: { product_id: "prod-milk", canonical_name: "Milbona Vollmilch 3.5%", brand: "Milbona", default_unit: "l", category_id: "dairy", gtin_ean: null, created_at: "2025-09-08T12:00:00Z" },
    aliases: [
      { alias_id: "alias-milk-1", source_kind: "grocery", raw_name: "Milbona Vollmilch 3,5%", raw_sku: null, match_confidence: 0.99, match_method: "exactish", created_at: "2025-09-08T12:00:01Z" }
    ]
  }),
  "prod-bananas": ok({
    product: { product_id: "prod-bananas", canonical_name: "Bio Bananen", brand: null, default_unit: "kg", category_id: "produce", gtin_ean: null, created_at: "2025-08-14T12:00:00Z" },
    aliases: [
      { alias_id: "alias-bananas-1", source_kind: "grocery", raw_name: "Bio Bananen", raw_sku: null, match_confidence: 0.99, match_method: "exactish", created_at: "2025-08-14T12:00:01Z" }
    ]
  })
};

export const demoProductSeries = {
  "prod-gouda": ok({
    product_id: "prod-gouda",
    net: true,
    grain: "month",
    points: [
      { period: "2025-12", source_kind: "lidl_plus_de", unit_price_cents: 249, purchase_count: 2, min_unit_price_cents: 239, max_unit_price_cents: 249 },
      { period: "2026-01", source_kind: "lidl_plus_de", unit_price_cents: 259, purchase_count: 2, min_unit_price_cents: 249, max_unit_price_cents: 259 },
      { period: "2026-02", source_kind: "rewe_de", unit_price_cents: 269, purchase_count: 1, min_unit_price_cents: 269, max_unit_price_cents: 269 },
      { period: "2026-03", source_kind: "lidl_plus_de", unit_price_cents: 279, purchase_count: 2, min_unit_price_cents: 269, max_unit_price_cents: 279 }
    ]
  }),
  "prod-milk": ok({
    product_id: "prod-milk",
    net: true,
    grain: "month",
    points: [
      { period: "2025-12", source_kind: "lidl_plus_de", unit_price_cents: 135, purchase_count: 4, min_unit_price_cents: 129, max_unit_price_cents: 139 },
      { period: "2026-01", source_kind: "lidl_plus_de", unit_price_cents: 137, purchase_count: 4, min_unit_price_cents: 135, max_unit_price_cents: 139 },
      { period: "2026-02", source_kind: "lidl_plus_de", unit_price_cents: 139, purchase_count: 3, min_unit_price_cents: 139, max_unit_price_cents: 139 },
      { period: "2026-03", source_kind: "lidl_plus_de", unit_price_cents: 139, purchase_count: 3, min_unit_price_cents: 139, max_unit_price_cents: 139 }
    ]
  }),
  "prod-bananas": ok({
    product_id: "prod-bananas",
    net: true,
    grain: "month",
    points: [
      { period: "2025-12", source_kind: "lidl_plus_de", unit_price_cents: 229, purchase_count: 2, min_unit_price_cents: 219, max_unit_price_cents: 229 },
      { period: "2026-01", source_kind: "rewe_de", unit_price_cents: 239, purchase_count: 1, min_unit_price_cents: 239, max_unit_price_cents: 239 },
      { period: "2026-02", source_kind: "lidl_plus_de", unit_price_cents: 219, purchase_count: 2, min_unit_price_cents: 209, max_unit_price_cents: 219 },
      { period: "2026-03", source_kind: "lidl_plus_de", unit_price_cents: 215, purchase_count: 2, min_unit_price_cents: 199, max_unit_price_cents: 229 }
    ]
  })
};

export const demoProductPurchases = {
  "prod-gouda": ok({
    product_id: "prod-gouda",
    count: 4,
    items: [
      { transaction_id: "tx-demo-1", date: "2026-03-28", source_id: "lidl_plus_de", source_kind: "grocery", merchant_name: "Lidl Wasbuettel Nord", raw_item_name: "Junger Gouda 400g", quantity_value: 1, quantity_unit: "pack", unit_price_gross_cents: 279, unit_price_net_cents: 279, line_total_gross_cents: 279, line_total_net_cents: 279 },
      { transaction_id: "tx-demo-2", date: "2026-02-21", source_id: "rewe_de", source_kind: "grocery", merchant_name: "REWE Braunschweig", raw_item_name: "Gouda Jung 400g", quantity_value: 1, quantity_unit: "pack", unit_price_gross_cents: 269, unit_price_net_cents: 269, line_total_gross_cents: 269, line_total_net_cents: 269 }
    ]
  }),
  "prod-milk": ok({
    product_id: "prod-milk",
    count: 6,
    items: [
      { transaction_id: "tx-demo-1", date: "2026-03-28", source_id: "lidl_plus_de", source_kind: "grocery", merchant_name: "Lidl Wasbuettel Nord", raw_item_name: "Milbona Vollmilch 3.5%", quantity_value: 1, quantity_unit: "l", unit_price_gross_cents: 139, unit_price_net_cents: 139, line_total_gross_cents: 139, line_total_net_cents: 139 }
    ]
  }),
  "prod-bananas": ok({
    product_id: "prod-bananas",
    count: 5,
    items: [
      { transaction_id: "tx-demo-1", date: "2026-03-28", source_id: "lidl_plus_de", source_kind: "grocery", merchant_name: "Lidl Wasbuettel Nord", raw_item_name: "Bio Bananen", quantity_value: 1, quantity_unit: "kg", unit_price_gross_cents: 229, unit_price_net_cents: 229, line_total_gross_cents: 229, line_total_net_cents: 229 }
    ]
  })
};

function connectorAction(kind: string | null, enabled: boolean) {
  return {
    kind,
    href: null,
    enabled
  };
}

function connectorOperatorActions() {
  return {
    full_sync: false,
    rescan: false,
    reload: false,
    install: false,
    enable: false,
    disable: false,
    uninstall: false,
    configure: false,
    manual_commands: {}
  };
}

function connectorRow(input: {
  source_id: string;
  display_name: string;
  maturity: "verified" | "working" | "preview" | "stub";
  status: "connected" | "preview" | "needs_attention" | "ready";
  description: string;
  origin_label: string;
  runtime_kind: string;
  install_state: "catalog_only" | "discovered" | "installed";
  enable_state: "enabled" | "disabled" | "blocked" | "invalid" | "incompatible";
  config_state: "not_required" | "required" | "incomplete" | "complete";
  supports_bootstrap: boolean;
  supports_sync: boolean;
  supports_live_session: boolean;
  supports_live_session_bootstrap: boolean;
  status_detail: string | null;
  last_sync_summary: string | null;
  last_synced_at: string | null;
  support_posture: string;
}) {
  const operator = connectorOperatorActions();
  const primary = connectorAction(input.supports_bootstrap ? "set_up" : "view", false);
  const secondary = connectorAction(input.supports_sync ? "sync_now" : "learn_more", false);

  return {
    source_id: input.source_id,
    plugin_id: null,
    display_name: input.display_name,
    origin: "catalog",
    origin_label: input.origin_label,
    runtime_kind: input.runtime_kind,
    install_origin: "catalog",
    install_state: input.install_state,
    enable_state: input.enable_state,
    config_state: input.config_state,
    maturity: input.maturity,
    maturity_label: input.maturity,
    supports_bootstrap: input.supports_bootstrap,
    supports_sync: input.supports_sync,
    supports_live_session: input.supports_live_session,
    supports_live_session_bootstrap: input.supports_live_session_bootstrap,
    trust_class: "verified",
    status_detail: input.status_detail,
    last_sync_summary: input.last_sync_summary,
    last_synced_at: input.last_synced_at,
    ui: {
      status: input.status,
      visibility: "default",
      description: input.description,
      actions: {
        primary,
        secondary,
        operator
      }
    },
    actions: {
      primary,
      secondary,
      operator
    },
    advanced: {
      source_exists: true,
      stale: false,
      stale_reason: null,
      auth_state: input.status === "needs_attention" ? "reauth_required" : "ready",
      latest_sync_output: input.last_sync_summary ? [input.last_sync_summary] : [],
      latest_bootstrap_output: input.supports_live_session ? ["demo snapshot - bootstrap flow disabled"] : [],
      latest_sync_status: input.status === "needs_attention" ? "failed" : "idle",
      latest_bootstrap_status: input.status === "needs_attention" ? "failed" : "idle",
      block_reason: null,
      release: {
        maturity: input.maturity,
        label: input.maturity,
        support_posture: input.support_posture,
        description: input.description,
        default_visibility: "default",
        graduation_requirements: [
          "Stable fixture-driven demo only.",
          "Real bootstrap and sync remain disabled on the public host."
        ]
      },
      origin: {
        kind: "catalog",
        runtime_kind: input.runtime_kind,
        search_path: null,
        origin_path: null,
        origin_directory: null
      },
      diagnostics: input.status_detail ? [input.status_detail] : [],
      manual_commands: {}
    }
  };
}

export const demoConnectors = ok({
  generated_at: now,
  viewer: {
    is_admin: false
  },
  operator_actions: {
    can_reload: false,
    can_rescan: false
  },
  summary: {
    total_connectors: 4,
    by_status: {
      connected: 1,
      ready: 1,
      preview: 1,
      needs_attention: 1
    }
  },
  connectors: [
    connectorRow({
      source_id: "lidl_plus_de",
      display_name: "Lidl Plus",
      maturity: "verified",
      status: "connected",
      description: "OAuth-based receipt sync with discount separation and local-first storage.",
      origin_label: "Bundled catalog",
      runtime_kind: "oauth",
      install_state: "installed",
      enable_state: "enabled",
      config_state: "complete",
      supports_bootstrap: true,
      supports_sync: true,
      supports_live_session: false,
      supports_live_session_bootstrap: false,
      status_detail: "Connected in the synthetic demo dataset.",
      last_sync_summary: "Last demo sync imported 8 receipts and 42 line items.",
      last_synced_at: "2026-04-13T18:20:00Z",
      support_posture: "Stable self-hosted connector"
    }),
    connectorRow({
      source_id: "rewe_de",
      display_name: "REWE",
      maturity: "working",
      status: "ready",
      description: "Session bootstrap and sync flow for retailers that need an interactive login.",
      origin_label: "Bundled catalog",
      runtime_kind: "playwright_session",
      install_state: "installed",
      enable_state: "enabled",
      config_state: "complete",
      supports_bootstrap: true,
      supports_sync: true,
      supports_live_session: true,
      supports_live_session_bootstrap: true,
      status_detail: "Live-session capable connector showcased in read-only mode.",
      last_sync_summary: "Demo snapshot highlights session bootstrap without exposing live credentials.",
      last_synced_at: "2026-04-12T07:45:00Z",
      support_posture: "Live-session sensitive connector"
    }),
    connectorRow({
      source_id: "amazon_de",
      display_name: "Amazon",
      maturity: "working",
      status: "preview",
      description: "Order-history connector that normalizes marketplace orders into the same ledger.",
      origin_label: "Bundled catalog",
      runtime_kind: "session",
      install_state: "installed",
      enable_state: "enabled",
      config_state: "complete",
      supports_bootstrap: true,
      supports_sync: true,
      supports_live_session: true,
      supports_live_session_bootstrap: true,
      status_detail: "Preview posture in the public demo.",
      last_sync_summary: "2 household replenishment orders normalized.",
      last_synced_at: "2026-04-10T13:12:00Z",
      support_posture: "Preview connector with read-only showcase"
    }),
    connectorRow({
      source_id: "dm_de",
      display_name: "dm",
      maturity: "preview",
      status: "needs_attention",
      description: "Illustrates how review-first flows surface extraction issues instead of silently failing.",
      origin_label: "Bundled catalog",
      runtime_kind: "ocr",
      install_state: "installed",
      enable_state: "enabled",
      config_state: "incomplete",
      supports_bootstrap: false,
      supports_sync: false,
      supports_live_session: false,
      supports_live_session_bootstrap: false,
      status_detail: "One OCR-imported receipt is routed to review in this demo dataset.",
      last_sync_summary: null,
      last_synced_at: null,
      support_posture: "Preview review-first ingestion"
    })
  ]
});

export const demoConnectorSyncStatuses = {
  "lidl_plus_de": ok({
    source_id: "lidl_plus_de",
    status: "idle",
    command: null,
    pid: null,
    started_at: null,
    finished_at: "2026-04-13T18:20:00Z",
    return_code: 0,
    output_tail: ["stage=completed seen=8/8 new=0 items=42"],
    can_cancel: false
  }),
  "rewe_de": ok({
    source_id: "rewe_de",
    status: "idle",
    command: null,
    pid: null,
    started_at: null,
    finished_at: "2026-04-12T07:45:00Z",
    return_code: 0,
    output_tail: ["stage=completed seen=5/5 new=0 items=31"],
    can_cancel: false
  }),
  "amazon_de": ok({
    source_id: "amazon_de",
    status: "idle",
    command: null,
    pid: null,
    started_at: null,
    finished_at: "2026-04-10T13:12:00Z",
    return_code: 0,
    output_tail: ["stage=completed seen=2/2 new=0 items=4"],
    can_cancel: false
  }),
  "dm_de": ok({
    source_id: "dm_de",
    status: "failed",
    command: null,
    pid: null,
    started_at: "2026-04-09T09:00:00Z",
    finished_at: "2026-04-09T09:00:12Z",
    return_code: 1,
    output_tail: ["stage=ocr_review required current=merchant header cropped"],
    can_cancel: false
  })
};

export const demoReviewQueueList = ok({
  limit: 25,
  offset: 0,
  count: 2,
  total: 2,
  items: [
    {
      document_id: "doc-review-1",
      transaction_id: "tx-demo-4",
      source_id: "dm_de",
      review_status: "needs_review",
      ocr_status: "completed",
      merchant_name: "dm Wolfsburg",
      purchased_at: "2026-03-13T16:21:00",
      total_gross_cents: 2364,
      currency: "EUR",
      transaction_confidence: 0.71,
      ocr_confidence: 0.82,
      created_at: "2026-03-13T16:21:21"
    },
    {
      document_id: "doc-review-2",
      transaction_id: "tx-demo-7",
      source_id: "ocr_upload",
      review_status: "needs_review",
      ocr_status: "completed",
      merchant_name: "Amazon EU",
      purchased_at: "2026-03-05T11:10:00",
      total_gross_cents: 1249,
      currency: "EUR",
      transaction_confidence: 0.79,
      ocr_confidence: 0.88,
      created_at: "2026-03-05T11:10:19"
    }
  ]
});

export const demoReviewQueueDetails = {
  "doc-review-1": ok({
    document: {
      id: "doc-review-1",
      transaction_id: "tx-demo-4",
      source_id: "dm_de",
      review_status: "needs_review",
      ocr_status: "completed",
      file_name: "dm-receipt-demo.jpg",
      mime_type: "image/jpeg",
      storage_uri: "demo://documents/dm-receipt-demo.jpg",
      ocr_provider: "local_vlm",
      ocr_confidence: 0.82,
      ocr_fallback_used: false,
      ocr_latency_ms: 1840,
      ocr_text: "dm drogerie markt ...",
      created_at: "2026-03-13T16:21:21",
      processed_at: "2026-03-13T16:21:23"
    },
    transaction: {
      id: "tx-demo-4",
      source_id: "dm_de",
      source_transaction_id: "dm-2026-03-13",
      purchased_at: "2026-03-13T16:21:00",
      merchant_name: "dm Wolfsburg",
      total_gross_cents: 2364,
      currency: "EUR",
      discount_total_cents: 135,
      confidence: 0.71,
      raw_payload: { source: "demo" }
    },
    items: [
      { id: "doc-review-1-item-1", line_no: 1, name: "Balea Shampoo", qty: 1, unit: "pc", unit_price_cents: 195, line_total_cents: 195, category: "care", confidence: 0.96, raw_payload: {} },
      { id: "doc-review-1-item-2", line_no: 2, name: "Dontodent Sensitive", qty: 1, unit: "pc", unit_price_cents: 85, line_total_cents: 85, category: "care", confidence: 0.94, raw_payload: {} },
      { id: "doc-review-1-item-3", line_no: 3, name: "Unknown line", qty: 1, unit: null, unit_price_cents: null, line_total_cents: 0, category: null, confidence: 0.44, raw_payload: {} }
    ],
    confidence: {
      transaction: 0.71,
      items: {
        "doc-review-1-item-1": 0.96,
        "doc-review-1-item-2": 0.94,
        "doc-review-1-item-3": 0.44
      }
    }
  }),
  "doc-review-2": ok({
    document: {
      id: "doc-review-2",
      transaction_id: "tx-demo-7",
      source_id: "ocr_upload",
      review_status: "needs_review",
      ocr_status: "completed",
      file_name: "amazon-demo-upload.pdf",
      mime_type: "application/pdf",
      storage_uri: "demo://documents/amazon-demo-upload.pdf",
      ocr_provider: "local_vlm",
      ocr_confidence: 0.88,
      ocr_fallback_used: true,
      ocr_latency_ms: 2210,
      ocr_text: "Amazon order...",
      created_at: "2026-03-05T11:10:19",
      processed_at: "2026-03-05T11:10:22"
    },
    transaction: {
      id: "tx-demo-7",
      source_id: "ocr_upload",
      source_transaction_id: "ocr-amazon-demo",
      purchased_at: "2026-03-05T11:10:00",
      merchant_name: "Amazon EU",
      total_gross_cents: 1249,
      currency: "EUR",
      discount_total_cents: 0,
      confidence: 0.79,
      raw_payload: { source: "demo" }
    },
    items: [
      { id: "doc-review-2-item-1", line_no: 1, name: "Filter cartridge", qty: 1, unit: "pc", unit_price_cents: 1249, line_total_cents: 1249, category: "household", confidence: 0.79, raw_payload: {} }
    ],
    confidence: { transaction: 0.79 }
  })
};

export const demoChatThreads = ok({
  items: [
    { thread_id: "thread-spend", user_id: "demo-user", title: "Where is my grocery spend going?", stream_status: "idle", created_at: "2026-04-11T08:00:00Z", updated_at: "2026-04-11T08:03:00Z", archived_at: null },
    { thread_id: "thread-price", user_id: "demo-user", title: "Which products became more expensive?", stream_status: "idle", created_at: "2026-04-10T09:20:00Z", updated_at: "2026-04-10T09:23:00Z", archived_at: null },
    { thread_id: "thread-patterns", user_id: "demo-user", title: "What patterns stand out in this household?", stream_status: "idle", created_at: "2026-04-09T14:12:00Z", updated_at: "2026-04-09T14:15:00Z", archived_at: null }
  ],
  total: 3
});

function textPart(text: string) {
  return [{ type: "text", text }];
}

export const demoChatMessages = {
  "thread-spend": ok({
    items: [
      { message_id: "msg-spend-1", thread_id: "thread-spend", role: "user", content_json: textPart("Where is my grocery spend going right now?"), tool_name: null, tool_call_id: null, idempotency_key: null, usage_json: null, error: null, created_at: "2026-04-11T08:00:00Z" },
      { message_id: "msg-spend-2", thread_id: "thread-spend", role: "tool", content_json: textPart("Net spend 428.60 EUR. Lidl share 41%. Savings rate 12.7%."), tool_name: "dashboard_summary", tool_call_id: "tool-dashboard-summary", idempotency_key: null, usage_json: null, error: null, created_at: "2026-04-11T08:00:06Z" },
      { message_id: "msg-spend-3", thread_id: "thread-spend", role: "assistant", content_json: textPart("Most spend in the synthetic March household goes to Lidl, then REWE, with dairy, pantry staples, and household basics showing the densest repeat purchases."), tool_name: null, tool_call_id: null, idempotency_key: null, usage_json: { output: 86, input: 122 }, error: null, created_at: "2026-04-11T08:00:08Z" }
    ],
    total: 3
  }),
  "thread-price": ok({
    items: [
      { message_id: "msg-price-1", thread_id: "thread-price", role: "user", content_json: textPart("Which products became more expensive over time?"), tool_name: null, tool_call_id: null, idempotency_key: null, usage_json: null, error: null, created_at: "2026-04-10T09:20:00Z" },
      { message_id: "msg-price-2", thread_id: "thread-price", role: "tool", content_json: textPart("Matched Gouda, paper towels, and cat food as the strongest upward movers over the last 90 days."), tool_name: "search_products", tool_call_id: "tool-search-products", idempotency_key: null, usage_json: null, error: null, created_at: "2026-04-10T09:20:04Z" },
      { message_id: "msg-price-3", thread_id: "thread-price", role: "assistant", content_json: textPart("Cheese and paper goods rose the fastest in the sample data, while bananas softened slightly. Gouda shows the cleanest cross-retailer inflation signal."), tool_name: null, tool_call_id: null, idempotency_key: null, usage_json: { output: 78, input: 108 }, error: null, created_at: "2026-04-10T09:20:08Z" }
    ],
    total: 3
  }),
  "thread-patterns": ok({
    items: [
      { message_id: "msg-patterns-1", thread_id: "thread-patterns", role: "user", content_json: textPart("What patterns stand out in this household?"), tool_name: null, tool_call_id: null, idempotency_key: null, usage_json: null, error: null, created_at: "2026-04-09T14:12:00Z" },
      { message_id: "msg-patterns-2", thread_id: "thread-patterns", role: "tool", content_json: textPart("Detected weekly Saturday Lidl baskets, midweek REWE top-ups, and a 28-35 day Amazon replenishment cycle."), tool_name: "search_transactions", tool_call_id: "tool-search-transactions", idempotency_key: null, usage_json: null, error: null, created_at: "2026-04-09T14:12:05Z" },
      { message_id: "msg-patterns-3", thread_id: "thread-patterns", role: "assistant", content_json: textPart("The synthetic household has a stable weekly grocery anchor, a smaller midweek refill trip, and a monthly marketplace pulse for bulk consumables."), tool_name: null, tool_call_id: null, idempotency_key: null, usage_json: { output: 75, input: 101 }, error: null, created_at: "2026-04-09T14:12:08Z" }
    ],
    total: 3
  })
};
