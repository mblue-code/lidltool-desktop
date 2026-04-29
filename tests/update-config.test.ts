import test from "node:test";
import assert from "node:assert/strict";
import { resolveDesktopUpdateConfig } from "../src/main/updates/update-config.ts";

test("no update URL disables updates", () => {
  const config = resolveDesktopUpdateConfig({
    env: { OUTLAYS_DESKTOP_RELEASE_CHANNEL: "stable" },
    isPackaged: true,
    version: "1.0.0"
  });
  assert.equal(config.enabled, false);
  assert.equal(config.reason, "missing_update_base_url");
});

test("development updates require explicit override", () => {
  const config = resolveDesktopUpdateConfig({
    env: {
      OUTLAYS_DESKTOP_UPDATE_BASE_URL: "http://127.0.0.1:47821",
      OUTLAYS_DESKTOP_RELEASE_CHANNEL: "beta"
    },
    isPackaged: false,
    version: "0.2.0-beta.1"
  });
  assert.equal(config.enabled, false);
  assert.equal(config.reason, "dev_updates_disabled");
});

test("development updates can be enabled explicitly", () => {
  const config = resolveDesktopUpdateConfig({
    env: {
      OUTLAYS_DESKTOP_UPDATE_BASE_URL: "http://127.0.0.1:47821",
      OUTLAYS_DESKTOP_RELEASE_CHANNEL: "beta",
      OUTLAYS_DESKTOP_ALLOW_DEV_UPDATES: "1"
    },
    isPackaged: false,
    version: "0.2.0-beta.1"
  });
  assert.equal(config.enabled, true);
  assert.equal(config.channel, "beta");
});

test("beta channel resolves beta feed", () => {
  const config = resolveDesktopUpdateConfig({
    env: {
      OUTLAYS_DESKTOP_UPDATE_BASE_URL: "https://updates.example.invalid/outlays-desktop",
      OUTLAYS_DESKTOP_RELEASE_CHANNEL: "beta"
    },
    isPackaged: true,
    version: "0.2.0-beta.1"
  });
  assert.equal(config.channel, "beta");
  assert.equal(config.updateBaseUrl, "https://updates.example.invalid/outlays-desktop/beta");
});

test("production channel resolves stable feed", () => {
  const config = resolveDesktopUpdateConfig({
    env: {
      OUTLAYS_DESKTOP_UPDATE_BASE_URL: "https://updates.example.invalid/outlays-desktop",
      OUTLAYS_DESKTOP_RELEASE_CHANNEL: "production"
    },
    isPackaged: true,
    version: "1.0.0"
  });
  assert.equal(config.channel, "stable");
  assert.equal(config.updateBaseUrl, "https://updates.example.invalid/outlays-desktop/stable");
});

test("invalid channel falls back safely", () => {
  const config = resolveDesktopUpdateConfig({
    env: {
      OUTLAYS_DESKTOP_UPDATE_BASE_URL: "https://updates.example.invalid/outlays-desktop",
      OUTLAYS_DESKTOP_RELEASE_CHANNEL: "nightly"
    },
    isPackaged: true,
    version: "1.0.0"
  });
  assert.equal(config.channel, "stable");
});

test("legacy update environment variables remain supported", () => {
  const config = resolveDesktopUpdateConfig({
    env: {
      OUTLAYS_DESKTOP_UPDATE_BASE_URL: "https://updates.example.invalid/legacy-feed",
      OUTLAYS_DESKTOP_RELEASE_CHANNEL: "beta",
      OUTLAYS_DESKTOP_ALLOW_DEV_UPDATES: "1"
    },
    isPackaged: false,
    version: "0.2.0-beta.1"
  });
  assert.equal(config.enabled, true);
  assert.equal(config.channel, "beta");
  assert.equal(config.updateBaseUrl, "https://updates.example.invalid/legacy-feed/beta");
});
