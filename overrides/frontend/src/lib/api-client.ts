import { z } from "zod";

import { ApiDomainError, ApiTransportError } from "@/lib/api-errors";
import type { ApiWarning } from "@/lib/api-messages";
import { emitApiWarnings } from "@/lib/api-warnings";
import { parseEnvelopeResult } from "@/lib/envelope";
import { getRequestScopeQueryParam } from "@/lib/request-scope";

const API_BASE = import.meta.env.VITE_DASHBOARD_API_BASE || window.location.origin;
const DEFAULT_DB = import.meta.env.VITE_DASHBOARD_DB || "";
const OPTIONAL_API_KEY = import.meta.env.VITE_OPENCLAW_API_KEY || "";

type QueryParamValue = string | number | boolean | undefined | null;

type RequestOptions<T> = {
  path: string;
  query?: Record<string, QueryParamValue>;
  init?: RequestInit;
  schema: z.ZodType<T>;
};

type ApiResultWithWarnings<T> = {
  result: T;
  warnings: ApiWarning[];
};

function buildUrl(path: string, query?: Record<string, QueryParamValue>): URL {
  const url = new URL(path, API_BASE);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (key === "scope") {
        continue;
      }
      if (value !== undefined && value !== null && String(value).length > 0) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  const scopeParam = getRequestScopeQueryParam();
  if (scopeParam !== undefined) {
    url.searchParams.set("scope", scopeParam);
  }
  if (DEFAULT_DB) {
    url.searchParams.set("db", DEFAULT_DB);
  }
  return url;
}

function mergeHeaders(headers?: HeadersInit): Headers {
  const merged = new Headers(headers);
  if (OPTIONAL_API_KEY && !merged.has("X-API-Key")) {
    merged.set("X-API-Key", OPTIONAL_API_KEY);
  }
  return merged;
}

async function parseDomainErrorFromResponse<T>(
  response: Response,
  schema: z.ZodType<T>
): Promise<ApiDomainError | null> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    return null;
  }

  try {
    parseEnvelopeResult(payload, schema);
  } catch (error) {
    if (error instanceof ApiDomainError) {
      emitApiWarnings(error.warnings);
      return error;
    }
  }

  return null;
}

async function request<T>({ path, query, init, schema }: RequestOptions<T>): Promise<{ result: T; warnings: ApiWarning[] }> {
  const url = buildUrl(path, query);
  const response = await fetch(url.toString(), {
    credentials: "include",
    ...init,
    headers: mergeHeaders(init?.headers)
  });

  if (!response.ok) {
    const domainError = await parseDomainErrorFromResponse(response, schema);
    if (domainError) {
      throw domainError;
    }
    throw new ApiTransportError(response.status, `Request failed with status ${response.status}`);
  }

  const payload = await response.json();
  try {
    const parsed = parseEnvelopeResult(payload, schema);
    emitApiWarnings(parsed.warnings);
    return parsed;
  } catch (error) {
    if (error instanceof ApiDomainError) {
      emitApiWarnings(error.warnings);
    }
    throw error;
  }
}

export const apiClient = {
  buildUrl,
  async getWithWarnings<T>(
    path: string,
    schema: z.ZodType<T>,
    query?: Record<string, QueryParamValue>
  ): Promise<ApiResultWithWarnings<T>> {
    return request({ path, query, schema });
  },
  async get<T>(path: string, schema: z.ZodType<T>, query?: Record<string, QueryParamValue>): Promise<T> {
    const { result } = await request({ path, query, schema });
    return result;
  },
  async patch<T, B = unknown>(path: string, schema: z.ZodType<T>, body: B): Promise<T> {
    const { result } = await request({
      path,
      schema,
      init: {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }
    });
    return result;
  },
  async post<T, B = unknown>(path: string, schema: z.ZodType<T>, body?: B): Promise<T> {
    const { result } = await request({
      path,
      schema,
      init: {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body)
      }
    });
    return result;
  },
  async postForm<T>(path: string, schema: z.ZodType<T>, body: FormData): Promise<T> {
    const { result } = await request({
      path,
      schema,
      init: {
        method: "POST",
        body
      }
    });
    return result;
  },
  async delete<T>(path: string, schema: z.ZodType<T>): Promise<T> {
    const { result } = await request({
      path,
      schema,
      init: { method: "DELETE" }
    });
    return result;
  }
};
