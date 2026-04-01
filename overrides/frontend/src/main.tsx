import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";

import { pageLoaders } from "./app/page-loaders";
import { AppProviders } from "./app/providers";
import { AppErrorBoundary } from "./components/shared/AppErrorBoundary";
import { AuthGuard } from "./components/shared/AuthGuard";
import { RoutePendingFallback } from "./components/shared/RoutePendingFallback";
import {
  DesktopCapabilitiesProvider,
  DesktopRouteGate,
  loadDesktopCapabilities,
} from "./lib/desktop-capabilities";
import { LoginPage } from "./pages/LoginPage";
import { SetupPage } from "./pages/SetupPage";
import App from "./App";
import "./index.css";

const DashboardPage = lazy(() => pageLoaders.dashboard().then((module) => ({ default: module.DashboardPage })));
const ExplorePage = lazy(() => pageLoaders.explore().then((module) => ({ default: module.ExplorePage })));
const OffersPage = lazy(() => pageLoaders.offers().then((module) => ({ default: module.OffersPage })));
const ProductsPage = lazy(() => pageLoaders.products().then((module) => ({ default: module.ProductsPage })));
const ComparisonsPage = lazy(() =>
  pageLoaders.compare().then((module) => ({ default: module.ComparisonsPage }))
);
const DataQualityPage = lazy(() =>
  pageLoaders.quality().then((module) => ({ default: module.DataQualityPage }))
);
const ConnectorsPage = lazy(() =>
  pageLoaders.connectors().then((module) => ({ default: module.ConnectorsPage }))
);
const SourcesPage = lazy(() => pageLoaders.sources().then((module) => ({ default: module.SourcesPage })));
const ManualImportPage = lazy(() =>
  pageLoaders.manualImport().then((module) => ({ default: module.ManualImportPage }))
);
const BudgetPage = lazy(() => pageLoaders.budget().then((module) => ({ default: module.BudgetPage })));
const BillsPage = lazy(() => pageLoaders.bills().then((module) => ({ default: module.BillsPage })));
const PatternsPage = lazy(() => pageLoaders.patterns().then((module) => ({ default: module.PatternsPage })));
const TransactionsPage = lazy(() =>
  pageLoaders.transactions().then((module) => ({ default: module.TransactionsPage }))
);
const TransactionDetailPage = lazy(() =>
  pageLoaders.transactionDetail().then((module) => ({ default: module.TransactionDetailPage }))
);
const DocumentsUploadPage = lazy(() =>
  pageLoaders.documentsUpload().then((module) => ({ default: module.DocumentsUploadPage }))
);
const ReviewQueuePage = lazy(() => pageLoaders.reviewQueue().then((module) => ({ default: module.ReviewQueuePage })));
const AutomationsPage = lazy(() => pageLoaders.automations().then((module) => ({ default: module.AutomationsPage })));
const AutomationInboxPage = lazy(() =>
  pageLoaders.automationInbox().then((module) => ({ default: module.AutomationInboxPage }))
);
const ChatWorkspacePage = lazy(() =>
  pageLoaders.chat().then((module) => ({ default: module.ChatWorkspacePage }))
);
const ReliabilityPage = lazy(() => pageLoaders.reliability().then((module) => ({ default: module.ReliabilityPage })));
const UsersSettingsPage = lazy(() =>
  pageLoaders.usersSettings().then((module) => ({ default: module.UsersSettingsPage }))
);
const AISettingsPage = lazy(() =>
  pageLoaders.aiSettings().then((module) => ({ default: module.AISettingsPage }))
);

function TransactionsRedirect() {
  const location = useLocation();
  return <Navigate to={{ pathname: "/receipts", search: location.search, hash: location.hash }} replace />;
}

async function bootstrap() {
  const desktopCapabilities = await loadDesktopCapabilities();

  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <DesktopCapabilitiesProvider capabilities={desktopCapabilities}>
        <AppProviders>
          <AppErrorBoundary>
            <BrowserRouter>
              <Suspense fallback={<RoutePendingFallback />}>
                <Routes>
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/setup" element={<SetupPage />} />

                  <Route
                    path="/"
                    element={
                      <AuthGuard>
                        {(user) => <App user={user} />}
                      </AuthGuard>
                    }
                  >
                    <Route index element={<DashboardPage />} />
                    <Route path="explore" element={<ExplorePage />} />
                    <Route
                      path="offers"
                      element={
                        <DesktopRouteGate>
                          <OffersPage />
                        </DesktopRouteGate>
                      }
                    />
                    <Route path="products" element={<ProductsPage />} />
                    <Route path="compare" element={<ComparisonsPage />} />
                    <Route path="quality" element={<DataQualityPage />} />
                    <Route path="connectors" element={<ConnectorsPage />} />
                    <Route path="sources" element={<SourcesPage />} />
                    <Route path="add" element={<ManualImportPage />} />
                    <Route path="imports/manual" element={<ManualImportPage />} />
                    <Route path="imports/ocr" element={<DocumentsUploadPage />} />
                    <Route path="budget" element={<BudgetPage />} />
                    <Route path="bills" element={<BillsPage />} />
                    <Route path="patterns" element={<PatternsPage />} />
                    <Route path="receipts" element={<TransactionsPage />} />
                    <Route path="transactions" element={<TransactionsRedirect />} />
                    <Route path="transactions/:transactionId" element={<TransactionDetailPage />} />
                    <Route path="documents/upload" element={<DocumentsUploadPage />} />
                    <Route path="review-queue" element={<ReviewQueuePage />} />
                    <Route path="review-queue/:documentId" element={<ReviewQueuePage />} />
                    <Route
                      path="automations"
                      element={
                        <DesktopRouteGate>
                          <AutomationsPage />
                        </DesktopRouteGate>
                      }
                    />
                    <Route
                      path="automation-inbox"
                      element={
                        <DesktopRouteGate>
                          <AutomationInboxPage />
                        </DesktopRouteGate>
                      }
                    />
                    <Route path="chat" element={<ChatWorkspacePage />} />
                    <Route
                      path="reliability"
                      element={
                        <DesktopRouteGate>
                          <ReliabilityPage />
                        </DesktopRouteGate>
                      }
                    />
                    <Route path="settings/ai" element={<AISettingsPage />} />
                    <Route path="settings/users" element={<UsersSettingsPage />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Route>
                </Routes>
              </Suspense>
            </BrowserRouter>
          </AppErrorBoundary>
        </AppProviders>
      </DesktopCapabilitiesProvider>
    </React.StrictMode>
  );
}

void bootstrap();
