// Transport for the consistency API: base-URL bootstrap, JSON fetch, error
// mapping and the shared request pipeline. Kept separate from the schema
// guards so regression tests can inject a transport without the responses
// module pulling in browser-only machinery, and to keep both modules small.
//
// Only type-level contracts are imported from the shared api.ts; those
// imports are erased at runtime.
import type { ApiFailureKind, ApiResult } from "./api";

// The Vite-injected environment is read defensively so this module can also
// resolve outside Vite (unit tests), where import.meta.env is undefined.
const DEFAULT_PROD_API_BASE = "https://aicte-compliance-api-preview.onrender.com";

type EnvShape = Record<string, string | boolean | undefined>;
const ENV = ((import.meta as unknown as { env?: EnvShape }).env ?? {}) as EnvShape;

const RAW_API_BASE = ENV.VITE_API_BASE_URL
  ? String(ENV.VITE_API_BASE_URL)
  : ENV.DEV ? "" : DEFAULT_PROD_API_BASE;

export const API_BASE = RAW_API_BASE.trim().replace(/\/+$/, "");

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function fetchJson(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<{ response: Response; body: unknown; parseError: boolean }> {
  try {
    const response = await fetch(input, { ...init });
    const text = await response.text();
    if (!text.trim()) return { response, body: undefined, parseError: false };
    try {
      return { response, body: JSON.parse(text) as unknown, parseError: false };
    } catch {
      return { response, body: undefined, parseError: true };
    }
  } catch {
    return {
      response: new Response(null, { status: 0 }),
      body: undefined,
      parseError: true,
    } as { response: Response; body: unknown; parseError: boolean };
  }
}

// Mirrors the shared mapValidationErrors helper (duplicated for the same
// non-Vite import reason above).
function mapValidationErrors(
  body: unknown,
): Record<string, string> {
  if (!body || typeof body !== "object") return {};
  const detail = (body as Record<string, unknown>).detail;
  if (!Array.isArray(detail)) return {};

  const result: Record<string, string> = {};

  for (const entry of detail) {
    if (!entry || typeof entry !== "object") {
      result._unknown = String(entry);
      continue;
    }
    const e = entry as Record<string, unknown>;
    const msg = e.msg;
    if (typeof msg !== "string") continue;

    const loc = e.loc;
    if (!Array.isArray(loc) || loc.length === 0) {
      result._unknown = msg;
      continue;
    }
    const field = loc[loc.length - 1];
    if (typeof field !== "string") {
      result._unknown = msg;
      continue;
    }
    result[field] = msg;
  }
  return result;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

const REQUEST_TIMEOUT_MS = 15_000;

export interface ConsistencyRequestOptions {
  /** Overrides the JSON transport; used by regression tests. */
  fetchJson?: typeof fetchJson;
  /** Base-URL resolver; used by regression tests to inspect relative paths. */
  baseUrl?: (path: string) => string;
}

function errorResult(
  kind: ApiFailureKind,
  status: number,
  _server: string,
  raw?: unknown,
): ApiResult<never> {
  return { ok: false, kind, status, errors: { _server }, raw };
}

function applyParsedFieldErrors(
  status: number,
  body: unknown,
): ApiResult<never> | null {
  const errors = mapValidationErrors(body);
  if (status === 422 && Object.keys(errors).length > 0) {
    return { ok: false, kind: "validation", status, errors, raw: body };
  }
  return null;
}

function consistencyErrorMessage(status: number, body: unknown): string {
  if (isRecord(body) && typeof body.detail === "string") return body.detail;
  if (status === 401) return "Your session expired. Sign in again.";
  if (status === 403) return "You do not have access to these consistency records.";
  if (status === 404) return "The consistency record was not found.";
  return `Consistency service returned an error (${status}).`;
}

function isHttpStatusOkay(response: Response): boolean {
  return response.status >= 200 && response.status < 300;
}

async function consistencyRequest<T>(
  path: string,
  token: string,
  init: RequestInit,
  validate: (body: unknown) => body is T,
  invalidMessage: string,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<T>> {
  const doFetch = options?.fetchJson ?? fetchJson;
  const resolveBase = options?.baseUrl ?? apiUrl;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${token}`);
    if (init.body) headers.set("Content-Type", "application/json");

    const { response, body, parseError } = await doFetch(resolveBase(path), {
      ...init,
      headers,
      signal: controller.signal,
    });

    if (response.status === 204) return { ok: true, data: undefined as T };
    if (isHttpStatusOkay(response) && !parseError && validate(body)) {
      return { ok: true, data: body };
    }
    if (isHttpStatusOkay(response)) {
      return errorResult("invalid_response", response.status, invalidMessage, body);
    }
    const fieldErrors = applyParsedFieldErrors(response.status, body);
    if (fieldErrors) return fieldErrors;
    return errorResult(
      response.status === 422 ? "validation" : "server",
      response.status,
      consistencyErrorMessage(response.status, body),
      body,
    );
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === "AbortError";
    return errorResult(
      timedOut ? "timeout" : "network",
      0,
      timedOut
        ? "Consistency request timed out."
        : "Unable to reach the consistency service. Check your connection.",
    );
  } finally {
    clearTimeout(timeout);
  }
}

export { consistencyRequest };
