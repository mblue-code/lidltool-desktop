import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { ensureManagedPlaywrightBrowsers } from "../src/main/runtime-backend-env.ts";
import type { CommandLogEvent, CommandResult } from "../src/shared/contracts.ts";

test("serializes concurrent managed Playwright browser installs for the same user data dir", async () => {
  const tempRoot = mkdtempSync(join(tmpdir(), "desktop-playwright-install-"));
  try {
    const userDataDir = join(tempRoot, "user-data");
    const pythonExecutable = join(tempRoot, ".backend", "venv", "bin", "python");
    mkdirSync(join(tempRoot, ".backend", "venv", "bin"), { recursive: true });
    writeFileSync(pythonExecutable, "");

    let installCount = 0;
    const logs: Array<Omit<CommandLogEvent, "timestamp">> = [];
    const runRawCommandCapture = async (
      _command: string,
      _commandArgs: string[],
      env: NodeJS.ProcessEnv
    ): Promise<CommandResult> => {
      installCount += 1;
      await new Promise((resolve) => setTimeout(resolve, 20));
      const browsersPath = String(env.PLAYWRIGHT_BROWSERS_PATH);
      mkdirSync(join(browsersPath, "chromium-1217"), { recursive: true });
      writeFileSync(join(browsersPath, "chromium-1217", "INSTALLATION_COMPLETE"), "");
      return {
        ok: true,
        command: _command,
        args: _commandArgs,
        exitCode: 0,
        stdout: "installed",
        stderr: ""
      };
    };

    const args = {
      command: join(tempRoot, ".backend", "venv", "bin", "lidltool"),
      userDataDir,
      pythonExecutable,
      isPathLike: () => true,
      emitLog: (payload: Omit<CommandLogEvent, "timestamp">) => logs.push(payload),
      runRawCommandCapture
    };

    const firstEnv: NodeJS.ProcessEnv = {};
    const secondEnv: NodeJS.ProcessEnv = {};
    await Promise.all([
      ensureManagedPlaywrightBrowsers({ ...args, env: firstEnv }),
      ensureManagedPlaywrightBrowsers({ ...args, env: secondEnv })
    ]);

    assert.equal(installCount, 1);
    assert.equal(firstEnv.PLAYWRIGHT_BROWSERS_PATH, join(userDataDir, "playwright-browsers"));
    assert.equal(secondEnv.PLAYWRIGHT_BROWSERS_PATH, join(userDataDir, "playwright-browsers"));
    assert.equal(logs.filter((entry) => entry.line.startsWith("Installing Playwright Chromium")).length, 1);
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});
