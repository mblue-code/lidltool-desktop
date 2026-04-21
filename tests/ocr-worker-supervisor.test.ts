import { afterEach, beforeEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import type { ChildProcessWithoutNullStreams } from "node:child_process";
import { OcrWorkerSupervisor } from "../src/main/ocr-worker-supervisor.ts";

class FakeChildProcess extends EventEmitter {
  stdout = new EventEmitter();
  stderr = new EventEmitter();
  killedSignals: string[] = [];

  kill(signal: string): boolean {
    this.killedSignals.push(signal);
    return true;
  }
}

describe("OcrWorkerSupervisor", () => {
  let logs: Array<{ stream: "stdout" | "stderr"; line: string; source: "ocr" }>;

  beforeEach(() => {
    logs = [];
  });

  afterEach(() => {
    logs = [];
  });

  it("starts the worker once and reuses the running process", async () => {
    const fakeProcess = new FakeChildProcess();
    let spawnCount = 0;
    const supervisor = new OcrWorkerSupervisor({
      buildLaunchSpec: async () => ({
        command: "python3",
        args: ["-m", "lidltool.ingest.jobs"],
        env: {},
        idleTimeoutSeconds: 600,
      }),
      emitLog: (payload) => logs.push(payload),
      spawnProcess: (() => {
        spawnCount += 1;
        return fakeProcess as unknown as ChildProcessWithoutNullStreams;
      }) as typeof import("node:child_process").spawn,
    });

    const first = await supervisor.ensureRunning();
    const second = await supervisor.ensureRunning();

    assert.equal(spawnCount, 1);
    assert.deepEqual(first, {
      running: true,
      started: true,
      idleTimeoutSeconds: 600,
    });
    assert.deepEqual(second, {
      running: true,
      started: false,
      idleTimeoutSeconds: 600,
    });
  });

  it("stops the worker process", async () => {
    const fakeProcess = new FakeChildProcess();
    const supervisor = new OcrWorkerSupervisor({
      buildLaunchSpec: async () => ({
        command: "python3",
        args: ["-m", "lidltool.ingest.jobs"],
        env: {},
        idleTimeoutSeconds: 600,
      }),
      emitLog: (payload) => logs.push(payload),
      spawnProcess: (() => fakeProcess as unknown as ChildProcessWithoutNullStreams) as typeof import("node:child_process").spawn,
    });

    await supervisor.ensureRunning();
    await supervisor.stop();

    assert.deepEqual(fakeProcess.killedSignals, ["SIGTERM", "SIGKILL"]);
  });

  it("surfaces a worker that exits during startup", async () => {
    const fakeProcess = new FakeChildProcess();
    const supervisor = new OcrWorkerSupervisor({
      buildLaunchSpec: async () => ({
        command: "python3",
        args: ["-m", "lidltool.ingest.jobs", "--idle-exit-after-s", "2"],
        env: {},
        idleTimeoutSeconds: 2,
      }),
      emitLog: (payload) => logs.push(payload),
      spawnProcess: (() => {
        queueMicrotask(() => {
          fakeProcess.emit("exit", 2, null);
        });
        return fakeProcess as unknown as ChildProcessWithoutNullStreams;
      }) as typeof import("node:child_process").spawn,
    });

    await assert.rejects(
      supervisor.ensureRunning(),
      /ocr worker exited during startup/
    );
  });
});
