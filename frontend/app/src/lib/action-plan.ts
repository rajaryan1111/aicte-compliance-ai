/**
 * Deterministic remediation plan derived from a validation result.
 *
 * No network, no storage side effects in the pure functions: the component owns persistence so
 * every rule here stays testable with Node's type-stripping test runner.
 */

import type { Finding, ValidationRequest, ValidationResponse } from "./api.ts";
import { lookupDocumentGuidance } from "./compliance-guidance.ts";
import { safeSpreadsheetValue } from "./report.ts";

export type PlanPriority = "P1" | "P2" | "P3";
export type PlanStatus = "open" | "in_progress" | "blocked" | "done";
export type PlanFindingCode = "MISSING_DOCUMENT" | "DOCUMENT_EXPIRED" | "EXPIRING_SOON";

export interface PlanItem {
  /** Stable within a plan: document id + finding code. */
  id: string;
  documentId: string;
  documentLabel: string;
  findingCode: PlanFindingCode;
  priority: PlanPriority;
  ownerRole: string;
  dueDate: string;
  evidenceRequired: string;
  /** Catalog citation, or null when no mapping exists. Never synthesized. */
  clause: string | null;
  /** Expiry date that drove an EXPIRING_SOON task; null for other findings. */
  expiryDate: string | null;
  status: PlanStatus;
  note: string;
}

export interface ActionPlan {
  planId: string;
  institutionId: string;
  applicationType: string;
  checkedAt: string;
  createdAt: string;
  items: PlanItem[];
}

export interface PlanSummary {
  total: number;
  done: number;
  open: number;
  inProgress: number;
  blocked: number;
  overdue: number;
  completionPct: number;
  nextDueDate: string | null;
}

export const ACTION_PLAN_STORAGE_KEY = "aicte.actionPlans.v1";
export const ACTION_PLAN_STORAGE_VERSION = 1;
export const MAX_STORED_PLANS = 25;
export const EXPIRING_SOON_DAYS = 60;

/** P1 statutory gap, P2 other gap, P3 certificate expiring within the window. */
const DUE_OFFSET_DAYS: Record<PlanPriority, number> = { P1: 3, P2: 7, P3: 21 };

/**
 * Configurable deadline policy for internal task scheduling.
 *
 * These offsets are a project recommendation for managing the work. They are NOT AICTE deadlines
 * and must never be presented as official dates; the UI labels them accordingly.
 */
export interface DeadlinePolicy {
  p1Days: number;
  p2Days: number;
  p3BufferDays: number;
  p3MaxDays: number;
  expiringWindowDays: number;
}

export const DEFAULT_DEADLINE_POLICY: DeadlinePolicy = {
  p1Days: 3,
  p2Days: 7,
  p3BufferDays: 14,
  p3MaxDays: 21,
  expiringWindowDays: 60,
};

export const MAX_DEADLINE_DAYS = 365;

function clampDays(value: number, minimum: number): number {
  if (!Number.isFinite(value)) return minimum;
  return Math.min(MAX_DEADLINE_DAYS, Math.max(minimum, Math.round(value)));
}

/** Clamp arbitrary input into a valid policy; also used when restoring stored settings. */
export function normalizeDeadlinePolicy(input?: Partial<DeadlinePolicy> | null): DeadlinePolicy {
  const p1Days = clampDays(input?.p1Days ?? DEFAULT_DEADLINE_POLICY.p1Days, 1);
  return {
    p1Days,
    p2Days: clampDays(input?.p2Days ?? DEFAULT_DEADLINE_POLICY.p2Days, p1Days),
    p3BufferDays: clampDays(input?.p3BufferDays ?? DEFAULT_DEADLINE_POLICY.p3BufferDays, 0),
    p3MaxDays: clampDays(input?.p3MaxDays ?? DEFAULT_DEADLINE_POLICY.p3MaxDays, 1),
    expiringWindowDays: clampDays(
      input?.expiringWindowDays ?? DEFAULT_DEADLINE_POLICY.expiringWindowDays,
      1,
    ),
  };
}

/**
 * Re-derive every due date from a policy. Statuses and notes are preserved.
 *
 * EXPIRING_SOON tasks work backwards from expiry by the buffer, capped by `p3MaxDays` so a
 * far-off certificate cannot create a deadline months away.
 */
export function applyDeadlinePolicy(
  plan: ActionPlan,
  policy: DeadlinePolicy,
  now: Date = new Date(),
): ActionPlan {
  const resolved = normalizeDeadlinePolicy(policy);
  const today = formatIsoDate(now);
  const earliest = addDays(today, 1);
  const p3Cap = addDays(today, resolved.p3MaxDays);

  return {
    ...plan,
    items: plan.items.map((item) => {
      let dueDate: string;
      if (item.findingCode === "EXPIRING_SOON" && item.expiryDate) {
        const fromExpiry = addDays(item.expiryDate, -resolved.p3BufferDays);
        const candidate = daysBetween(today, fromExpiry) < 1 ? earliest : fromExpiry;
        dueDate = daysBetween(today, candidate) > daysBetween(today, p3Cap) ? p3Cap : candidate;
      } else if (item.priority === "P1") {
        dueDate = addDays(today, resolved.p1Days);
      } else if (item.priority === "P2") {
        dueDate = addDays(today, resolved.p2Days);
      } else {
        dueDate = p3Cap;
      }
      return { ...item, dueDate };
    }),
  };
}

const STATUS_ORDER: PlanStatus[] = ["open", "in_progress", "blocked", "done"];

export function isPlanStatus(value: unknown): value is PlanStatus {
  return typeof value === "string" && (STATUS_ORDER as string[]).includes(value);
}

export function parseIsoDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return null;
  }
  return date;
}

export function formatIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function todayIso(now: Date = new Date()): string {
  return formatIsoDate(now);
}

export function addDays(isoDate: string, days: number): string {
  const base = parseIsoDate(isoDate);
  if (!base) throw new Error(`Invalid ISO date: ${isoDate}`);
  base.setUTCDate(base.getUTCDate() + days);
  return formatIsoDate(base);
}

/** Whole days from `from` to `to`; negative when `to` is in the past. */
export function daysBetween(from: string, to: string): number {
  const start = parseIsoDate(from);
  const end = parseIsoDate(to);
  if (!start || !end) return 0;
  return Math.round((end.getTime() - start.getTime()) / 86_400_000);
}

function fnv1a(input: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

/**
 * Keyed by institution, application type and the set of deficiencies, never by the run
 * timestamp: re-running the same checklist must reopen the same plan so recorded progress
 * survives re-validation. Changing the deficiencies is a genuinely different plan.
 */
export function planIdFor(
  institutionId: string,
  applicationType: string,
  deficiencySignature: string,
): string {
  return `plan-${fnv1a(`${institutionId}|${applicationType}|${deficiencySignature}`)}`;
}

function displayLabel(documentId: string): string {
  const guidance = lookupDocumentGuidance(documentId);
  if (guidance) return guidance.label.en;
  return documentId
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function dueOffsetFor(priority: PlanPriority): number {
  return DUE_OFFSET_DAYS[priority];
}

function priorityFor(zeroTolerance: boolean, code: PlanFindingCode): PlanPriority {
  if (code === "EXPIRING_SOON") return "P3";
  return zeroTolerance ? "P1" : "P2";
}

function evidenceFor(documentId: string, code: PlanFindingCode): string {
  const guidance = lookupDocumentGuidance(documentId);
  if (code === "DOCUMENT_EXPIRED") {
    return guidance
      ? `Renewed ${guidance.label.en.toLowerCase()} with a validity date after the submission date. ${guidance.evidenceRequired.en}`
      : "A renewed certificate whose validity date falls after the submission date.";
  }
  if (code === "EXPIRING_SOON") {
    return guidance
      ? `Renewal acknowledgement before the current date lapses. ${guidance.evidenceRequired.en}`
      : "A renewal acknowledgement received before the current certificate lapses.";
  }
  return guidance
    ? guidance.evidenceRequired.en
    : "The document itself, named exactly as it appears in the required list.";
}

function ownerFor(documentId: string): string {
  return lookupDocumentGuidance(documentId)?.ownerRole.en ?? "Registrar / Principal";
}

function clauseFor(documentId: string): string | null {
  return lookupDocumentGuidance(documentId)?.clause ?? null;
}

function zeroToleranceFor(documentId: string): boolean {
  return lookupDocumentGuidance(documentId)?.isStatutoryZeroTolerance ?? false;
}

function itemIdFor(documentId: string, code: PlanFindingCode): string {
  return `${documentId}::${code}`;
}

function buildItem(
  documentId: string,
  code: PlanFindingCode,
  today: string,
  expiryDate?: string,
): PlanItem {
  const zeroTolerance = zeroToleranceFor(documentId);
  const priority = priorityFor(zeroTolerance, code);
  let dueDate = addDays(today, dueOffsetFor(priority));

  if (code === "EXPIRING_SOON" && expiryDate) {
    // Work backwards from the expiry, leaving a fortnight of buffer, but never in the past.
    const renewalTarget = addDays(expiryDate, -14);
    const earliest = addDays(today, 1);
    dueDate = daysBetween(today, renewalTarget) < 1 ? earliest : renewalTarget;
  }

  return {
    id: itemIdFor(documentId, code),
    documentId,
    documentLabel: displayLabel(documentId),
    findingCode: code,
    priority,
    ownerRole: ownerFor(documentId),
    dueDate,
    evidenceRequired: evidenceFor(documentId, code),
    clause: clauseFor(documentId),
    expiryDate: code === "EXPIRING_SOON" && expiryDate ? expiryDate : null,
    status: "open",
    note: "",
  };
}

function sortItems(items: PlanItem[]): PlanItem[] {
  const priorityRank: Record<PlanPriority, number> = { P1: 0, P2: 1, P3: 2 };
  return [...items].sort((left, right) => {
    const byPriority = priorityRank[left.priority] - priorityRank[right.priority];
    if (byPriority !== 0) return byPriority;
    const byDue = left.dueDate.localeCompare(right.dueDate);
    if (byDue !== 0) return byDue;
    return left.documentLabel.localeCompare(right.documentLabel);
  });
}

/** Certificates that lapse inside the window but are not already reported as expired. */
function expiringSoon(
  request: ValidationRequest,
  response: ValidationResponse,
  today: string,
): Array<{ documentId: string; expiryDate: string }> {
  const expired = new Set(response.expired_documents);
  const missing = new Set(response.missing_documents);
  const result: Array<{ documentId: string; expiryDate: string }> = [];

  for (const documentId of request.submitted_documents) {
    if (expired.has(documentId) || missing.has(documentId)) continue;
    const expiryDate = request.expiry_dates[documentId];
    if (!expiryDate) continue;
    if (!parseIsoDate(expiryDate)) continue;
    const remaining = daysBetween(today, expiryDate);
    if (remaining >= 0 && remaining <= EXPIRING_SOON_DAYS) {
      result.push({ documentId, expiryDate });
    }
  }
  return result;
}

export function buildActionPlan(
  request: ValidationRequest,
  response: ValidationResponse,
  now: Date = new Date(),
): ActionPlan {
  const today = formatIsoDate(now);
  const items: PlanItem[] = [];
  const seen = new Set<string>();

  const add = (item: PlanItem) => {
    if (seen.has(item.id)) return;
    seen.add(item.id);
    items.push(item);
  };

  // Derive from the typed lists as well as the findings, so a response that omits a finding
  // entry still produces a complete plan. `add` de-duplicates by document + code.
  for (const documentId of response.missing_documents) {
    add(buildItem(documentId, "MISSING_DOCUMENT", today));
  }
  for (const documentId of response.expired_documents) {
    add(buildItem(documentId, "DOCUMENT_EXPIRED", today));
  }
  for (const finding of response.findings as Finding[]) {
    add(buildItem(finding.document_type, finding.code, today));
  }

  for (const { documentId, expiryDate } of expiringSoon(request, response, today)) {
    add(buildItem(documentId, "EXPIRING_SOON", today, expiryDate));
  }

  const sortedItems = sortItems(items);
  const signature = sortedItems
    .map((item) => item.id)
    .sort()
    .join("|");

  return {
    planId: planIdFor(request.institution_id, response.application_type, signature),
    institutionId: request.institution_id,
    applicationType: response.application_type,
    checkedAt: response.checked_at,
    createdAt: now.toISOString(),
    items: sortedItems,
  };
}

/**
 * Carry statuses and notes from a previously stored plan onto a fresh run of the same plan.
 * Only matching task ids inherit; a task that appears or disappears is never guessed at.
 */
export function mergePlanProgress(current: ActionPlan, previous: ActionPlan): ActionPlan {
  const previousById = new Map(previous.items.map((item) => [item.id, item]));
  return {
    ...current,
    items: current.items.map((item) => {
      const carried = previousById.get(item.id);
      return carried ? { ...item, status: carried.status, note: carried.note } : item;
    }),
  };
}

export function summarizePlan(plan: ActionPlan, now: Date = new Date()): PlanSummary {
  const today = formatIsoDate(now);
  let done = 0;
  let open = 0;
  let inProgress = 0;
  let blocked = 0;
  let overdue = 0;
  let nextDueDate: string | null = null;

  for (const item of plan.items) {
    if (item.status === "done") {
      done += 1;
      continue;
    }
    if (item.status === "open") open += 1;
    if (item.status === "in_progress") inProgress += 1;
    if (item.status === "blocked") blocked += 1;
    if (daysBetween(today, item.dueDate) < 0) overdue += 1;
    if (nextDueDate === null || item.dueDate < nextDueDate) nextDueDate = item.dueDate;
  }

  const total = plan.items.length;
  return {
    total,
    done,
    open,
    inProgress,
    blocked,
    overdue,
    completionPct: total === 0 ? 100 : Math.round((done / total) * 100),
    nextDueDate,
  };
}

export function setItemStatus(plan: ActionPlan, itemId: string, status: PlanStatus): ActionPlan {
  return {
    ...plan,
    items: plan.items.map((item) => (item.id === itemId ? { ...item, status } : item)),
  };
}

export function setItemNote(plan: ActionPlan, itemId: string, note: string): ActionPlan {
  return {
    ...plan,
    items: plan.items.map((item) =>
      item.id === itemId ? { ...item, note: note.slice(0, 280) } : item,
    ),
  };
}

export function resetPlanProgress(plan: ActionPlan): ActionPlan {
  return {
    ...plan,
    items: plan.items.map((item) => (item.status === "done" ? { ...item, status: "open" } : item)),
  };
}

// ── Storage codec ────────────────────────────────────────────────────────────

function sanitizeItem(value: unknown): PlanItem | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  const findingCode = item.findingCode;
  const priority = item.priority;
  if (
    typeof item.id !== "string" ||
    typeof item.documentId !== "string" ||
    typeof item.documentLabel !== "string" ||
    typeof item.dueDate !== "string" ||
    !parseIsoDate(item.dueDate) ||
    (findingCode !== "MISSING_DOCUMENT" &&
      findingCode !== "DOCUMENT_EXPIRED" &&
      findingCode !== "EXPIRING_SOON") ||
    (priority !== "P1" && priority !== "P2" && priority !== "P3")
  ) {
    return null;
  }
  return {
    id: item.id,
    documentId: item.documentId,
    documentLabel: item.documentLabel,
    findingCode,
    priority,
    ownerRole: typeof item.ownerRole === "string" ? item.ownerRole : "Registrar / Principal",
    dueDate: item.dueDate,
    evidenceRequired:
      typeof item.evidenceRequired === "string" ? item.evidenceRequired : "Document evidence.",
    clause: typeof item.clause === "string" ? item.clause : null,
    expiryDate:
      typeof item.expiryDate === "string" && parseIsoDate(item.expiryDate)
        ? item.expiryDate
        : null,
    status: isPlanStatus(item.status) ? item.status : "open",
    note: typeof item.note === "string" ? item.note.slice(0, 280) : "",
  };
}

function sanitizePlan(value: unknown): ActionPlan | null {
  if (!value || typeof value !== "object") return null;
  const plan = value as Record<string, unknown>;
  if (
    typeof plan.planId !== "string" ||
    typeof plan.institutionId !== "string" ||
    typeof plan.applicationType !== "string" ||
    typeof plan.checkedAt !== "string" ||
    typeof plan.createdAt !== "string" ||
    !Array.isArray(plan.items)
  ) {
    return null;
  }
  const items = plan.items.map(sanitizeItem).filter((item): item is PlanItem => item !== null);
  if (items.length !== plan.items.length) return null;
  return {
    planId: plan.planId,
    institutionId: plan.institutionId,
    applicationType: plan.applicationType,
    checkedAt: plan.checkedAt,
    createdAt: plan.createdAt,
    items,
  };
}

/** Tolerant parse: corrupt or foreign JSON yields an empty store instead of throwing. */
export function parseStoredPlans(raw: string | null): ActionPlan[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return [];
    const record = parsed as Record<string, unknown>;
    if (record.version !== ACTION_PLAN_STORAGE_VERSION || !Array.isArray(record.plans)) return [];
    const plans = record.plans
      .map(sanitizePlan)
      .filter((plan): plan is ActionPlan => plan !== null);
    return plans.slice(0, MAX_STORED_PLANS);
  } catch {
    return [];
  }
}

export function serializeStoredPlans(plans: ActionPlan[]): string {
  return JSON.stringify({
    version: ACTION_PLAN_STORAGE_VERSION,
    plans: plans.slice(0, MAX_STORED_PLANS),
  });
}

/** Insert or replace by planId, newest first, capped so storage cannot grow without bound. */
export function upsertPlan(plans: ActionPlan[], plan: ActionPlan): ActionPlan[] {
  const without = plans.filter((entry) => entry.planId !== plan.planId);
  return [plan, ...without].slice(0, MAX_STORED_PLANS);
}

// ── CSV ──────────────────────────────────────────────────────────────────────

const CSV_COLUMNS = [
  "plan_id",
  "institution_id",
  "application_type",
  "checked_at",
  "plan_created_at",
  "priority",
  "document",
  "finding",
  "owner_role",
  "due_date",
  "status",
  "clause",
  "evidence_required",
  "note",
  "guidance_note",
] as const;

function csvCell(value: string): string {
  return `"${safeSpreadsheetValue(value).replace(/"/g, '""')}"`;
}

export function createActionPlanCsv(
  plan: ActionPlan,
  guidanceNote = "Plan derived from a caller-supplied preliminary validation. Not an AICTE determination.",
): string {
  const rows = plan.items.map((item) => [
    plan.planId,
    plan.institutionId,
    plan.applicationType,
    plan.checkedAt,
    plan.createdAt,
    item.priority,
    item.documentLabel,
    item.findingCode,
    item.ownerRole,
    item.dueDate,
    item.status,
    item.clause ?? "",
    item.evidenceRequired,
    item.note,
    guidanceNote,
  ]);

  return [CSV_COLUMNS as readonly string[], ...rows]
    .map((row) => row.map((cell) => csvCell(cell)).join(","))
    .join("\r\n") + "\r\n";
}
