import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

const requiredEnv = [
  "GLITCHTIP_AUTH_TOKEN",
  "GLITCHTIP_ORG",
  "GLITCHTIP_PROJECT",
  "LIDLTOOL_DESKTOP_RELEASE"
];

const missing = requiredEnv.filter((name) => !process.env[name]?.trim());
if (missing.length > 0) {
  console.error(`Missing required source map upload environment variables: ${missing.join(", ")}`);
  process.exit(1);
}

if (!existsSync("out")) {
  console.error("Missing out/ build directory. Run npm run build before uploading source maps.");
  process.exit(1);
}

const sentryCliArgs = [
  "--yes",
  "@sentry/cli",
  "sourcemaps",
  "upload",
  "out",
  "--org",
  process.env.GLITCHTIP_ORG,
  "--project",
  process.env.GLITCHTIP_PROJECT,
  "--release",
  process.env.LIDLTOOL_DESKTOP_RELEASE
].filter(Boolean);

const env = {
  ...process.env,
  SENTRY_AUTH_TOKEN: process.env.GLITCHTIP_AUTH_TOKEN
};

console.log("Uploading source maps for configured release. Tokens are intentionally not printed.");
const result = spawnSync("npx", sentryCliArgs, {
  stdio: "inherit",
  env
});

if (result.status !== 0) {
  console.error("Source map upload failed.");
  process.exit(result.status ?? 1);
}
