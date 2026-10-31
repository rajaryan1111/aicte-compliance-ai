/**
 * Server persistence for remediation plans.
 *
 * The plan is computed in the browser from a preliminary validation result and then stored against
 * the institution, so progress is shared by every authorised officer instead of living in one
 * browser's localStorage. The browser stays usable offline: callers keep the local copy as a cache
 * and apply the returned snapshot when a sync succeeds.
 *
 * Nothing here evaluates compliance. Stored due dates are internal recommendations derived from a
 * configurable policy, never AICTE deadlines.
 */

import { apiUrl } from "./api.ts";
import {
  applyDeadlinePolicy,
  normalizeDeadlinePolicy,
  type ActionPlan,
  type DeadlinePolicy,
  type PlanItem,
  type PlanStatus,
} from "./action-plan.ts";

export const PLAN_POLICY_STORAGE_KEY = "aicte.deadlinePolicy.v1";

export interface RemoteTaskSnapshot {
  taskKey: string;
  status: PlanStatus;
  note: string;
  version: number;
  dueDate: string;
  statusChangedBy: string | null;
  statusChangedAt: string | null;
}

export interface RemoteDeadlineChange {
  changedBy: string;
  changedAt: string;
  rescheduledTasks: number;
  newPolicy: DeadlinePolicy;
}

export interface RemotePlanSnapshot {
  id: number;
  institutionRef: string;
  planKey: string;
  applicationType: string;
  deadlinePolicy: DeadlinePolicy;
  tasks: RemoteTaskSnapshot[];
  /** Newest first; empty when no administrator has rescheduled the plan. */
  deadlineHistory: RemoteDeadlineChange[];
  updatedAt: string;
  createdBy: string;
}

export type PlanSyncFailure =
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "validation"
  | "network"
  | "server"
  | "invalid_response"
  | "not_configured";

export type PlanSyncResult =
  | { ok: true; plan: RemotePlanSnapshot }
  | { ok: false; kind: PlanSyncFailure; message: string };

/**
 * Some failures cannot be fixed by retrying: the account is not linked to the institution, the role
 * is read-only, or the deployment has no plan API. Only genuine transient failures offer a retry.
 */
export function isRetryableSyncFailure(kind: PlanSyncFailure): boolean {
  return kind === "network" || kind === "server" || kind === "conflict" || kind === "unauthenticated";
}

const PLAN_STATUSES: PlanStatus[] = ["open", "in_progress", "blocked", "done"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function failure(kind: PlanSyncFailure, message: string): PlanSyncResult {
  return { ok: false, kind, message };
}

/** Reads a stored policy, falling back to defaults when storage is unavailable or malformed. */
export function readStoredDeadlinePolicy(): DeadlinePolicy | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(PLAN_POLICY_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isRecord(parsed) ? normalizeDeadlinePolicy(parsed as Partial<DeadlinePolicy>) : null;
  } catch {
    return null;
  }
}

export function storeDeadlinePolicy(policy: DeadlinePolicy): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PLAN_POLICY_STORAGE_KEY, JSON.stringify(normalizeDeadlinePolicy(policy)));
  } catch {
    // Storage can be blocked (private mode, quota). The in-memory policy still applies.
  }
}

export function toDeadlinePolicyPayload(policy: DeadlinePolicy) {
  const resolved = normalizeDeadlinePolicy(policy);
  return {
    p1_days: resolved.p1Days,
    p2_days: resolved.p2Days,
    p3_buffer_days: resolved.p3BufferDays,
    p3_max_days: resolved.p3MaxDays,
    expiring_window_days: resolved.expiringWindowDays,
  };
}

/** Request body for create-or-get. Mirrors the backend RemediationPlanCreateRequest schema. */
export function buildPlanPayload(
  plan: ActionPlan,
  policy: DeadlinePolicy,
  institutionRef: string,
) {
  return {
    institution_ref: institutionRef,
    plan_key: plan.planId,
    application_type: plan.applicationType,
    deadline_policy: toDeadlinePolicyPayload(policy),
    items: plan.items.map((item) => ({
      task_key: item.id,
      document_id: item.documentId,
      document_label: item.documentLabel,
      finding_code: item.findingCode,
      priority: item.priority,
      owner_role: item.ownerRole,
      due_date: item.dueDate,
      evidence_required: item.evidenceRequired,
      clause: item.clause,
    })),
  };
}

function parsePolicy(value: unknown): DeadlinePolicy {
  if (!isRecord(value)) return normalizeDeadlinePolicy(null);
  return normalizeDeadlinePolicy({
    p1Days: Number(value.p1_days),
    p2Days: Number(value.p2_days),
    p3BufferDays: Number(value.p3_buffer_days),
    p3MaxDays: Number(value.p3_max_days),
    expiringWindowDays: Number(value.expiring_window_days),
  });
}

function parseDeadlineChange(value: unknown): RemoteDeadlineChange | null {
  if (!isRecord(value)) return null;
  return {
    changedBy: typeof value.changed_by === "string" ? value.changed_by : "",
    changedAt: typeof value.created_at === "string" ? value.created_at : "",
    rescheduledTasks: typeof value.rescheduled_tasks === "number" ? value.rescheduled_tasks : 0,
    newPolicy: parsePolicy(value.new_policy),
  };
}

function parseTask(value: unknown): RemoteTaskSnapshot | null {
  if (!isRecord(value)) return null;
  const { task_key, status, note, version, due_date } = value;
  if (typeof task_key !== "string" || typeof due_date !== "string") return null;
  if (typeof status !== "string" || !PLAN_STATUSES.includes(status as PlanStatus)) return null;
  if (typeof version !== "number" || !Number.isInteger(version) || version < 1) return null;
  return {
    taskKey: task_key,
    status: status as PlanStatus,
    note: typeof note === "string" ? note : "",
    version,
    dueDate: due_date,
    statusChangedBy: typeof value.status_changed_by === "string" ? value.status_changed_by : null,
    statusChangedAt: typeof value.status_changed_at === "string" ? value.status_changed_at : null,
  };
}

/** Validates a server payload. Returns null rather than trusting an unexpected shape. */
export function parseRemotePlan(value: unknown): RemotePlanSnapshot | null {
  if (!isRecord(value)) return null;
  const { id, plan_key, institution_ref, application_type, tasks } = value;
  if (typeof id !== "number" || typeof plan_key !== "string" || typeof institution_ref !== "string") {
    return null;
  }
  if (!Array.isArray(tasks)) return null;
  const parsed = tasks.map(parseTask);
  if (parsed.some((task) => task === null)) return null;
  const history = Array.isArray(value.deadline_history)
    ? value.deadline_history.map(parseDeadlineChange).filter((entry): entry is RemoteDeadlineChange => entry !== null)
    : [];
  return {
    id,
    planKey: plan_key,
    institutionRef: institution_ref,
    applicationType: typeof application_type === "string" ? application_type : "",
    deadlinePolicy: parsePolicy(value.deadline_policy),
    tasks: parsed as RemoteTaskSnapshot[],
    deadlineHistory: history,
    updatedAt: typeof value.updated_at === "string" ? value.updated_at : "",
    createdBy: typeof value.created_by === "string" ? value.created_by : "",
  };
}

async function requestJson(
  path: string,
  token: string,
  init: RequestInit,
): Promise<{ ok: true; status: number; body: unknown } | { ok: false; kind: PlanSyncFailure; message: string }> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(apiUrl(path), { ...init, headers });
  } catch {
    return {
      ok: false,
      kind: "network",
      message: "Could not reach the server. Your changes stay saved in this browser until it reconnects.",
    };
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (response.ok) return { ok: true, status: response.status, body };

  if (response.status === 401) return { ok: false, kind: "unauthenticated", message: "Your session expired. Sign in again to sync this plan." };
  if (response.status === 403) return { ok: false, kind: "forbidden", message: "Your role can view this institution's plan but cannot change it." };
  if (response.status === 404) {
    // A 404 is deliberately ambiguous: it can mean the account is not linked to this institution,
    // or that the deployed backend is older than this front-end and has no plan routes at all.
    return {
      ok: false,
      kind: "not_found",
      message:
        "Shared plan storage is unavailable for this account or this deployment, so the plan stays " +
        "in this browser. Your work is not lost; ask an administrator to link your account, or ask " +
        "the deployment owner to update the backend.",
    };
  }
  if (response.status === 409) return { ok: false, kind: "conflict", message: "Another user changed this task. Reload the plan to see their update." };
  if (response.status === 422) {
    const detail = isRecord(body) && typeof body.detail === "string" ? body.detail : "The server rejected the plan data.";
    return { ok: false, kind: "validation", message: detail };
  }
  if (response.status === 503) return { ok: false, kind: "not_configured", message: "Server-side plans are not configured on this deployment." };
  return { ok: false, kind: "server", message: `The plan service returned an error (${response.status}).` };
}

/**
 * Create-or-get the stored plan for this deficiency signature.
 *
 * Idempotent: re-posting the same plan_key returns the existing plan with its current progress, so a
 * repeated validation run never resets work. The payload is re-sent rather than patched so task
 * metadata stays aligned with the latest rule catalog.
 */
export async function syncPlan(
  institutionRef: string,
  plan: ActionPlan,
  policy: DeadlinePolicy,
  token: string,
): Promise<PlanSyncResult> {
  const result = await requestJson(
    `/api/v1/institutions/${encodeURIComponent(institutionRef)}/remediation-plans`,
    token,
    { method: "POST", body: JSON.stringify(buildPlanPayload(plan, policy, institutionRef)) },
  );
  if (!result.ok) return result;
  const parsed = parseRemotePlan(result.body);
  if (!parsed) return failure("invalid_response", "The plan service returned an unexpected response.");
  return { ok: true, plan: parsed };
}

/** Reads the stored plan for a signature, or null when none has been saved yet. */
export async function fetchStoredPlan(
  institutionRef: string,
  planKey: string,
  token: string,
): Promise<PlanSyncResult | null> {
  const query = new URLSearchParams({ plan_key: planKey });
  const result = await requestJson(
    `/api/v1/institutions/${encodeURIComponent(institutionRef)}/remediation-plans?${query.toString()}`,
    token,
    { method: "GET" },
  );
  if (!result.ok) return result;
  if (!isRecord(result.body) || !Array.isArray(result.body.items)) {
    return failure("invalid_response", "The plan service returned an unexpected response.");
  }
  if (result.body.items.length === 0) return null;
  const parsed = parseRemotePlan(result.body.items[0]);
  if (!parsed) return failure("invalid_response", "The plan service returned an unexpected response.");
  return { ok: true, plan: parsed };
}

/**
 * Push one task change using optimistic concurrency.
 *
 * The current version is read first so a stale browser tab cannot silently overwrite a colleague's
 * update; the server's 409 is surfaced instead.
 */
export async function pushTaskUpdate(
  institutionRef: string,
  remotePlanId: number,
  taskKey: string,
  change: { status?: PlanStatus; note?: string },
  token: string,
): Promise<PlanSyncResult> {
  const base = `/api/v1/institutions/${encodeURIComponent(institutionRef)}/remediation-plans/${remotePlanId}`;
  const current = await requestJson(base, token, { method: "GET" });
  if (!current.ok) return current;
  const parsed = parseRemotePlan(current.body);
  if (!parsed) return failure("invalid_response", "The plan service returned an unexpected response.");
  const task = parsed.tasks.find((entry) => entry.taskKey === taskKey);
  if (!task) return failure("not_found", "This task is no longer part of the stored plan. Reload to re-sync.");

  const body: Record<string, unknown> = { version: task.version };
  if (change.status !== undefined) body.status = change.status;
  if (change.note !== undefined) body.note = change.note;

  const patched = await requestJson(`${base}/tasks/${encodeURIComponent(taskKey)}`, token, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (!patched.ok) return patched;

  const updated = parseTask(patched.body);
  if (!updated) return failure("invalid_response", "The plan service returned an unexpected response.");
  return {
    ok: true,
    plan: {
      ...parsed,
      tasks: parsed.tasks.map((entry) => (entry.taskKey === taskKey ? updated : entry)),
    },
  };
}

/**
 * Apply a stored plan onto a freshly built local plan.
 *
 * Only progress fields are taken from the server: due dates follow the saved policy, while the
 * deficiency list itself always comes from the current validation result.
 */
export function mergeRemotePlan(local: ActionPlan, remote: RemotePlanSnapshot): ActionPlan {
  if (remote.planKey !== local.planId) return local;
  const byKey = new Map(remote.tasks.map((task) => [task.taskKey, task]));
  const scheduled = applyDeadlinePolicy(local, remote.deadlinePolicy);

  const items: PlanItem[] = scheduled.items.map((item) => {
    const stored = byKey.get(item.id);
    if (!stored) return item;
    return {
      ...item,
      dueDate: stored.dueDate,
      status: stored.status,
      note: stored.note,
    };
  });

  return { ...scheduled, items };
}

/**
 * True when the stored plan already reflects every local status and note, so no write is needed.
 * Keeps routine renders from issuing redundant PATCH requests.
 */
export function planMatchesRemote(local: ActionPlan, remote: RemotePlanSnapshot): boolean {
  if (remote.planKey !== local.planId) return false;
  if (remote.tasks.length !== local.items.length) return false;
  const byKey = new Map(remote.tasks.map((task) => [task.taskKey, task]));
  return local.items.every((item) => {
    const stored = byKey.get(item.id);
    return stored !== undefined && stored.status === item.status && stored.note === item.note;
  });
}

/**
 * Change the shared schedule. Restricted server-side to institution administrators.
 *
 * The returned snapshot already carries the rescheduled due dates and the appended history entry,
 * so callers should replace their remote state with it instead of guessing dates locally.
 */
export async function updateDeadlinePolicy(
  institutionRef: string,
  remotePlanId: number,
  policy: DeadlinePolicy,
  token: string,
): Promise<PlanSyncResult> {
  const result = await requestJson(
    `/api/v1/institutions/${encodeURIComponent(institutionRef)}/remediation-plans/${remotePlanId}/deadline-policy`,
    token,
    { method: "PATCH", body: JSON.stringify({ policy: toDeadlinePolicyPayload(policy) }) },
  );
  if (!result.ok) return result;
  const parsed = parseRemotePlan(result.body);
  if (!parsed) return failure("invalid_response", "The plan service returned an unexpected response.");
  return { ok: true, plan: parsed };
}
