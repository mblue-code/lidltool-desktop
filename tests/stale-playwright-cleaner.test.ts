import assert from "node:assert/strict";
import test from "node:test";

import {
  isOutlaysOwnedPlaywrightProcess,
  parseDarwinLinuxProcessList
} from "../src/main/stale-playwright-cleaner.ts";

const userDataDir = "/Users/tester/Library/Application Support/outlays-desktop";

test("matches old Playwright Chrome processes from temporary Playwright profiles", () => {
  const match = isOutlaysOwnedPlaywrightProcess(
    {
      pid: 7606,
      ageSeconds: 7200,
      command:
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/var/folders/x/T/playwright_chromiumdev_profile-X22v4Z --remote-debugging-pipe"
    },
    { userDataDir, staleAfterMs: 60 * 60 * 1000 }
  );

  assert.equal(match?.pid, 7606);
  assert.equal(match?.reason, "outlays_playwright_browser_stale");
});

test("matches old app-managed Amazon browser profiles", () => {
  const match = isOutlaysOwnedPlaywrightProcess(
    {
      pid: 123,
      ageSeconds: 13 * 60 * 60,
      command:
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/Users/tester/Library/Application Support/outlays-desktop/config/amazon_browser_profile"
    },
    { userDataDir, staleAfterMs: 60 * 60 * 1000, connectorStaleAfterMs: 12 * 60 * 60 * 1000 }
  );

  assert.equal(match?.pid, 123);
  assert.equal(match?.reason, "outlays_connector_browser_profile_stale");
});

test("does not match long-running connector browser profiles inside the connector grace period", () => {
  const match = isOutlaysOwnedPlaywrightProcess(
    {
      pid: 124,
      ageSeconds: 2 * 60 * 60,
      command:
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/Users/tester/Library/Application Support/outlays-desktop/config/amazon_browser_profile"
    },
    { userDataDir, staleAfterMs: 60 * 60 * 1000, connectorStaleAfterMs: 12 * 60 * 60 * 1000 }
  );

  assert.equal(match, null);
});

test("does not match regular Chrome", () => {
  const match = isOutlaysOwnedPlaywrightProcess(
    {
      pid: 456,
      ageSeconds: 7200,
      command: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    },
    { userDataDir, staleAfterMs: 60 * 60 * 1000 }
  );

  assert.equal(match, null);
});

test("does not match fresh app-owned browser processes", () => {
  const match = isOutlaysOwnedPlaywrightProcess(
    {
      pid: 789,
      ageSeconds: 120,
      command:
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/var/folders/x/T/playwright_chromiumdev_profile-fresh"
    },
    { userDataDir, staleAfterMs: 60 * 60 * 1000 }
  );

  assert.equal(match, null);
});

test("parses darwin/linux ps output with commands containing spaces", () => {
  const currentYear = new Date().getFullYear();
  const processes = parseDarwinLinuxProcessList(
    `  111 Mon Jan  1 00:00:00 ${currentYear} /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/tmp/profile\n` +
      `  222 Mon Jan  1 00:00:01 ${currentYear} node script.js\n`
  );

  assert.equal(processes.length, 2);
  assert.equal(processes[0].pid, 111);
  assert.equal(processes[0].command, "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/tmp/profile");
  assert.equal(typeof processes[0].ageSeconds, "number");
  assert.equal(processes[1].pid, 222);
  assert.equal(processes[1].command, "node script.js");
});
