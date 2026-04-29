#!/usr/bin/env node
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir, hostname, cpus, release as osRelease } from "node:os";
import net from "node:net";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const desktopDir = resolve(__dirname, "..");
const defaultOutputRoot = resolve(desktopDir, "output", "desktop-profiles");
const defaultElectronBinary = resolve(
  desktopDir,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "electron.cmd" : "electron"
);

const scenarioCatalog = {
  "idle-control-center": {
    description: "Launch the desktop shell and keep it idle.",
    intent: "idle",
    defaultDurationMs: 30_000,
    startupGraceMs: 10_000,
    sampleIntervalMs: 2_000,
    defaultLaunchCommand: existsSync(defaultElectronBinary) ? [defaultElectronBinary, "."] : ["npm", "run", "dev"]
  },
  "idle-full-app": {
    description: "Launch the desktop app in the full-app path and keep it idle.",
    intent: "idle",
    defaultDurationMs: 30_000,
    startupGraceMs: 10_000,
    sampleIntervalMs: 2_000,
    defaultLaunchCommand: existsSync(defaultElectronBinary) ? [defaultElectronBinary, "."] : ["npm", "run", "dev"]
  },
  sync: {
    description: "Profile a sync workflow while the desktop app is running.",
    intent: "active",
    defaultDurationMs: 90_000,
    startupGraceMs: 8_000,
    sampleIntervalMs: 1_500,
    defaultLaunchCommand: existsSync(defaultElectronBinary) ? [defaultElectronBinary, "."] : ["npm", "run", "dev"]
  },
  export: {
    description: "Profile an export workflow while the desktop app is running.",
    intent: "active",
    defaultDurationMs: 90_000,
    startupGraceMs: 8_000,
    sampleIntervalMs: 1_500,
    defaultLaunchCommand: existsSync(defaultElectronBinary) ? [defaultElectronBinary, "."] : ["npm", "run", "dev"]
  },
  backup: {
    description: "Profile a backup workflow while the desktop app is running.",
    intent: "active",
    defaultDurationMs: 90_000,
    startupGraceMs: 8_000,
    sampleIntervalMs: 1_500,
    defaultLaunchCommand: existsSync(defaultElectronBinary) ? [defaultElectronBinary, "."] : ["npm", "run", "dev"]
  }
};

function printUsage() {
  console.log(`Usage:
  node scripts/profile-desktop.mjs [options] [-- launch command args...]

Options:
  --scenario <name>           One of: ${Object.keys(scenarioCatalog).join(", ")}
  --output <path>             JSON output file path
  --duration-ms <ms>          Measurement window length after startup grace
  --interval-ms <ms>          Sampling interval
  --startup-grace-ms <ms>     Warm-up time before measurement begins
  --launch-cwd <path>         Working directory for the launch command
  --launch-shell <command>    Launch command executed through a shell
  --action-shell <command>    Optional follow-up command executed through a shell
  --action-delay-ms <ms>      Delay before the action command starts
  --profile-root <path>       Override the isolated profile root
  --env KEY=VALUE             Additional environment override; repeatable
  --keep-profile              Keep the generated profile root (default)
  --help                      Show this help text

Examples:
  node scripts/profile-desktop.mjs --scenario idle-control-center
  node scripts/profile-desktop.mjs --scenario sync --action-shell "npm run test:sync" -- npm run dev
`);
}

function parseInteger(value, name) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Invalid integer for ${name}: ${value}`);
  }
  return parsed;
}

function parseEnvAssignments(values) {
  const env = {};
  for (const value of values) {
    const eqIndex = value.indexOf("=");
    if (eqIndex <= 0) {
      throw new Error(`Invalid --env assignment. Expected KEY=VALUE, got: ${value}`);
    }
    const key = value.slice(0, eqIndex).trim();
    const raw = value.slice(eqIndex + 1);
    if (!key) {
      throw new Error(`Invalid --env assignment. Empty key in: ${value}`);
    }
    env[key] = raw;
  }
  return env;
}

function resolveDesktopLaunchEnv(profileRoot, extraEnv, apiPort) {
  const homeDir = join(profileRoot, "home");
  const tmpDir = join(profileRoot, "tmp");
  const configDir = join(homeDir, ".config", "lidltool");
  const documentsDir = join(homeDir, ".local", "share", "lidltool", "documents");

  mkdirSync(homeDir, { recursive: true });
  mkdirSync(tmpDir, { recursive: true });
  mkdirSync(configDir, { recursive: true });
  mkdirSync(documentsDir, { recursive: true });

  return {
    env: {
      ...process.env,
      CI: "1",
      HOME: homeDir,
      USERPROFILE: homeDir,
      APPDATA: join(homeDir, "AppData", "Roaming"),
      LOCALAPPDATA: join(homeDir, "AppData", "Local"),
      XDG_CONFIG_HOME: join(homeDir, ".config"),
      XDG_DATA_HOME: join(homeDir, ".local", "share"),
      TMPDIR: tmpDir,
      OUTLAYS_DESKTOP_USER_DATA_DIR: join(profileRoot, "electron-user-data"),
      OUTLAYS_DESKTOP_CONFIG_DIR: configDir,
      OUTLAYS_DESKTOP_DOCUMENT_STORAGE_PATH: documentsDir,
      OUTLAYS_DESKTOP_API_PORT: String(apiPort),
      ...extraEnv
    },
    homeDir,
    tmpDir,
    configDir,
    documentsDir
  };
}

function allocateFreePort() {
  return new Promise((resolvePort, rejectPort) => {
    const server = net.createServer();
    server.once("error", rejectPort);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close((error) => rejectPort(error ?? new Error("Failed to allocate a port.")));
        return;
      }
      const { port } = address;
      server.close((error) => {
        if (error) {
          rejectPort(error);
          return;
        }
        resolvePort(port);
      });
    });
  });
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function waitFor(predicate, { timeoutMs = 30_000, intervalMs = 250, errorMessage = "Timed out waiting for condition." } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) {
      return;
    }
    await sleep(intervalMs);
  }
  throw new Error(errorMessage);
}

function runSync(command, args, options = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf-8",
    maxBuffer: 10 * 1024 * 1024,
    ...options
  });
  if (result.error) {
    return {
      ok: false,
      code: null,
      signal: null,
      stdout: result.stdout ?? "",
      stderr: `${result.stderr ?? ""}\n${result.error.message}`.trim()
    };
  }
  return {
    ok: result.status === 0,
    code: typeof result.status === "number" ? result.status : null,
    signal: result.signal ?? null,
    stdout: result.stdout ?? "",
    stderr: result.stderr ?? ""
  };
}

function parseProcessTable() {
  const result = runSync("ps", ["-axo", "pid=,ppid=,rss=,%cpu=,command="]);
  if (!result.ok && !result.stdout.trim()) {
    return {
      ok: false,
      error: result.stderr || "ps did not return a process table.",
      processes: []
    };
  }

  const processes = [];
  for (const rawLine of result.stdout.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }
    const match = /^(\d+)\s+(\d+)\s+(\d+)\s+([0-9.]+)\s+(.*)$/.exec(line);
    if (!match) {
      continue;
    }
    const pid = Number.parseInt(match[1], 10);
    const ppid = Number.parseInt(match[2], 10);
    const rssKib = Number.parseInt(match[3], 10);
    const cpuPercent = Number.parseFloat(match[4]);
    processes.push({
      pid,
      ppid,
      rssKib: Number.isFinite(rssKib) ? rssKib : null,
      rssBytes: Number.isFinite(rssKib) ? rssKib * 1024 : null,
      cpuPercent: Number.isFinite(cpuPercent) ? cpuPercent : null,
      command: match[5]
    });
  }

  return {
    ok: true,
    error: null,
    processes
  };
}

function formatMegabytes(bytes) {
  if (!Number.isFinite(bytes) || bytes == null) {
    return "unknown";
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function parseByteSuffix(text) {
  const normalized = String(text).trim().replace(/,/g, "");
  const match = /^([0-9.]+)\s*([KMGTPE]?)(?:i?B)?$/i.exec(normalized);
  if (!match) {
    const numeric = Number.parseFloat(normalized);
    return Number.isFinite(numeric) ? numeric : null;
  }
  const value = Number.parseFloat(match[1]);
  if (!Number.isFinite(value)) {
    return null;
  }
  const suffix = match[2].toUpperCase();
  const multipliers = {
    "": 1,
    K: 1024,
    M: 1024 ** 2,
    G: 1024 ** 3,
    T: 1024 ** 4,
    P: 1024 ** 5,
    E: 1024 ** 6
  };
  return Math.round(value * (multipliers[suffix] ?? 1));
}

function collectVmmapFootprint(pid) {
  if (process.platform !== "darwin") {
    return { available: false, bytes: null, error: "vmmap is only available on macOS." };
  }
  const result = runSync("vmmap", ["-summary", String(pid)]);
  if (!result.ok && !result.stdout.trim()) {
    return { available: false, bytes: null, error: result.stderr || `vmmap failed for pid ${pid}` };
  }

  const lines = `${result.stdout}\n${result.stderr}`.split(/\r?\n/);
  for (const line of lines) {
    const match = /Physical footprint(?: \(peak\))?:\s*([0-9.,]+)\s*([KMGTPE]?)(?:i?B)?/i.exec(line);
    if (!match) {
      continue;
    }
    const bytes = parseByteSuffix(`${match[1]}${match[2]}`);
    if (Number.isFinite(bytes)) {
      return { available: true, bytes, error: null };
    }
  }
  return { available: false, bytes: null, error: `Could not parse vmmap footprint for pid ${pid}` };
}

function collectTopPower(pid) {
  if (process.platform !== "darwin") {
    return { available: false, value: null, error: "top POWER is only available on macOS." };
  }
  const result = runSync("top", ["-l", "1", "-pid", String(pid), "-stats", "pid,command,cpu,rsize,power"]);
  if (!result.ok && !result.stdout.trim()) {
    return { available: false, value: null, error: result.stderr || `top failed for pid ${pid}` };
  }

  for (const rawLine of result.stdout.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || !/^\d+/.test(line)) {
      continue;
    }
    const tokens = line.split(/\s+/);
    if (Number.parseInt(tokens[0], 10) !== pid) {
      continue;
    }
    const lastToken = tokens[tokens.length - 1];
    const value = Number.parseFloat(lastToken.replace(/%$/, ""));
    if (Number.isFinite(value)) {
      return { available: true, value, error: null };
    }
  }

  return { available: false, value: null, error: `Could not parse top POWER for pid ${pid}` };
}

function buildProcessForest(processes, trackedPids) {
  const byPid = new Map();
  const childrenByPid = new Map();
  for (const processInfo of processes) {
    byPid.set(processInfo.pid, processInfo);
    if (!childrenByPid.has(processInfo.ppid)) {
      childrenByPid.set(processInfo.ppid, []);
    }
    childrenByPid.get(processInfo.ppid).push(processInfo.pid);
  }
  for (const children of childrenByPid.values()) {
    children.sort((left, right) => left - right);
  }

  const trackedAlive = [...trackedPids]
    .filter((pid) => byPid.has(pid))
    .sort((left, right) => left - right);
  const trackedAliveSet = new Set(trackedAlive);
  const roots = trackedAlive.filter((pid) => !trackedAliveSet.has(byPid.get(pid).ppid));

  const visited = new Set();
  const buildNode = (pid, depth) => {
    const info = byPid.get(pid);
    if (!info || visited.has(pid)) {
      return null;
    }
    visited.add(pid);
    const childNodes = [];
    for (const childPid of childrenByPid.get(pid) ?? []) {
      if (!trackedPids.has(childPid)) {
        continue;
      }
      const node = buildNode(childPid, depth + 1);
      if (node) {
        childNodes.push(node);
      }
    }
    childNodes.sort((left, right) => left.pid - right.pid);
    return {
      pid: info.pid,
      ppid: info.ppid,
      depth,
      command: info.command,
      rssBytes: info.rssBytes,
      cpuPercent: info.cpuPercent,
      physicalFootprintBytes: null,
      topPower: null,
      children: childNodes
    };
  };

  const forest = [];
  for (const pid of roots) {
    const node = buildNode(pid, 0);
    if (node) {
      forest.push(node);
    }
  }

  return { byPid, childrenByPid, forest, trackedAlive };
}

function annotateForestWithCollectors(forest, collectorMap) {
  const visit = (node) => {
    const collector = collectorMap.get(node.pid);
    if (collector) {
      node.physicalFootprintBytes = collector.physicalFootprintBytes;
      node.topPower = collector.topPower;
    }
    for (const child of node.children) {
      visit(child);
    }
  };
  for (const node of forest) {
    visit(node);
  }
}

function flattenForest(forest) {
  const flat = [];
  const visit = (node) => {
    flat.push({
      pid: node.pid,
      ppid: node.ppid,
      depth: node.depth,
      command: node.command,
      rssBytes: node.rssBytes,
      cpuPercent: node.cpuPercent,
      physicalFootprintBytes: node.physicalFootprintBytes,
      topPower: node.topPower,
      childCount: node.children.length
    });
    for (const child of node.children) {
      visit(child);
    }
  };
  for (const node of forest) {
    visit(node);
  }
  return flat;
}

function sumFinite(values) {
  let total = 0;
  let count = 0;
  for (const value of values) {
    if (!Number.isFinite(value) || value == null) {
      continue;
    }
    total += value;
    count += 1;
  }
  return { total, count };
}

async function sampleTree({ trackedPids, topPidLimit }) {
  const table = parseProcessTable();
  if (!table.ok) {
    return {
      ok: false,
      error: table.error,
      sample: null
    };
  }

  const byPid = new Map(table.processes.map((proc) => [proc.pid, proc]));
  let grew = true;
  while (grew) {
    grew = false;
    for (const proc of table.processes) {
      if (!trackedPids.has(proc.ppid)) {
        continue;
      }
      if (!trackedPids.has(proc.pid)) {
        trackedPids.add(proc.pid);
        grew = true;
      }
    }
  }

  const { forest, trackedAlive } = buildProcessForest(table.processes, trackedPids);
  const trackedAliveSet = new Set(trackedAlive);
  const collectedPids = [...trackedAliveSet].sort((left, right) => left - right);
  const candidates = collectedPids
    .map((pid) => byPid.get(pid))
    .filter(Boolean)
    .sort((left, right) => {
      const leftRss = left.rssBytes ?? 0;
      const rightRss = right.rssBytes ?? 0;
      if (rightRss !== leftRss) {
        return rightRss - leftRss;
      }
      return left.pid - right.pid;
    });

  const selectedForCollectors = [];
  for (const proc of candidates) {
    if (selectedForCollectors.length >= topPidLimit) {
      break;
    }
    selectedForCollectors.push(proc.pid);
  }

  const collectorMap = new Map();
  for (const pid of selectedForCollectors) {
    collectorMap.set(pid, {
      physicalFootprintBytes: collectVmmapFootprint(pid).bytes,
      topPower: collectTopPower(pid).value
    });
  }

  annotateForestWithCollectors(forest, collectorMap);
  const flat = flattenForest(forest);
  const physicalFootprintValues = [];
  const powerValues = [];
  for (const node of flat) {
    if (Number.isFinite(node.physicalFootprintBytes)) {
      physicalFootprintValues.push(node.physicalFootprintBytes);
    }
    if (Number.isFinite(node.topPower)) {
      powerValues.push(node.topPower);
    }
  }
  const rssValues = flat.map((node) => node.rssBytes).filter((value) => Number.isFinite(value));
  const cpuValues = flat.map((node) => node.cpuPercent).filter((value) => Number.isFinite(value));

  const physicalFootprint = sumFinite(physicalFootprintValues);
  const power = sumFinite(powerValues);
  const rss = sumFinite(rssValues);
  const cpu = sumFinite(cpuValues);

  return {
    ok: true,
    error: null,
    sample: {
      processCount: flat.length,
      trackedProcessCount: trackedAlive.length,
      totalRssBytes: rss.total,
      totalRssCount: rss.count,
      totalCpuPercent: cpu.total,
      totalCpuCount: cpu.count,
      totalPhysicalFootprintBytes: physicalFootprint.total,
      physicalFootprintSampledCount: physicalFootprint.count,
      totalPower: power.total,
      powerSampledCount: power.count,
      rootForest: forest,
      processes: flat
    }
  };
}

function normalizeScenario(name) {
  const scenario = scenarioCatalog[name];
  if (!scenario) {
    throw new Error(`Unknown scenario '${name}'. Expected one of: ${Object.keys(scenarioCatalog).join(", ")}`);
  }
  return { name, ...scenario };
}

function parseArgs(argv) {
  const args = {
    scenario: "idle-control-center",
    output: null,
    durationMs: null,
    intervalMs: null,
    startupGraceMs: null,
    launchCwd: desktopDir,
    launchShell: null,
    actionShell: null,
    actionDelayMs: null,
    profileRoot: null,
    keepProfile: true,
    envAssignments: [],
    launchCommand: null,
    help: false
  };

  const launchSplit = argv.indexOf("--");
  const optionArgs = launchSplit === -1 ? argv : argv.slice(0, launchSplit);
  const rawLaunchArgs = launchSplit === -1 ? [] : argv.slice(launchSplit + 1);

  for (let index = 0; index < optionArgs.length; index += 1) {
    const token = optionArgs[index];
    if (token === "--help" || token === "-h") {
      args.help = true;
      continue;
    }
    if (token === "--scenario") {
      args.scenario = optionArgs[++index];
      continue;
    }
    if (token === "--output") {
      args.output = optionArgs[++index];
      continue;
    }
    if (token === "--duration-ms") {
      args.durationMs = parseInteger(optionArgs[++index], "--duration-ms");
      continue;
    }
    if (token === "--interval-ms") {
      args.intervalMs = parseInteger(optionArgs[++index], "--interval-ms");
      continue;
    }
    if (token === "--startup-grace-ms") {
      args.startupGraceMs = parseInteger(optionArgs[++index], "--startup-grace-ms");
      continue;
    }
    if (token === "--launch-cwd") {
      args.launchCwd = resolve(optionArgs[++index]);
      continue;
    }
    if (token === "--launch-shell") {
      args.launchShell = optionArgs[++index];
      continue;
    }
    if (token === "--action-shell") {
      args.actionShell = optionArgs[++index];
      continue;
    }
    if (token === "--action-delay-ms") {
      args.actionDelayMs = parseInteger(optionArgs[++index], "--action-delay-ms");
      continue;
    }
    if (token === "--profile-root") {
      args.profileRoot = resolve(optionArgs[++index]);
      continue;
    }
    if (token === "--env") {
      args.envAssignments.push(optionArgs[++index]);
      continue;
    }
    if (token === "--keep-profile") {
      args.keepProfile = true;
      continue;
    }
    throw new Error(`Unknown argument: ${token}`);
  }

  if (rawLaunchArgs.length > 0) {
    args.launchCommand = rawLaunchArgs;
  }

  return args;
}

function createRunLayout(scenarioName, outputPath) {
  const timestamp = new Date().toISOString().replace(/[:]/g, "-").replace(/\..+$/, "Z");
  if (outputPath) {
    const resolvedOutputPath = resolve(outputPath);
    const runDir = dirname(resolvedOutputPath);
    mkdirSync(runDir, { recursive: true });
    return {
      runId: `${scenarioName}-${timestamp}`,
      runDir,
      outputPath: resolvedOutputPath
    };
  }

  mkdirSync(defaultOutputRoot, { recursive: true });
  const runDir = mkdtempSync(join(defaultOutputRoot, `${scenarioName}-`));
  return {
    runId: `${scenarioName}-${timestamp}`,
    runDir,
    outputPath: join(runDir, "profile.json")
  };
}

async function launchProcess(command, cwd, env, stdoutPath, stderrPath) {
  const child = spawn(command[0], command.slice(1), {
    cwd,
    env,
    stdio: ["ignore", "pipe", "pipe"]
  });

  const stdout = [];
  const stderr = [];
  child.stdout?.on("data", (chunk) => {
    stdout.push(chunk);
  });
  child.stderr?.on("data", (chunk) => {
    stderr.push(chunk);
  });

  const exitPromise = new Promise((resolveExit) => {
    child.once("exit", (code, signal) => {
      resolveExit({ code, signal });
    });
  });

  return {
    child,
    exitPromise,
    flushLogs: () => {
      if (stdoutPath) {
        writeFileSync(stdoutPath, Buffer.concat(stdout), { flag: "w" });
      }
      if (stderrPath) {
        writeFileSync(stderrPath, Buffer.concat(stderr), { flag: "w" });
      }
    }
  };
}

async function terminateProcessTree(rootPid, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  const sentSigterm = new Set();
  const sentSigkill = new Set();

  const collectKnownDescendants = () => {
    const table = parseProcessTable();
    if (!table.ok) {
      return [];
    }
    const byParent = new Map();
    for (const proc of table.processes) {
      if (!byParent.has(proc.ppid)) {
        byParent.set(proc.ppid, []);
      }
      byParent.get(proc.ppid).push(proc.pid);
    }
    const queue = [rootPid];
    const tracked = new Set([rootPid]);
    while (queue.length > 0) {
      const current = queue.shift();
      for (const childPid of byParent.get(current) ?? []) {
        if (tracked.has(childPid)) {
          continue;
        }
        tracked.add(childPid);
        queue.push(childPid);
      }
    }
    return [...tracked].sort((left, right) => right - left);
  };

  while (Date.now() < deadline) {
    const pids = collectKnownDescendants();
    if (pids.length === 0) {
      return;
    }
    for (const pid of pids) {
      if (!sentSigterm.has(pid)) {
        try {
          process.kill(pid, "SIGTERM");
          sentSigterm.add(pid);
        } catch {
          sentSigterm.add(pid);
        }
      }
    }
    await sleep(500);
  }

  const remaining = collectKnownDescendants();
  for (const pid of remaining) {
    if (!sentSigkill.has(pid)) {
      try {
        process.kill(pid, "SIGKILL");
        sentSigkill.add(pid);
      } catch {
        sentSigkill.add(pid);
      }
    }
  }
}

async function connectToDesktopPage(debugPort) {
  const { chromium } = await import("playwright");
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${debugPort}`);

  try {
    let targetPage = null;
    await waitFor(
      async () => {
        for (const context of browser.contexts()) {
          for (const page of context.pages()) {
            const url = page.url();
            if (url.startsWith("file:") || url.startsWith("http://127.0.0.1") || url.startsWith("http://localhost")) {
              targetPage = page;
              return true;
            }
          }
        }
        return false;
      },
      {
        timeoutMs: 30_000,
        errorMessage: `Could not find the desktop app page on remote debugging port ${debugPort}.`
      }
    );
    return { browser, page: targetPage };
  } catch (error) {
    await browser.close();
    throw error;
  }
}

async function prepareEnglishShellPage(page) {
  await page.waitForLoadState("domcontentloaded");
  const updated = await page.evaluate(() => {
    try {
      const previous = window.localStorage.getItem("desktop.shell.locale");
      window.localStorage.setItem("app.locale", "en");
      window.localStorage.setItem("desktop.shell.locale", "en");
      return previous !== "en";
    } catch {
      return false;
    }
  });
  if (updated) {
    await page.reload({ waitUntil: "domcontentloaded" });
  }
}

async function runBuiltInScenarioAction({ scenarioName, debugPort, profileRoot }) {
  if (!Number.isInteger(debugPort)) {
    return {
      kind: scenarioName,
      ok: false,
      detail: "Built-in scenario actions require a default Electron launch with remote debugging enabled."
    };
  }

  const { browser, page } = await connectToDesktopPage(debugPort);
  try {
    await prepareEnglishShellPage(page);
    await page.getByRole("heading", { name: "Local receipt sync, review, export, and backup." }).waitFor({ timeout: 30_000 });

    if (scenarioName === "idle-full-app") {
      await page.getByRole("button", { name: "Open main app" }).first().click();
      await page.waitForURL(/:\/\/(?:127\.0\.0\.1|localhost):\d+(?:\/|$|[?#])/, { timeout: 90_000 });
      await page.waitForLoadState("domcontentloaded");
      return { kind: scenarioName, ok: true, detail: "Opened the full-app route." };
    }
    return {
      kind: scenarioName,
      ok: true,
      detail: "No built-in action for this scenario. Use --action-shell to drive sync, export, or backup steps."
    };
  } finally {
    await browser.close();
  }
}

function summarizeSamples(samples) {
  const measurementSamples = samples.filter((sample) => sample.phase === "measurement");
  const relevant = measurementSamples.length > 0 ? measurementSamples : samples;
  if (relevant.length === 0) {
    return {
      sampleCount: 0,
      measurementSampleCount: 0,
      firstSampleAt: null,
      lastSampleAt: null,
      settled: null,
      peaks: null
    };
  }

  const peak = (selector) => {
    let winner = relevant[0];
    for (const sample of relevant.slice(1)) {
      if ((selector(sample) ?? -Infinity) > (selector(winner) ?? -Infinity)) {
        winner = sample;
      }
    }
    return winner;
  };

  const peakProcess = peak((sample) => sample.processCount);
  const peakRss = peak((sample) => sample.totalRssBytes);
  const peakCpu = peak((sample) => sample.totalCpuPercent);
  const peakPhysical = peak((sample) => sample.totalPhysicalFootprintBytes);
  const peakPower = peak((sample) => sample.totalPower);
  const settled = relevant.at(-1);

  return {
    sampleCount: samples.length,
    measurementSampleCount: measurementSamples.length,
    firstSampleAt: new Date(relevant[0].timestampMs).toISOString(),
    lastSampleAt: new Date(settled.timestampMs).toISOString(),
    settled: {
      timestamp: new Date(settled.timestampMs).toISOString(),
      processCount: settled.processCount,
      totalRssBytes: settled.totalRssBytes,
      totalCpuPercent: settled.totalCpuPercent,
      totalPhysicalFootprintBytes: settled.totalPhysicalFootprintBytes,
      physicalFootprintSampledCount: settled.physicalFootprintSampledCount,
      totalPower: settled.totalPower,
      powerSampledCount: settled.powerSampledCount
    },
    peaks: {
      processCount: {
        timestamp: new Date(peakProcess.timestampMs).toISOString(),
        value: peakProcess.processCount
      },
      totalRssBytes: {
        timestamp: new Date(peakRss.timestampMs).toISOString(),
        value: peakRss.totalRssBytes
      },
      totalCpuPercent: {
        timestamp: new Date(peakCpu.timestampMs).toISOString(),
        value: peakCpu.totalCpuPercent
      },
      totalPhysicalFootprintBytes: {
        timestamp: new Date(peakPhysical.timestampMs).toISOString(),
        value: peakPhysical.totalPhysicalFootprintBytes,
        sampledPidCount: peakPhysical.physicalFootprintSampledCount
      },
      totalPower: {
        timestamp: new Date(peakPower.timestampMs).toISOString(),
        value: peakPower.totalPower,
        sampledPidCount: peakPower.powerSampledCount
      }
    }
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    printUsage();
    return;
  }

  const scenario = normalizeScenario(args.scenario);
  const usingScenarioDefaultLaunch = !args.launchShell && !args.launchCommand;
  const debugPort = usingScenarioDefaultLaunch ? await allocateFreePort() : null;
  const launchCommand = args.launchShell
    ? ["/bin/sh", "-lc", args.launchShell]
    : args.launchCommand ?? [
        ...scenario.defaultLaunchCommand,
        ...(debugPort ? [`--remote-debugging-port=${debugPort}`] : [])
      ];
  const actionCommand = args.actionShell ? ["/bin/sh", "-lc", args.actionShell] : null;
  const layout = createRunLayout(scenario.name, args.output);
  const reportPath = layout.outputPath;
  const profileRoot = args.profileRoot ?? join(layout.runDir, "profile-root");
  mkdirSync(profileRoot, { recursive: true });
  mkdirSync(join(profileRoot, "electron-user-data"), { recursive: true });

  const apiPort = await allocateFreePort();
  const extraEnv = parseEnvAssignments(args.envAssignments);
  const { env } = resolveDesktopLaunchEnv(profileRoot, extraEnv, apiPort);

  const launchStdoutPath = join(layout.runDir, "launcher.stdout.log");
  const launchStderrPath = join(layout.runDir, "launcher.stderr.log");
  const actionStdoutPath = join(layout.runDir, "action.stdout.log");
  const actionStderrPath = join(layout.runDir, "action.stderr.log");

  const launched = await launchProcess(launchCommand, args.launchCwd, env, launchStdoutPath, launchStderrPath);
  const launchedAt = Date.now();
  const trackedPids = new Set([launched.child.pid]);

  const sampleIntervalMs = args.intervalMs ?? scenario.sampleIntervalMs;
  const startupGraceMs = args.startupGraceMs ?? scenario.startupGraceMs;
  const durationMs = args.durationMs ?? scenario.defaultDurationMs;
  const actionDelayMs = args.actionDelayMs ?? Math.max(1_500, Math.min(5_000, Math.floor(startupGraceMs / 2)));
  const runUntil = launchedAt + startupGraceMs + durationMs;
  const samples = [];
  let actionHandle = null;
  let actionStartedAt = null;
  let actionFinishedAt = null;
  let actionResult = null;
  let builtInActionStartedAt = null;
  let builtInActionFinishedAt = null;
  let builtInActionResult = null;
  const runErrors = [];

  let nextSampleAt = launchedAt;
  while (Date.now() < runUntil) {
    if (!actionHandle && actionCommand && Date.now() >= launchedAt + actionDelayMs) {
      actionStartedAt = Date.now();
      actionHandle = await launchProcess(actionCommand, args.launchCwd, env, actionStdoutPath, actionStderrPath);
      actionHandle.exitPromise.then((result) => {
        actionFinishedAt = Date.now();
        actionResult = result;
      });
    } else if (
      !actionCommand &&
      builtInActionResult === null &&
      (Date.now() >= launchedAt + actionDelayMs || Date.now() + sampleIntervalMs >= launchedAt + actionDelayMs) &&
      scenario.name !== "idle-control-center"
    ) {
      builtInActionStartedAt = Date.now();
      try {
        builtInActionResult = await runBuiltInScenarioAction({
          scenarioName: scenario.name,
          debugPort,
          profileRoot
        });
      } catch (error) {
        builtInActionResult = {
          kind: scenario.name,
          ok: false,
          detail: error instanceof Error ? error.message : String(error)
        };
        runErrors.push({
          timestampMs: Date.now(),
          kind: "scenario-action",
          message: builtInActionResult.detail
        });
      } finally {
        builtInActionFinishedAt = Date.now();
      }
    }

    const sampleResult = await sampleTree({ trackedPids, topPidLimit: 12 });
    if (sampleResult.ok && sampleResult.sample) {
      samples.push({
        timestampMs: Date.now(),
        elapsedMs: Date.now() - launchedAt,
        phase: Date.now() - launchedAt < startupGraceMs ? "startup" : "measurement",
        ...sampleResult.sample
      });
    } else {
      runErrors.push({
        timestampMs: Date.now(),
        kind: "sample",
        message: sampleResult.error
      });
    }

    const sleepFor = Math.max(0, nextSampleAt + sampleIntervalMs - Date.now());
    nextSampleAt += sampleIntervalMs;
    if (sleepFor > 0) {
      await sleep(sleepFor);
    }
  }

  await terminateProcessTree(launched.child.pid);
  if (actionHandle) {
    await terminateProcessTree(actionHandle.child.pid);
  }

  const launchExit = await Promise.race([launched.exitPromise, sleep(2_000).then(() => null)]);
  if (launchExit) {
    const terminatedByProfiler =
      launchExit.signal === "SIGTERM" ||
      launchExit.signal === "SIGKILL" ||
      launchExit.code === 1;
    if (!terminatedByProfiler && typeof launchExit.code === "number" && launchExit.code !== 0) {
      runErrors.push({
        timestampMs: Date.now(),
        kind: "launcher-exit",
        message: `Launcher exited with code ${launchExit.code}${launchExit.signal ? ` and signal ${launchExit.signal}` : ""}`
      });
    }
  } else {
    runErrors.push({
      timestampMs: Date.now(),
      kind: "launcher-exit",
      message: "Launcher did not exit cleanly within the shutdown timeout."
    });
  }

  if (actionHandle && !actionResult) {
    actionResult = await Promise.race([actionHandle.exitPromise, sleep(2_000).then(() => null)]);
  }

  launched.flushLogs();
  if (actionHandle) {
    actionHandle.flushLogs();
  }

  const processCountSet = new Set();
  for (const sample of samples) {
    for (const proc of sample.processes) {
      processCountSet.add(proc.pid);
    }
  }

  const platform = {
    hostname: hostname(),
    platform: process.platform,
    arch: process.arch,
    release: osRelease(),
    nodeVersion: process.version,
    cpuModel: cpus()[0]?.model ?? null,
    cpuCount: cpus().length
  };

  const report = {
    schemaVersion: 1,
    generatedAt: new Date().toISOString(),
    run: {
      runId: layout.runId,
      scenario: scenario.name,
      scenarioDescription: scenario.description,
      intent: scenario.intent,
      outputPath: reportPath,
      runDir: layout.runDir,
      profileRoot,
      launchCwd: args.launchCwd,
      launchCommand,
      actionCommand,
      launchCommandSource: args.launchCommand ? "argv" : "scenario-default",
      actionCommandSource: args.actionShell ? "action-shell" : actionCommand ? "explicit" : "none",
      durationMs,
      startupGraceMs,
      sampleIntervalMs,
      actionDelayMs,
      keepProfile: args.keepProfile
    },
    machine: platform,
    launch: {
      pid: launched.child.pid,
      startedAt: new Date(launchedAt).toISOString(),
      env: {
        OUTLAYS_DESKTOP_USER_DATA_DIR: env.OUTLAYS_DESKTOP_USER_DATA_DIR,
        OUTLAYS_DESKTOP_API_PORT: env.OUTLAYS_DESKTOP_API_PORT,
        REMOTE_DEBUGGING_PORT: debugPort,
        HOME: env.HOME,
        TMPDIR: env.TMPDIR
      },
      exit: launchExit ?? null
    },
    action:
      actionHandle || builtInActionResult
        ? {
            pid: actionHandle?.child.pid ?? null,
            kind: actionHandle ? "shell" : "builtin",
            startedAt: new Date((actionStartedAt ?? builtInActionStartedAt) || launchedAt).toISOString(),
            finishedAt:
              actionFinishedAt || builtInActionFinishedAt
                ? new Date((actionFinishedAt ?? builtInActionFinishedAt) || launchedAt).toISOString()
                : null,
            exit: actionHandle ? actionResult : builtInActionResult
          }
        : null,
    capabilities: {
      vmmap: process.platform === "darwin",
      topPower: process.platform === "darwin"
    },
    samples,
    summary: {
      ...summarizeSamples(samples),
      uniquePidsObserved: processCountSet.size,
      errors: runErrors
    }
  };

  writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf-8");
  if (!args.keepProfile) {
    rmSync(profileRoot, { recursive: true, force: true });
  }
  console.log(`Wrote desktop profile report to ${reportPath}`);
  console.log(`Profile root: ${args.keepProfile ? profileRoot : `${profileRoot} (removed)`}`);
  console.log(`Samples captured: ${samples.length}`);
  if (runErrors.length > 0) {
    console.log(`Warnings: ${runErrors.length}`);
  }
  if (samples.length > 0) {
    const first = samples[0];
    const last = samples.at(-1);
    console.log(
      `Process count ${first.processCount} -> ${last.processCount}, RSS ${formatMegabytes(first.totalRssBytes)} -> ${formatMegabytes(last.totalRssBytes)}`
    );
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});
