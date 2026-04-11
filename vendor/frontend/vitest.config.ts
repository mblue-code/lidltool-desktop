import { configDefaults, defineConfig } from "vitest/config";

const maxWorkers = process.env.VITEST_MAX_WORKERS ?? (process.env.CI ? "50%" : "2");

export default defineConfig({
  resolve: {
    alias: {
      "@": "/src"
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    exclude: [...configDefaults.exclude, "e2e/**"],
    maxWorkers
  }
});
