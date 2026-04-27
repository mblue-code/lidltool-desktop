import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { networkInterfaces, type NetworkInterfaceInfo } from "node:os";
import { URL } from "node:url";
import type {
  MobileBridgeInterface,
  MobileBridgeRouteDecision,
  MobileBridgeStatus,
  StartMobileBridgeRequest
} from "@shared/contracts";

const DEFAULT_BRIDGE_EXPIRES_IN_SECONDS = 600;
const MIN_BRIDGE_EXPIRES_IN_SECONDS = 60;
const MAX_BRIDGE_EXPIRES_IN_SECONDS = 600;
const HANDSHAKE_BODY_LIMIT_BYTES = 32 * 1024;
const JSON_BODY_LIMIT_BYTES = 64 * 1024;
const CAPTURE_BODY_LIMIT_BYTES = 25 * 1024 * 1024;

const REJECTED_INTERFACE_NAME_PATTERN =
  /(docker|bridge|br-|veth|vmnet|vbox|virtualbox|utun|tun|tap|tailscale|zerotier|wg|wireguard|llw|awdl)/i;

const ALLOWED_ROUTES: Record<string, ReadonlySet<string>> = {
  "POST /api/mobile-pair/v1/handshake": new Set(["POST"]),
  "POST /api/mobile-captures/v1": new Set(["POST"]),
  "GET /api/mobile-sync/v1/changes": new Set(["GET"]),
  "POST /api/mobile-sync/v1/manual-transactions": new Set(["POST"]),
  "GET /api/mobile-local/v1/health": new Set(["GET"])
};

type NetworkInterfaceMap = ReturnType<typeof networkInterfaces>;

interface ActiveBridge {
  server: Server;
  status: MobileBridgeStatus;
  stopTimer: NodeJS.Timeout | null;
}

export function isPrivateLanIpv4(address: string): boolean {
  const parts = address.split(".").map((part) => Number.parseInt(part, 10));
  if (parts.length !== 4 || parts.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
    return false;
  }
  const [a, b] = parts;
  if (a === 10) {
    return true;
  }
  if (a === 172 && b >= 16 && b <= 31) {
    return true;
  }
  if (a === 192 && b === 168) {
    return true;
  }
  if (a === 169 && b === 254) {
    return true;
  }
  return false;
}

export function isRejectedMobileInterfaceName(name: string): boolean {
  return REJECTED_INTERFACE_NAME_PATTERN.test(name);
}

export function isAllowedPrivateBridgeAddress(address: string): boolean {
  if (!address || address === "0.0.0.0" || address.startsWith("127.")) {
    return false;
  }
  return isPrivateLanIpv4(address);
}

export function normalizeRemoteAddress(address: string | undefined): string {
  if (!address) {
    return "";
  }
  if (address.startsWith("::ffff:")) {
    return address.slice("::ffff:".length);
  }
  return address;
}

export function isAllowedBridgeRemoteAddress(address: string | undefined): boolean {
  const normalized = normalizeRemoteAddress(address);
  return normalized === "127.0.0.1" || normalized === "::1" || isPrivateLanIpv4(normalized);
}

export function discoverPrivateMobileInterfaces(
  interfaces: NetworkInterfaceMap = networkInterfaces()
): MobileBridgeInterface[] {
  const candidates: MobileBridgeInterface[] = [];
  for (const [name, entries] of Object.entries(interfaces)) {
    if (!name || !entries || isRejectedMobileInterfaceName(name)) {
      continue;
    }
    for (const entry of entries as NetworkInterfaceInfo[]) {
      if (entry.family !== "IPv4" || entry.internal || !isAllowedPrivateBridgeAddress(entry.address)) {
        continue;
      }
      candidates.push({
        name,
        address: entry.address,
        family: "IPv4",
        cidr: entry.cidr ?? null,
        mac: entry.mac || null
      });
    }
  }
  return candidates.sort((left, right) => left.name.localeCompare(right.name) || left.address.localeCompare(right.address));
}

export function selectPrivateMobileInterface(
  requestedAddress?: string,
  interfaces: NetworkInterfaceMap = networkInterfaces()
): MobileBridgeInterface {
  const candidates = discoverPrivateMobileInterfaces(interfaces);
  if (requestedAddress) {
    const selected = candidates.find((candidate) => candidate.address === requestedAddress);
    if (!selected) {
      throw new Error("Selected address is not an allowed private LAN IPv4 interface.");
    }
    return selected;
  }
  const selected = candidates[0];
  if (!selected) {
    throw new Error("No private LAN IPv4 interface is available for local phone pairing.");
  }
  return selected;
}

export function decideMobileBridgeRoute(method: string | undefined, rawUrl: string | undefined): MobileBridgeRouteDecision {
  const normalizedMethod = (method || "GET").toUpperCase();
  const pathname = new URL(rawUrl || "/", "http://127.0.0.1").pathname;
  const key = `${normalizedMethod} ${pathname}`;
  const allowedMethods = ALLOWED_ROUTES[key];
  if (allowedMethods?.has(normalizedMethod)) {
    return {
      allowed: true,
      method: normalizedMethod,
      path: pathname,
      bodyLimitBytes: bodyLimitFor(normalizedMethod, pathname)
    };
  }
  return {
    allowed: false,
    method: normalizedMethod,
    path: pathname,
    bodyLimitBytes: 0
  };
}

function bodyLimitFor(method: string, path: string): number {
  if (method === "GET") {
    return 0;
  }
  if (path === "/api/mobile-captures/v1") {
    return CAPTURE_BODY_LIMIT_BYTES;
  }
  if (path === "/api/mobile-pair/v1/handshake") {
    return HANDSHAKE_BODY_LIMIT_BYTES;
  }
  return JSON_BODY_LIMIT_BYTES;
}

function clampBridgeExpiresInSeconds(value: number | undefined): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_BRIDGE_EXPIRES_IN_SECONDS;
  }
  return Math.max(MIN_BRIDGE_EXPIRES_IN_SECONDS, Math.min(Math.trunc(value ?? DEFAULT_BRIDGE_EXPIRES_IN_SECONDS), MAX_BRIDGE_EXPIRES_IN_SECONDS));
}

function writeJson(response: ServerResponse, statusCode: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body)
  });
  response.end(body);
}

async function readRequestBody(request: IncomingMessage, limitBytes: number): Promise<Buffer> {
  const chunks: Buffer[] = [];
  let total = 0;
  for await (const chunk of request) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    total += buffer.length;
    if (total > limitBytes) {
      throw new Error("request body too large");
    }
    chunks.push(buffer);
  }
  return Buffer.concat(chunks);
}

function forwardedHeaders(request: IncomingMessage, body: Buffer): Headers {
  const headers = new Headers();
  const contentType = request.headers["content-type"];
  const authorization = request.headers.authorization;
  const accept = request.headers.accept;
  if (typeof contentType === "string") {
    headers.set("Content-Type", contentType);
  }
  if (typeof authorization === "string") {
    headers.set("Authorization", authorization);
  }
  if (typeof accept === "string") {
    headers.set("Accept", accept);
  }
  headers.set("Content-Length", String(body.length));
  return headers;
}

export class MobileBridge {
  private active: ActiveBridge | null = null;
  private readonly backendBaseUrl: () => string;

  constructor(backendBaseUrl: () => string) {
    this.backendBaseUrl = backendBaseUrl;
  }

  getStatus(): MobileBridgeStatus {
    return this.active?.status ?? {
      running: false,
      endpointUrl: null,
      interface: null,
      startedAt: null,
      expiresAt: null,
      lastMobileRequestAt: null,
      lastMobileRequest: null
    };
  }

  async start(request: StartMobileBridgeRequest = {}): Promise<MobileBridgeStatus> {
    if (this.active) {
      return this.getStatus();
    }

    const selectedInterface = selectPrivateMobileInterface(request.address);
    const expiresInSeconds = clampBridgeExpiresInSeconds(request.expiresInSeconds);
    const startedAt = new Date();
    const expiresAt = new Date(startedAt.getTime() + expiresInSeconds * 1000);

    const server = createServer((incomingRequest, response) => {
      void this.handleRequest(incomingRequest, response);
    });

    await new Promise<void>((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, selectedInterface.address, () => {
        server.off("error", reject);
        resolve();
      });
    });

    const addressInfo = server.address();
    if (addressInfo === null || typeof addressInfo === "string") {
      server.close();
      throw new Error("Mobile bridge did not bind to an IPv4 port.");
    }

    const status: MobileBridgeStatus = {
      running: true,
      endpointUrl: `http://${selectedInterface.address}:${addressInfo.port}`,
      interface: selectedInterface,
      startedAt: startedAt.toISOString(),
      expiresAt: expiresAt.toISOString(),
      lastMobileRequestAt: null,
      lastMobileRequest: null
    };
    const stopTimer = setTimeout(() => {
      void this.stop();
    }, expiresAt.getTime() - Date.now());
    this.active = { server, status, stopTimer };
    return status;
  }

  async stop(): Promise<MobileBridgeStatus> {
    const active = this.active;
    if (!active) {
      return this.getStatus();
    }
    this.active = null;
    if (active.stopTimer) {
      clearTimeout(active.stopTimer);
    }
    await new Promise<void>((resolve) => active.server.close(() => resolve()));
    return this.getStatus();
  }

  private async handleRequest(request: IncomingMessage, response: ServerResponse): Promise<void> {
    const active = this.active;
    if (!active) {
      writeJson(response, 503, { ok: false, error: "mobile bridge is not running" });
      return;
    }

    const remoteAddress = normalizeRemoteAddress(request.socket.remoteAddress);
    const decision = decideMobileBridgeRoute(request.method, request.url);
    active.status.lastMobileRequestAt = new Date().toISOString();
    active.status.lastMobileRequest = {
      method: decision.method,
      path: decision.path,
      remoteAddress,
      statusCode: null,
      at: active.status.lastMobileRequestAt
    };

    if (!isAllowedBridgeRemoteAddress(remoteAddress)) {
      active.status.lastMobileRequest.statusCode = 403;
      writeJson(response, 403, { ok: false, error: "mobile bridge only accepts private local network clients" });
      return;
    }

    if (!decision.allowed) {
      active.status.lastMobileRequest.statusCode = 404;
      writeJson(response, 404, { ok: false, error: "route is not available on the mobile bridge" });
      return;
    }

    if (decision.path === "/api/mobile-local/v1/health") {
      active.status.lastMobileRequest.statusCode = 200;
      writeJson(response, 200, {
        ok: true,
        result: {
          status: "alive",
          bridge: "mobile-local",
          endpoint_url: active.status.endpointUrl,
          expires_at: active.status.expiresAt
        },
        warnings: [],
        error: null
      });
      return;
    }

    try {
      const body = decision.bodyLimitBytes > 0 ? await readRequestBody(request, decision.bodyLimitBytes) : Buffer.alloc(0);
      const target = new URL(request.url || "/", this.backendBaseUrl());
      const fetchBody = body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength) as ArrayBuffer;
      const proxied = await fetch(target, {
        method: decision.method,
        headers: forwardedHeaders(request, body),
        body: decision.method === "GET" ? undefined : fetchBody
      });
      const responseBody = Buffer.from(await proxied.arrayBuffer());
      const responseHeaders: Record<string, string> = {};
      const contentType = proxied.headers.get("content-type");
      if (contentType) {
        responseHeaders["Content-Type"] = contentType;
      }
      responseHeaders["Content-Length"] = String(responseBody.length);
      active.status.lastMobileRequest.statusCode = proxied.status;
      response.writeHead(proxied.status, responseHeaders);
      response.end(responseBody);
    } catch (error) {
      const message = error instanceof Error && error.message === "request body too large"
        ? "request body too large"
        : "mobile bridge proxy request failed";
      const statusCode = message === "request body too large" ? 413 : 502;
      active.status.lastMobileRequest.statusCode = statusCode;
      writeJson(response, statusCode, { ok: false, error: message });
    }
  }
}
