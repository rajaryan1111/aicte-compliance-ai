// Typed client for the authenticated, tenant-scoped consistency API.
//
// Contracts follow docs/development/API_CONTRACT.md (/api/v1/consistency/*):
// every request carries the session's Bearer token, and every response is
// validated against the backend's ConsistencyCheckRead / ConsistencyFindingRead
// / ApplicationRead schemas before being handed to the UI.
//
// The transport is injectable (fetchJson/baseUrl) so the response guards and
// request builders can be regression-tested without a live backend.

// Transport details (base-URL bootstrap, JSON fetch, error mapping and the
// shared request pipeline) live in ./consistency-transport so the schema
// guards stay independently testable and the modules stay small. Only
// type-level contracts are imported from the shared api.ts; those imports
// are erased at runtime.
import type { ApiResult } from "./api";
import { consistencyRequest, type ConsistencyRequestOptions } from "./consistency-transport.ts";

// ── Types (mirrors backend/app/schemas/consistency.py) ─────────

export type ConsistencyStatus = "pending" | "discrepancy_detected" | "resolved";

export interface ConsistencyCheckCreate {
  application_id: number;
  check_name: string;
  description?: string | null;
  related_field?: string | null;
}

export interface ConsistencyCheck {
  id: number;
  application_id: number;
  check_name: string;
  description: string | null;
  related_field: string | null;
  status: ConsistencyStatus;
  created_at: string;
  updated_at: string;
}

export interface ConsistencyFindingCreate {
  consistency_check_id: number;
  field_name: string;
  value_1: string;
  value_2: string;
  severity: string;
  confidence?: number | null;
  description: string;
  evidence?: Record<string, unknown> | null;
}

/** Only the supplied keys are sent: the backend forbids unknown/partial bodies. */
export interface ConsistencyFindingUpdate {
  severity?: string;
  description?: string;
  evidence?: Record<string, unknown>;
  resolved?: boolean;
}

export interface ConsistencyFinding {
  id: number;
  consistency_check_id: number;
  field_name: string;
  value_1: string;
  value_2: string;
  severity: string;
  confidence: number | null;
  description: string;
  evidence: Record<string, unknown> | null;
  resolved: boolean;
  created_at: string;
  updated_at: string;
}

export interface ApplicationSummary {
  id: number;
  institution_id: number;
  application_type: string;
  academic_year: string;
  status: string;
}

export interface ApplicationPage {
  items: ApplicationSummary[];
  total: number;
  skip: number;
  limit: number;
}

// ── Response guards ────────────────────────────────────────────

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

const CONSISTENCY_STATUSES: readonly string[] = ["pending", "discrepancy_detected", "resolved"];

export function isConsistencyCheck(value: unknown): value is ConsistencyCheck {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "number" &&
    value.id > 0 &&
    typeof value.application_id === "number" &&
    value.application_id > 0 &&
    typeof value.check_name === "string" &&
    (value.description === null || typeof value.description === "string") &&
    (value.related_field === null || typeof value.related_field === "string") &&                
    typeof value.status === "string" &&
    CONSISTENCY_STATUSES.includes(value.status) &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

export function isConsistencyCheckList(value: unknown): value is ConsistencyCheck[] {
  return Array.isArray(value) && value.every(isConsistencyCheck);
}

export function isConsistencyFinding(value: unknown): value is ConsistencyFinding {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "number" &&
    value.id > 0 &&
    typeof value.consistency_check_id === "number" &&
    value.consistency_check_id > 0 &&
    typeof value.field_name === "string" &&
    typeof value.value_1 === "string" &&
    typeof value.value_2 === "string" &&
    typeof value.severity === "string" &&
    (value.confidence === null || typeof value.confidence === "number") &&
    typeof value.description === "string" &&
    (value.evidence === null || isRecord(value.evidence)) &&
    typeof value.resolved === "boolean" &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

export function isConsistencyFindingList(value: unknown): value is ConsistencyFinding[] {
  return Array.isArray(value) && value.every(isConsistencyFinding);
}

export function isApplicationPage(value: unknown): value is ApplicationPage {
  if (!isRecord(value)) return false;
  if (!Array.isArray(value.items) || typeof value.total !== "number") return false;
  return value.items.every(isRecord)
    && value.items.every((item) =>
      typeof item.id === "number" &&
      typeof item.institution_id === "number" &&
      typeof item.application_type === "string" &&
      typeof item.academic_year === "string" &&
      typeof item.status === "string");
}

// ── Transport (moved to ./consistency-transport) ───────────────

export interface ConsistencyListFilters {
  applicationId?: number;
  statusFilter?: ConsistencyStatus;
}

export interface ConsistencyFindingListFilters {
  severityFilter?: string;
  resolved?: boolean;
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

// ── Applications (tenant-scoped selector source) ────────────────

const APPLICATIONS_INVALID_MESSAGE =
  "Application list returned an invalid response.";

export function fetchApplications(
  token: string,
  options?: ConsistencyRequestOptions & { limit?: number; skip?: number },
): Promise<ApiResult<ApplicationPage>> {
  const query = buildQuery({ skip: options?.skip, limit: options?.limit });
  return consistencyRequest<ApplicationPage>(
    `/api/v1/applications${query}`,
    token,
    {},
    isApplicationPage,
    APPLICATIONS_INVALID_MESSAGE,
    options,
  );
}

// ── Consistency checks ──────────────────────────────────────────

export function createConsistencyCheck(
  payload: ConsistencyCheckCreate,
  token: string,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyCheck>> {
  return consistencyRequest<ConsistencyCheck>(
    "/api/v1/consistency/",
    token,
    { method: "POST", body: JSON.stringify(payload) },
    isConsistencyCheck,
    "Consistency check service returned an invalid response.",
    options,
  );
}

export function listConsistencyChecks(
  token: string,
  filters?: ConsistencyListFilters,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyCheck[]>> {
  const query = buildQuery({
    application_id: filters?.applicationId,
    status_filter: filters?.statusFilter,
  });
  return consistencyRequest<ConsistencyCheck[]>(
    `/api/v1/consistency/${query}`,
    token,
    {},
    isConsistencyCheckList,
    "Saved consistency checks returned an invalid response.",
    options,
  );
}

export function getConsistencyCheck(
  checkId: number,
  token: string,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyCheck>> {
  return consistencyRequest<ConsistencyCheck>(
    `/api/v1/consistency/${checkId}`,
    token,
    {},
    isConsistencyCheck,
    "Consistency check service returned an invalid response.",
    options,
  );
}

// ── Consistency findings ────────────────────────────────────────

export function listConsistencyFindings(
  checkId: number,
  token: string,
  filters?: ConsistencyFindingListFilters,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyFinding[]>> {
  const query = buildQuery({
    severity_filter: filters?.severityFilter,
    resolved: filters?.resolved,
  });
  return consistencyRequest<ConsistencyFinding[]>(
    `/api/v1/consistency/checks/${checkId}/findings${query}`,
    token,
    {},
    isConsistencyFindingList,
    "Findings service returned an invalid response.",
    options,
  );
}

export function createConsistencyFinding(
  payload: ConsistencyFindingCreate,
  token: string,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyFinding>> {
  return consistencyRequest<ConsistencyFinding>(
    "/api/v1/consistency/findings",
    token,
    { method: "POST", body: JSON.stringify(payload) },
    isConsistencyFinding,
    "Findings service returned an invalid response.",
    options,
  );
}

export function updateConsistencyFinding(
  findingId: number,
  payload: ConsistencyFindingUpdate,
  token: string,
  options?: ConsistencyRequestOptions,
): Promise<ApiResult<ConsistencyFinding>> {
  return consistencyRequest<ConsistencyFinding>(
    `/api/v1/consistency/findings/${findingId}`,
    token,
    { method: "PATCH", body: JSON.stringify(payload) },
    isConsistencyFinding,
    "Findings service returned an invalid response.",
    options,
  );
}
