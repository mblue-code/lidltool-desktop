import { existsSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { summarizePreflightFindings } from "./lib/release-preflight.mjs";

function run(command, args) {
  const result = spawnSync(command, args, {
    encoding: "utf-8",
    stdio: ["ignore", "pipe", "pipe"]
  });
  return {
    ok: result.status === 0,
    stdout: result.stdout.trim(),
    stderr: result.stderr.trim()
  };
}

function stagedPaths() {
  const result = run("git", ["diff", "--cached", "--name-only"]);
  if (!result.ok) {
    throw new Error(result.stderr || "Could not inspect staged files.");
  }
  return result.stdout ? result.stdout.split(/\r?\n/).filter(Boolean) : [];
}

function relevantFiles(paths) {
  return paths
    .filter((path) => existsSync(path))
    .map((path) => ({
      path,
      content: readFileSync(path, "utf-8")
    }));
}

const channel = process.env.LIDLTOOL_DESKTOP_RELEASE_CHANNEL;
const packageJson = JSON.parse(readFileSync("package.json", "utf-8"));
const paths = stagedPaths();
const files = relevantFiles(paths);
const findings = summarizePreflightFindings({
  stagedPaths: paths,
  stagedFiles: files,
  channel,
  version: packageJson.version
});

console.log(`Release channel: ${channel || "(unset)"}`);
console.log(`Package version: ${packageJson.version}`);
console.log("Git status:");
console.log(run("git", ["status", "--short"]).stdout || "(clean)");

const typecheck = run("npm", ["run", "typecheck"]);
if (!typecheck.ok) {
  findings.push("npm run typecheck failed.");
  if (typecheck.stderr) {
    console.error(typecheck.stderr);
  }
}

if (!process.env.LIDLTOOL_DESKTOP_UPDATE_BASE_URL?.trim()) {
  findings.push("LIDLTOOL_DESKTOP_UPDATE_BASE_URL is required for release preflight.");
}

if (findings.length > 0) {
  console.error("\nRelease preflight failed:");
  for (const finding of findings) {
    console.error(`- ${finding}`);
  }
  process.exit(1);
}

console.log("Release preflight passed.");
