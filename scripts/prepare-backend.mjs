import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const backendSource = resolve(desktopDir, "vendor", "backend");
const venvDir = resolve(desktopDir, ".backend", "venv");
const playwrightBrowsersPath = process.env.PLAYWRIGHT_BROWSERS_PATH?.trim() || "0";

const venvPython =
  process.platform === "win32"
    ? resolve(venvDir, "Scripts", "python.exe")
    : resolve(venvDir, "bin", "python");

function run(command, args, opts = {}) {
  const res = spawnSync(command, args, {
    stdio: "inherit",
    ...opts
  });
  if (res.status !== 0) {
    throw new Error(`Command failed (${res.status}): ${command} ${args.join(" ")}`);
  }
}

function resolveHostPython() {
  if (process.platform === "win32") {
    const py = spawnSync("py", ["-3", "--version"], { stdio: "ignore" });
    if (py.status === 0) {
      return { command: "py", args: ["-3"] };
    }
  }

  for (const candidate of ["python3", "python"]) {
    const check = spawnSync(candidate, ["--version"], { stdio: "ignore" });
    if (check.status === 0) {
      return { command: candidate, args: [] };
    }
  }

  throw new Error("No suitable Python interpreter found. Install Python 3.11+ first.");
}

if (!existsSync(backendSource)) {
  throw new Error(`Vendored backend not found at ${backendSource}. Run 'npm run vendor:sync' first.`);
}

if (!existsSync(venvPython)) {
  const hostPython = resolveHostPython();
  run(hostPython.command, [...hostPython.args, "-m", "venv", venvDir], { cwd: desktopDir });
}

run(venvPython, ["-m", "pip", "install", "--upgrade", "pip"], { cwd: desktopDir });
run(venvPython, ["-m", "pip", "install", "-e", backendSource], { cwd: desktopDir });
run(venvPython, ["-m", "playwright", "install", "chromium"], {
  cwd: desktopDir,
  env: {
    ...process.env,
    PLAYWRIGHT_BROWSERS_PATH: playwrightBrowsersPath
  }
});

console.log(`Prepared desktop backend runtime at ${venvDir}`);
