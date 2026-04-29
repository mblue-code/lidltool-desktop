import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const desktopDir = resolve(__dirname, "..");
const buildDir = resolve(desktopDir, "build");
const smokeScript = resolve(desktopDir, "tests", "backend", "packaged_ocr_smoke.py");

const pythonExecutable =
  process.platform === "win32"
    ? resolve(buildDir, "backend-venv", "Scripts", "python.exe")
    : resolve(buildDir, "backend-venv", "bin", "python");

if (!existsSync(pythonExecutable)) {
  throw new Error(
    `Packaged backend Python runtime was not found at ${pythonExecutable}. Run 'npm run backend:prepare' and 'npm run build' first.`
  );
}

if (!existsSync(smokeScript)) {
  throw new Error(`Packaged OCR smoke script was not found at ${smokeScript}.`);
}

const result = spawnSync(pythonExecutable, [smokeScript], {
  cwd: desktopDir,
  stdio: "inherit",
  env: {
    ...process.env,
    OUTLAYS_DESKTOP_PACKAGED_SMOKE: "1"
  }
});

if (result.status !== 0) {
  throw new Error(`Packaged OCR smoke failed with exit code ${result.status ?? "unknown"}.`);
}
