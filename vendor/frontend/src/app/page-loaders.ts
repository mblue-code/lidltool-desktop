export const pageLoaders = {
  overview: () => import("@/pages/DashboardPage"),
  explore: () => import("@/pages/ExplorePage"),
  products: () => import("@/pages/ProductsPage"),
  offers: () => import("@/pages/OffersPage"),
  compare: () => import("@/pages/ComparisonsPage"),
  receipts: () => import("@/pages/TransactionsPage"),
  quality: () => import("@/pages/DataQualityPage"),
  connectors: () => import("@/pages/ConnectorsPage"),
  sources: () => import("@/pages/SourcesPage"),
  manualImport: () => import("@/pages/ManualImportPage"),
  budget: () => import("@/pages/BudgetPage"),
  bills: () => import("@/pages/BillsPage"),
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
  usersSettings: () => import("@/pages/UsersSettingsPage"),
  aiSettings: () => import("@/pages/AISettingsPage")
};

const ROUTE_PREFIX_PRELOADERS: Array<{
  prefix: string;
  preload: () => Promise<unknown>;
}> = [
  { prefix: "/explore", preload: pageLoaders.explore },
  { prefix: "/products", preload: pageLoaders.products },
  { prefix: "/offers", preload: pageLoaders.offers },
  { prefix: "/compare", preload: pageLoaders.compare },
  { prefix: "/receipts", preload: pageLoaders.receipts },
  { prefix: "/quality", preload: pageLoaders.quality },
  { prefix: "/connectors", preload: pageLoaders.connectors },
  { prefix: "/sources", preload: pageLoaders.sources },
  { prefix: "/imports/manual", preload: pageLoaders.manualImport },
  { prefix: "/imports/ocr", preload: pageLoaders.documentsUpload },
  { prefix: "/budget", preload: pageLoaders.budget },
  { prefix: "/bills", preload: pageLoaders.bills },
  { prefix: "/patterns", preload: pageLoaders.patterns },
  { prefix: "/transactions", preload: pageLoaders.transactions },
  { prefix: "/documents/upload", preload: pageLoaders.documentsUpload },
  { prefix: "/review-queue", preload: pageLoaders.reviewQueue },
  { prefix: "/automations", preload: pageLoaders.automations },
  { prefix: "/automation-inbox", preload: pageLoaders.automationInbox },
  { prefix: "/chat", preload: pageLoaders.chat },
  { prefix: "/reliability", preload: pageLoaders.reliability },
  { prefix: "/settings/ai", preload: pageLoaders.aiSettings },
  { prefix: "/settings/users", preload: pageLoaders.usersSettings },
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
