import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { initRendererTelemetry } from "./diagnostics/sentry-renderer";
import { DesktopI18nProvider } from "./i18n";
import "./styles.css";

void initRendererTelemetry();

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DesktopI18nProvider>
      <App />
    </DesktopI18nProvider>
  </React.StrictMode>
);
