import { spawn } from "node:child_process";

import type { CommandLogEvent, CommandResult } from "@shared/contracts";

export function nowIso(): string {
  return new Date().toISOString();
}

export function splitLines(chunk: string): string[] {
  return chunk
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line.length > 0);
}

export async function waitUntilHealthy(baseUrl: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastErr: unknown;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/api/v1/health`);
      if (response.ok) {
        return;
      }
    } catch (error) {
      lastErr = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 350));
  }

  throw new Error(`Backend did not become healthy in ${timeoutMs}ms. Last error: ${String(lastErr)}`);
}

export async function runCommandWithLogs(args: {
  command: string;
  args: string[];
  env: NodeJS.ProcessEnv;
  source: CommandLogEvent["source"];
  emitLog: (payload: Omit<CommandLogEvent, "timestamp">) => void;
}): Promise<CommandResult> {
  return await new Promise<CommandResult>((resolve, reject) => {
    const proc = spawn(args.command, args.args, {
      env: args.env,
      stdio: "pipe"
    });

    let stdout = "";
    let stderr = "";

    proc.on("error", reject);

    proc.stdout.on("data", (chunk) => {
      const text = chunk.toString("utf-8");
      stdout += text;
      for (const line of splitLines(text)) {
        args.emitLog({ stream: "stdout", line, source: args.source });
      }
    });

    proc.stderr.on("data", (chunk) => {
      const text = chunk.toString("utf-8");
      stderr += text;
      for (const line of splitLines(text)) {
        args.emitLog({ stream: "stderr", line, source: args.source });
      }
    });

    proc.on("close", (code) => {
      resolve({
        ok: code === 0,
        command: args.command,
        args: args.args,
        exitCode: code,
        stdout: stdout.trim(),
        stderr: stderr.trim()
      });
    });
  });
}

export async function runCommandCapture(args: {
  command: string;
  args: string[];
  env: NodeJS.ProcessEnv;
}): Promise<CommandResult> {
  return await new Promise<CommandResult>((resolve, reject) => {
    const proc = spawn(args.command, args.args, {
      env: args.env,
      stdio: "pipe"
    });

    let stdout = "";
    let stderr = "";

    proc.on("error", reject);

    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf-8");
    });

    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf-8");
    });

    proc.on("close", (code) => {
      resolve({
        ok: code === 0,
        command: args.command,
        args: args.args,
        exitCode: code,
        stdout: stdout.trim(),
        stderr: stderr.trim()
      });
    });
  });
}
