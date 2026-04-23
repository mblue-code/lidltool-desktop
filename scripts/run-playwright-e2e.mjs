import { existsSync, renameSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const desktopDir = resolve(__dirname, "..");
const nestedFrontendNodeModules = resolve(desktopDir, "vendor", "frontend", "node_modules");
const parkedFrontendNodeModules = resolve(desktopDir, "vendor", "frontend", ".node_modules.playwright-hidden");
const legacyParkedFrontendNodeModules = resolve(desktopDir, "vendor", "frontend", ".node_modules_tmp");
const playwrightCli = resolve(desktopDir, "node_modules", "@playwright", "test", "cli.js");

let movedNodeModules = false;

function restoreLegacyParkedNodeModules() {
  if (existsSync(legacyParkedFrontendNodeModules) && !existsSync(nestedFrontendNodeModules)) {
    renameSync(legacyParkedFrontendNodeModules, nestedFrontendNodeModules);
  }
}

function hideNestedFrontendNodeModules() {
  restoreLegacyParkedNodeModules();
  if (!existsSync(nestedFrontendNodeModules)) {
    return;
  }
  if (existsSync(parkedFrontendNodeModules)) {
    throw new Error(
      `Cannot run desktop Playwright tests because the parked frontend dependency directory already exists: ${parkedFrontendNodeModules}`
    );
  }
  renameSync(nestedFrontendNodeModules, parkedFrontendNodeModules);
  movedNodeModules = true;
}

function restoreNestedFrontendNodeModules() {
  if (!movedNodeModules) {
    restoreLegacyParkedNodeModules();
    return;
  }
  if (existsSync(parkedFrontendNodeModules)) {
    renameSync(parkedFrontendNodeModules, nestedFrontendNodeModules);
  }
  restoreLegacyParkedNodeModules();
  movedNodeModules = false;
}

async function main() {
  hideNestedFrontendNodeModules();

  const child = spawn(process.execPath, [playwrightCli, ...process.argv.slice(2)], {
    cwd: desktopDir,
    env: process.env,
    stdio: "inherit"
  });

  const cleanupAndExit = (code) => {
    try {
      restoreNestedFrontendNodeModules();
    } catch (error) {
      console.error(`Failed to restore ${nestedFrontendNodeModules}: ${String(error)}`);
      process.exitCode = 1;
      return;
    }
    process.exit(code ?? 1);
  };

  child.on("error", (error) => {
    console.error(String(error));
    cleanupAndExit(1);
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      console.error(`Playwright exited due to signal ${signal}`);
      cleanupAndExit(1);
      return;
    }
    cleanupAndExit(code ?? 1);
  });
}

process.on("SIGINT", () => {
  restoreNestedFrontendNodeModules();
  process.exit(130);
});

process.on("SIGTERM", () => {
  restoreNestedFrontendNodeModules();
  process.exit(143);
});

void main();
