import { existsSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const backendSource = resolve(desktopDir, "vendor", "backend");
const venvDir = resolve(desktopDir, ".backend", "venv");
const vendoredBackendVenvDir = resolve(backendSource, ".venv");
const playwrightBrowsersPath = process.env.PLAYWRIGHT_BROWSERS_PATH?.trim() || "0";
const allowUnsupportedPython = process.env.LIDLTOOL_DESKTOP_ALLOW_UNSUPPORTED_PYTHON?.trim() === "1";

const MIN_SUPPORTED_PYTHON_MINOR = 11;
const MAX_RECOMMENDED_PYTHON_MINOR = 12;

const venvPython =
  process.platform === "win32"
    ? resolve(venvDir, "Scripts", "python.exe")
    : resolve(venvDir, "bin", "python");
const vendoredBackendPython =
  process.platform === "win32"
    ? resolve(vendoredBackendVenvDir, "Scripts", "python.exe")
    : resolve(vendoredBackendVenvDir, "bin", "python");

function parsePythonVersion(text) {
  const match = /Python\s+(\d+)\.(\d+)\.(\d+)/i.exec(text);
  if (!match) {
    return null;
  }
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3])
  };
}

function isSupportedPythonVersion(version) {
  if (!version) {
    return false;
  }
  if (version.major !== 3) {
    return false;
  }
  if (version.minor < MIN_SUPPORTED_PYTHON_MINOR) {
    return false;
  }
  if (version.minor > MAX_RECOMMENDED_PYTHON_MINOR) {
    return allowUnsupportedPython;
  }
  return true;
}

function readPythonVersion(command, args = []) {
  const res = spawnSync(command, [...args, "--version"], {
    encoding: "utf-8"
  });
  if (res.status !== 0) {
    return null;
  }
  return parsePythonVersion(`${res.stdout ?? ""}\n${res.stderr ?? ""}`.trim());
}

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
  const bundledCandidates = [vendoredBackendPython];
  for (const candidate of bundledCandidates) {
    const version = readPythonVersion(candidate);
    if (isSupportedPythonVersion(version)) {
      return { command: candidate, args: [] };
    }
  }

  if (process.platform === "win32") {
    for (const pythonSelector of ["-3.13", "-3.12", "-3.11"]) {
      const version = readPythonVersion("py", [pythonSelector]);
      if (isSupportedPythonVersion(version)) {
        return { command: "py", args: [pythonSelector] };
      }
    }
    if (allowUnsupportedPython) {
      for (const pythonSelector of ["-3.14", "-3"]) {
        const version = readPythonVersion("py", [pythonSelector]);
        if (isSupportedPythonVersion(version)) {
          return { command: "py", args: [pythonSelector] };
        }
      }
    }
  }

  for (const candidate of ["python3.13", "python3.12", "python3.11"]) {
    const version = readPythonVersion(candidate);
    if (isSupportedPythonVersion(version)) {
      return { command: candidate, args: [] };
    }
  }
  if (allowUnsupportedPython) {
    for (const candidate of ["python3.14", "python3", "python"]) {
      const version = readPythonVersion(candidate);
      if (isSupportedPythonVersion(version)) {
        return { command: candidate, args: [] };
      }
    }
  }

  throw new Error(
    "No suitable Python interpreter found. Install Python 3.11-3.12 for desktop backend preparation. " +
      "Set LIDLTOOL_DESKTOP_ALLOW_UNSUPPORTED_PYTHON=1 only if you intentionally want to bypass the stable OCR runtime constraint."
  );
}

function ensureCompatibleVirtualenv() {
  if (!existsSync(venvPython)) {
    return false;
  }

  const version = readPythonVersion(venvPython);
  if (isSupportedPythonVersion(version)) {
    return true;
  }

  rmSync(venvDir, { recursive: true, force: true });
  return false;
}

if (!existsSync(backendSource)) {
  throw new Error(`Vendored backend not found at ${backendSource}. Run 'npm run vendor:sync' first.`);
}

if (!ensureCompatibleVirtualenv()) {
  const hostPython = resolveHostPython();
  run(hostPython.command, [...hostPython.args, "-m", "venv", venvDir], { cwd: desktopDir });
}

run(venvPython, ["-m", "pip", "install", "--upgrade", "pip"], { cwd: desktopDir });
run(
  venvPython,
  ["-m", "pip", "install", "--upgrade", "--force-reinstall", backendSource],
  { cwd: desktopDir }
);
const rapidocrInstallArgs = ["-m", "pip", "install", "rapidocr_onnxruntime==1.4.4"];
if (allowUnsupportedPython) {
  rapidocrInstallArgs.splice(3, 0, "--ignore-requires-python");
}
run(venvPython, rapidocrInstallArgs, { cwd: desktopDir });
run(venvPython, ["-m", "playwright", "install", "chromium"], {
  cwd: desktopDir,
  env: {
    ...process.env,
    PLAYWRIGHT_BROWSERS_PATH: playwrightBrowsersPath
  }
});

console.log(`Prepared desktop backend runtime at ${venvDir}`);
