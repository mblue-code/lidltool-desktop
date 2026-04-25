export const pageLoaders = {
  overview: () => import("@/pages/DashboardPage"),
  groceries: () => import("@/pages/GroceriesPage"),
  explore: () => import("@/pages/ExplorePage"),
  offers: () => import("@/pages/OffersPage"),
  products: () => import("@/pages/ProductsPage"),
  compare: () => import("@/pages/ComparisonsPage"),
  receipts: () => import("@/pages/TransactionsPage"),
  quality: () => import("@/pages/DataQualityPage"),
  connectors: () => import("@/pages/ConnectorsPage"),
  sources: () => import("@/pages/SourcesPage"),
  manualImport: () => import("@/pages/ManualImportPage"),
  budget: () => import("@/pages/BudgetPage"),
  bills: () => import("@/pages/BillsPage"),
  cashFlow: () => import("@/pages/CashFlowPage"),
  reports: () => import("@/pages/ReportsPage"),
  goals: () => import("@/pages/GoalsPage"),
  merchants: () => import("@/pages/MerchantsPage"),
  settings: () => import("@/pages/SettingsPage"),
  patterns: () => import("@/pages/PatternsPage"),
  dashboard: () => import("@/pages/DashboardPage"),
  transactions: () => import("@/pages/TransactionsPage"),
  transactionDetail: () => import("@/pages/TransactionDetailPage"),
  documentsUpload: () => import("@/pages/DocumentsUploadPage"),
  reviewQueue: () => import("@/pages/ReviewQueuePage"),
  automations: () => import("@/pages/AutomationsPage"),
  automationInbox: () => import("@/pages/AutomationInboxPage"),
  chat: () => import("@/pages/ChatWorkspacePage"),
  reliability: () => import("@/pages/ReliabilityPage"),
  appearanceSettings: () => import("@/pages/AppearanceSettingsPage"),
  usersSettings: () => import("@/pages/UsersSettingsPage"),
  aiSettings: () => import("@/pages/AISettingsPage")
};

const ROUTE_PREFIX_PRELOADERS: Array<{
  prefix: string;
  preload: () => Promise<unknown>;
}> = [
  { prefix: "/explore", preload: pageLoaders.explore },
  { prefix: "/groceries", preload: pageLoaders.groceries },
  { prefix: "/offers", preload: pageLoaders.offers },
  { prefix: "/products", preload: pageLoaders.products },
  { prefix: "/compare", preload: pageLoaders.compare },
  { prefix: "/receipts", preload: pageLoaders.receipts },
  { prefix: "/quality", preload: pageLoaders.quality },
  { prefix: "/connectors", preload: pageLoaders.connectors },
  { prefix: "/sources", preload: pageLoaders.sources },
  { prefix: "/add", preload: pageLoaders.manualImport },
  { prefix: "/imports/manual", preload: pageLoaders.manualImport },
  { prefix: "/imports/ocr", preload: pageLoaders.documentsUpload },
  { prefix: "/budget", preload: pageLoaders.budget },
  { prefix: "/bills", preload: pageLoaders.bills },
  { prefix: "/cash-flow", preload: pageLoaders.cashFlow },
  { prefix: "/reports", preload: pageLoaders.reports },
  { prefix: "/goals", preload: pageLoaders.goals },
  { prefix: "/merchants", preload: pageLoaders.merchants },
  { prefix: "/patterns", preload: pageLoaders.patterns },
  { prefix: "/transactions", preload: pageLoaders.transactions },
  { prefix: "/documents/upload", preload: pageLoaders.documentsUpload },
  { prefix: "/review-queue", preload: pageLoaders.reviewQueue },
  { prefix: "/automations", preload: pageLoaders.automations },
  { prefix: "/automation-inbox", preload: pageLoaders.automationInbox },
  { prefix: "/chat", preload: pageLoaders.chat },
  { prefix: "/reliability", preload: pageLoaders.reliability },
  { prefix: "/settings/appearance", preload: pageLoaders.appearanceSettings },
  { prefix: "/settings/ai", preload: pageLoaders.aiSettings },
  { prefix: "/settings/users", preload: pageLoaders.usersSettings },
  { prefix: "/settings", preload: pageLoaders.settings },
  { prefix: "/", preload: pageLoaders.overview }
];

export function preloadRouteModule(pathname: string): void {
  const entry = ROUTE_PREFIX_PRELOADERS.find((candidate) =>
    candidate.prefix === "/" ? pathname === "/" : pathname.startsWith(candidate.prefix)
  );

  if (!entry) {
    return;
  }

  void entry.preload();
}
