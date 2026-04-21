import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { OcrWorkerWakeResult } from "@shared/contracts";

interface OcrWorkerLaunchSpec {
  command: string;
  args: string[];
  env: NodeJS.ProcessEnv;
  idleTimeoutSeconds: number;
}

interface OcrWorkerSupervisorOptions {
  buildLaunchSpec: () => Promise<OcrWorkerLaunchSpec>;
  emitLog: (payload: { stream: "stdout" | "stderr"; line: string; source: "ocr" }) => void;
  spawnProcess?: typeof spawn;
}

function splitLines(chunk: string): string[] {
  return chunk
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line.length > 0);
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export class OcrWorkerSupervisor {
  private readonly buildLaunchSpec: OcrWorkerSupervisorOptions["buildLaunchSpec"];
  private readonly emitLog: OcrWorkerSupervisorOptions["emitLog"];
  private readonly spawnProcess: typeof spawn;
  private workerProcess: ChildProcessWithoutNullStreams | null = null;
  private idleTimeoutSeconds = 600;

  constructor(options: OcrWorkerSupervisorOptions) {
    this.buildLaunchSpec = options.buildLaunchSpec;
    this.emitLog = options.emitLog;
    this.spawnProcess = options.spawnProcess ?? spawn;
  }

  async ensureRunning(): Promise<OcrWorkerWakeResult> {
    if (this.workerProcess !== null) {
      return {
        running: true,
        started: false,
        idleTimeoutSeconds: this.idleTimeoutSeconds,
      };
    }

    const launch = await this.buildLaunchSpec();
    this.idleTimeoutSeconds = launch.idleTimeoutSeconds;
    const process = this.spawnProcess(launch.command, launch.args, {
      env: launch.env,
      stdio: "pipe",
    });
    this.workerProcess = process;

    let spawnError: Error | null = null;
    let earlyExit: { code: number | null; signal: NodeJS.Signals | null } | null = null;
    process.on("error", (error) => {
      spawnError = error;
      this.workerProcess = null;
      this.emitLog({
        stream: "stderr",
        line: `ocr worker spawn failed: ${String(error)}`,
        source: "ocr",
      });
    });
    process.on("exit", (code, signal) => {
      earlyExit = { code, signal };
      this.emitLog({
        stream: "stdout",
        line: `ocr worker exited code=${code ?? "null"} signal=${signal ?? "null"}`,
        source: "ocr",
      });
      if (this.workerProcess === process) {
        this.workerProcess = null;
      }
    });
    process.stdout.on("data", (chunk) => {
      for (const line of splitLines(chunk.toString("utf-8"))) {
        this.emitLog({ stream: "stdout", line, source: "ocr" });
      }
    });
    process.stderr.on("data", (chunk) => {
      for (const line of splitLines(chunk.toString("utf-8"))) {
        this.emitLog({ stream: "stderr", line, source: "ocr" });
      }
    });

    for (let attempt = 0; attempt < 10; attempt += 1) {
      if (spawnError) {
        throw spawnError;
      }
      const startupExitInfo: { code: number | null; signal: NodeJS.Signals | null } | null = earlyExit;
      if (this.workerProcess === null && startupExitInfo !== null) {
        const { code, signal } = startupExitInfo;
        throw new Error(
          `ocr worker exited during startup (code=${code ?? "null"}, signal=${signal ?? "null"})`
        );
      }
      await sleep(50);
    }

    return {
      running: this.workerProcess !== null,
      started: true,
      idleTimeoutSeconds: this.idleTimeoutSeconds,
    };
  }

  async stop(): Promise<void> {
    if (this.workerProcess === null) {
      return;
    }
    const process = this.workerProcess;
    process.kill("SIGTERM");
    await sleep(500);
    if (this.workerProcess === process) {
      process.kill("SIGKILL");
      this.workerProcess = null;
    }
  }
}
