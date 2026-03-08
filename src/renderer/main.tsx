import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { DesktopI18nProvider } from "./i18n";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DesktopI18nProvider>
      <App />
    </DesktopI18nProvider>
  </React.StrictMode>
);
